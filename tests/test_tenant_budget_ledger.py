from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
import subprocess
import sys
import threading

import pytest

from axio_fusion_api.tenant_budget_ledger import (
    InMemoryTenantBudgetLedger,
    SQLiteTenantBudgetLedger,
    TenantBudgetLedgerInvariantError,
    TenantBudgetLedgerUnavailable,
)


def test_sqlite_ledger_is_idempotent_across_two_instances(tmp_path):
    path = tmp_path / "tenant-budget.db"
    first = SQLiteTenantBudgetLedger(str(path))
    second = SQLiteTenantBudgetLedger(str(path))
    reservation = first.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.40,
        budget_usd=0.50,
        reservation_key="same-request",
    )
    replay = second.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.40,
        budget_usd=0.50,
        reservation_key="same-request",
    )
    assert replay.reservation_id == reservation.reservation_id
    assert replay.idempotent_replay is True
    settled = second.settle(
        reservation_id=reservation.reservation_id,
        actual_cost_usd=0.30,
        success=True,
    )
    assert settled.committed_usd == 0.30
    follow_up = first.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.10,
        budget_usd=0.50,
        reservation_key="follow-up",
    )
    first.settle(reservation_id=follow_up.reservation_id, actual_cost_usd=0.10, success=True)
    assert first.settle(
        reservation_id=reservation.reservation_id,
        actual_cost_usd=0.90,
        success=True,
    ) == settled.__class__(
        reservation_id=settled.reservation_id,
        status="settled",
        committed_usd=0.30,
        reserved_usd=0.0,
        actual_cost_usd=0.30,
        overcommit=False,
        idempotent_replay=True,
    )


def test_sqlite_ledger_serializes_cross_instance_reservations(tmp_path):
    path = tmp_path / "tenant-budget.db"
    ledgers = [SQLiteTenantBudgetLedger(str(path)), SQLiteTenantBudgetLedger(str(path))]
    barrier = threading.Barrier(8)

    def reserve(index: int):
        barrier.wait()
        return ledgers[index % 2].reserve(
            tenant_hash="tenant-hash",
            day="2026-09-19",
            amount_usd=0.20,
            budget_usd=1.00,
            reservation_key=f"request-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(reserve, range(8)))
    assert sum(row.allowed for row in rows) == 5
    assert ledgers[0].snapshot(day="2026-09-19")["rows"][0]["reserved_usd"] == 1.0


def test_sqlite_ledger_releases_failed_request_and_keeps_safe_snapshot(tmp_path):
    ledger = SQLiteTenantBudgetLedger(str(tmp_path / "tenant-budget.db"))
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.20,
        budget_usd=1.00,
        reservation_key="failed-request",
    )
    released = ledger.settle(
        reservation_id=reservation.reservation_id,
        actual_cost_usd=None,
        success=False,
    )
    assert released.status == "released"
    assert ledger.snapshot(day="2026-09-19")["rows"][0]["reserved_usd"] == 0.0
    assert ledger.snapshot(day="2026-09-19")["raw_api_keys_persisted"] is False


def test_sqlite_ledger_requires_explicit_recovery_after_process_exit(tmp_path):
    path = tmp_path / "crashed-budget.db"
    child_code = (
        "import os, sys; "
        "from axio_fusion_api.tenant_budget_ledger import SQLiteTenantBudgetLedger; "
        "ledger=SQLiteTenantBudgetLedger(sys.argv[1]); "
        "row=ledger.reserve(tenant_hash='tenant-hash', day='2026-09-19', amount_usd=0.40, "
        "budget_usd=0.50, reservation_key='crashed-request'); "
        "print(row.reservation_id, flush=True); os._exit(0)"
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(os.path.join(os.getcwd(), "src")), environment.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [sys.executable, "-c", child_code, str(path)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    reservation_id = completed.stdout.strip()
    ledger = SQLiteTenantBudgetLedger(str(path))
    assert ledger.snapshot(day="2026-09-19")["rows"][0]["reserved_usd"] == 0.40
    recovered = ledger.recover(
        reservation_id=reservation_id,
        recovery_key="operator-recovery-20260919",
        reason="worker process exited before settlement",
    )
    assert recovered.status == "released"
    assert recovered.reason_code == "tenant_budget_reservation_recovered"
    replay = ledger.recover(
        reservation_id=reservation_id,
        recovery_key="operator-recovery-replay",
        reason="repeated operator review after process exit",
    )
    assert replay.idempotent_replay is True
    assert replay.reason_code == recovered.reason_code
    assert ledger.snapshot(day="2026-09-19")["rows"][0]["reserved_usd"] == 0.0


def test_sqlite_ledger_lock_contention_is_retryable_and_recovers(tmp_path):
    path = tmp_path / "locked-budget.db"
    ledger = SQLiteTenantBudgetLedger(str(path), timeout_seconds=0.1)
    lock_connection = sqlite3.connect(str(path), timeout=0.1, isolation_level=None)
    try:
        lock_connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(TenantBudgetLedgerUnavailable) as error:
            ledger.reserve(
                tenant_hash="tenant-hash",
                day="2026-09-19",
                amount_usd=0.10,
                budget_usd=1.00,
                reservation_key="locked-request",
            )
        assert error.value.reason_code == "tenant_budget_shared_backend_unavailable"
    finally:
        lock_connection.execute("ROLLBACK")
        lock_connection.close()
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.10,
        budget_usd=1.00,
        reservation_key="locked-request-retry",
    )
    assert reservation.allowed is True


def test_sqlite_ledger_online_backup_can_be_reopened_without_raw_metadata(tmp_path):
    source_path = tmp_path / "source-budget.db"
    backup_path = tmp_path / "backup-budget.db"
    ledger = SQLiteTenantBudgetLedger(str(source_path))
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.20,
        budget_usd=1.00,
        reservation_key="backup-request",
    )
    ledger.settle(reservation_id=reservation.reservation_id, actual_cost_usd=0.15, success=True)
    receipt = ledger.backup(str(backup_path))
    assert receipt["schema"] == "axio_fusion_api.tenant_budget_ledger_backup.v1"
    assert len(receipt["sha256"]) == 64
    assert receipt["raw_path_persisted"] is False
    restored = SQLiteTenantBudgetLedger(str(backup_path))
    row = restored.snapshot(day="2026-09-19")["rows"][0]
    assert row["committed_usd"] == 0.15
    with pytest.raises(TenantBudgetLedgerInvariantError):
        ledger.backup(str(source_path))


def test_atomic_reservation_is_shared_across_concurrent_workers():
    ledger = InMemoryTenantBudgetLedger()
    barrier = threading.Barrier(8)

    def reserve(index: int):
        barrier.wait()
        return ledger.reserve(
            tenant_hash="tenant-hash",
            day="2026-09-19",
            amount_usd=0.20,
            budget_usd=1.00,
            reservation_key=f"request-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(reserve, range(8)))
    assert sum(row.allowed for row in rows) == 5
    assert ledger.snapshot(day="2026-09-19")["rows"][0]["reserved_usd"] == 1.0


def test_reserve_idempotency_key_does_not_double_charge():
    ledger = InMemoryTenantBudgetLedger()
    first = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.40,
        budget_usd=0.50,
        reservation_key="same-request",
    )
    replay = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.40,
        budget_usd=0.50,
        reservation_key="same-request",
    )
    assert replay.reservation_id == first.reservation_id
    assert replay.idempotent_replay is True
    assert replay.reserved_usd == 0.40


def test_settle_and_release_are_idempotent():
    ledger = InMemoryTenantBudgetLedger()
    settled = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.20,
        budget_usd=1.00,
        reservation_key="settle-request",
    )
    first_settlement = ledger.settle(
        reservation_id=settled.reservation_id,
        actual_cost_usd=0.15,
        success=True,
    )
    replay_settlement = ledger.settle(
        reservation_id=settled.reservation_id,
        actual_cost_usd=0.99,
        success=True,
    )
    assert first_settlement.actual_cost_usd == 0.15
    assert replay_settlement == first_settlement.__class__(
        reservation_id=first_settlement.reservation_id,
        status="settled",
        committed_usd=0.15,
        reserved_usd=0.0,
        actual_cost_usd=0.15,
        overcommit=False,
        idempotent_replay=True,
    )

    released = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.20,
        budget_usd=1.00,
        reservation_key="release-request",
    )
    first_release = ledger.release(reservation_id=released.reservation_id)
    replay_release = ledger.release(reservation_id=released.reservation_id)
    assert first_release.status == "released"
    assert replay_release.idempotent_replay is True
    assert replay_release.reserved_usd == 0.0


def test_backend_failure_is_explicit_and_recovery_preserves_state():
    ledger = InMemoryTenantBudgetLedger()
    ledger.set_available(False)
    with pytest.raises(TenantBudgetLedgerUnavailable) as error:
        ledger.reserve(
            tenant_hash="tenant-hash",
            day="2026-09-19",
            amount_usd=0.10,
            budget_usd=1.00,
            reservation_key="unavailable",
        )
    assert error.value.reason_code == "tenant_budget_shared_backend_unavailable"
    ledger.set_available(True)
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.10,
        budget_usd=1.00,
        reservation_key="unavailable",
    )
    assert reservation.allowed is True


def test_unknown_reservation_is_invariant_failure_not_silent_success():
    ledger = InMemoryTenantBudgetLedger()
    with pytest.raises(TenantBudgetLedgerInvariantError):
        ledger.settle(reservation_id="missing", actual_cost_usd=0.10, success=True)
    with pytest.raises(TenantBudgetLedgerInvariantError):
        ledger.release(reservation_id="missing")


def test_settlement_records_unexpected_overcommit_for_audit():
    ledger = InMemoryTenantBudgetLedger()
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.20,
        budget_usd=0.20,
        reservation_key="overcommit",
    )
    result = ledger.settle(
        reservation_id=reservation.reservation_id,
        actual_cost_usd=0.25,
        success=True,
    )
    assert result.overcommit is True
    assert result.committed_usd == 0.25
    assert result.reserved_usd == 0.0


def test_snapshot_is_hash_only_and_day_scoped():
    ledger = InMemoryTenantBudgetLedger()
    ledger.reserve(
        tenant_hash="sha256:tenant-a",
        day="2026-09-19",
        amount_usd=0.10,
        budget_usd=1.00,
        reservation_key="day-a",
    )
    ledger.reserve(
        tenant_hash="sha256:tenant-b",
        day="2026-09-20",
        amount_usd=0.20,
        budget_usd=1.00,
        reservation_key="day-b",
    )
    snapshot = ledger.snapshot(day="2026-09-19")
    assert snapshot["tenant_count"] == 1
    assert len(snapshot["rows"]) == 1
    assert snapshot["rows"][0]["tenant_sha256"] == "sha256:tenant-a"
    assert snapshot["raw_tenant_keys_persisted"] is False
    assert snapshot["raw_api_keys_persisted"] is False
    assert snapshot["secrets_persisted"] is False


def test_fault_injection_does_not_consume_active_reservation():
    ledger = InMemoryTenantBudgetLedger()
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.20,
        budget_usd=1.00,
        reservation_key="retry-settle",
    )
    ledger.fail_next("settle")
    with pytest.raises(TenantBudgetLedgerUnavailable):
        ledger.settle(
            reservation_id=reservation.reservation_id,
            actual_cost_usd=0.20,
            success=True,
        )
    result = ledger.settle(
        reservation_id=reservation.reservation_id,
        actual_cost_usd=0.20,
        success=True,
    )
    assert result.status == "settled"
    assert result.committed_usd == 0.20
