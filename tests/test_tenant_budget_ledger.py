from concurrent.futures import ThreadPoolExecutor
import json
import os
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from axio_fusion_api.cli import main as fusion_cli_main
from axio_fusion_api.tenant_budget_ledger import (
    LedgerFencingClaim,
    InMemoryTenantBudgetLedger,
    InMemoryFencedTenantBudgetLedger,
    SQLiteTenantBudgetLedger,
    TenantBudgetLedgerFencingStale,
    TenantBudgetLedgerInvariantError,
    TenantBudgetLedgerStorageUnavailable,
    TenantBudgetLedgerUnavailable,
    audit_fenced_ledger_backend,
)


class _ReferenceFencingAuthority:
    """仅用于验证跨主机契约的单调 epoch 与旧 claim 拒绝语义。"""

    def __init__(self):
        self._epoch = 0

    def claim(self, owner_hash):
        self._epoch += 1
        return LedgerFencingClaim(owner_hash=owner_hash, epoch=self._epoch, token=f"token-{self._epoch}")

    def assert_current(self, claim):
        if claim.epoch != self._epoch:
            raise TenantBudgetLedgerFencingStale()


class _CompleteFencedBackend:
    fencing_backend_name = "test_consensus_backend"

    def claim_fencing_epoch(self):
        return None

    def reserve_fenced(self):
        return None

    def settle_fenced(self):
        return None

    def release_fenced(self):
        return None

    def recover_fenced(self):
        return None


def test_fenced_backend_audit_is_safe_and_admits_complete_contract():
    receipt = audit_fenced_ledger_backend(_CompleteFencedBackend())
    assert receipt["schema"] == "axio_fusion_api.fenced_ledger_backend_audit.v1"
    assert receipt["cross_host_fencing_admitted"] is True
    assert receipt["reason_codes"] == []
    assert receipt["raw_backend_identity_persisted"] is False


def test_fenced_backend_audit_rejects_sqlite_and_partial_contract(tmp_path):
    receipt = audit_fenced_ledger_backend(SQLiteTenantBudgetLedger(str(tmp_path / "ledger.db")))
    assert receipt["cross_host_fencing_admitted"] is False
    assert "sqlite_backend_not_cross_host_fenced" in receipt["reason_codes"]
    assert "fencing_backend_name_missing" in receipt["reason_codes"]
    assert "fenced_operation_missing" in receipt["reason_codes"]


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


def test_fencing_claim_is_monotonic_and_safe_receipt_redacts_token():
    owner_hash = "a" * 64
    authority = _ReferenceFencingAuthority()
    first = authority.claim(owner_hash)
    second = authority.claim(owner_hash)
    assert first.epoch == 1
    assert second.epoch == 2
    receipt = first.safe_receipt()
    serialized = json.dumps(receipt, sort_keys=True)
    assert receipt["schema"] == "axio_fusion_api.tenant_budget_fencing_claim.v1"
    assert receipt["token_sha256"] == first.token_sha256
    assert "token-1" not in serialized
    assert receipt["raw_token_persisted"] is False
    with pytest.raises(TenantBudgetLedgerFencingStale) as error:
        authority.assert_current(first)
    assert error.value.reason_code == "tenant_budget_fencing_stale"
    assert error.value.retryable is True
    authority.assert_current(second)


def test_fencing_claim_rejects_non_hash_owner_and_non_positive_epoch():
    with pytest.raises(TenantBudgetLedgerInvariantError):
        LedgerFencingClaim(owner_hash="raw-owner", epoch=1, token="token")
    with pytest.raises(TenantBudgetLedgerInvariantError):
        LedgerFencingClaim(owner_hash="b" * 64, epoch=0, token="token")


def test_in_memory_fenced_ledger_rejects_stale_claim_and_preserves_idempotency():
    ledger = InMemoryFencedTenantBudgetLedger()
    owner_hash = "c" * 64
    stale = ledger.claim_fencing_epoch(owner_hash=owner_hash)
    current = ledger.claim_fencing_epoch(owner_hash=owner_hash)
    with pytest.raises(TenantBudgetLedgerFencingStale):
        ledger.reserve_fenced(
            fencing_claim=stale,
            tenant_hash="tenant-hash",
            day="2026-09-20",
            amount_usd=0.10,
            budget_usd=1.00,
            reservation_key="stale-request",
        )
    reservation = ledger.reserve_fenced(
        fencing_claim=current,
        tenant_hash="tenant-hash",
        day="2026-09-20",
        amount_usd=0.10,
        budget_usd=1.00,
        reservation_key="same-request",
    )
    replay = ledger.reserve_fenced(
        fencing_claim=current,
        tenant_hash="tenant-hash",
        day="2026-09-20",
        amount_usd=0.10,
        budget_usd=1.00,
        reservation_key="same-request",
    )
    assert replay.reservation_id == reservation.reservation_id
    assert replay.idempotent_replay is True


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
    integrity = ledger.integrity_check()
    assert integrity["valid"] is True
    assert integrity["sqlite_integrity_check"] == "ok"
    assert integrity["raw_path_persisted"] is False
    restored = SQLiteTenantBudgetLedger(str(backup_path))
    assert restored.integrity_check()["valid"] is True
    row = restored.snapshot(day="2026-09-19")["rows"][0]
    assert row["committed_usd"] == 0.15
    with pytest.raises(TenantBudgetLedgerInvariantError):
        ledger.backup(str(source_path))


def test_sqlite_ledger_backup_publishes_atomically_and_preserves_old_copy_on_replace_failure(
    tmp_path, monkeypatch
):
    source_path = tmp_path / "atomic-source-budget.db"
    backup_path = tmp_path / "atomic-backup-budget.db"
    ledger = SQLiteTenantBudgetLedger(str(source_path))
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.20,
        budget_usd=1.00,
        reservation_key="atomic-backup-request",
    )
    ledger.settle(reservation_id=reservation.reservation_id, actual_cost_usd=0.15, success=True)
    first_receipt = ledger.backup(str(backup_path))
    assert first_receipt["storage_ready"] is True
    assert not list(tmp_path.glob(f"{backup_path.name}.tmp-*"))

    backup_path.write_bytes(b"known-good-old-backup")
    original_replace = os.replace

    def fail_replace(source, destination):
        assert str(destination) == str(backup_path)
        raise OSError("database or disk is full")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(TenantBudgetLedgerStorageUnavailable) as error:
        ledger.backup(str(backup_path))
    assert error.value.reason_code == "tenant_budget_shared_backend_storage_unavailable"
    assert backup_path.read_bytes() == b"known-good-old-backup"
    assert not list(tmp_path.glob(f"{backup_path.name}.tmp-*"))

    monkeypatch.setattr(os, "replace", original_replace)
    final_receipt = ledger.backup(str(backup_path))
    assert final_receipt["schema"] == "axio_fusion_api.tenant_budget_ledger_backup.v1"
    assert final_receipt["storage_ready"] is True
    assert SQLiteTenantBudgetLedger(str(backup_path)).integrity_check()["valid"] is True


def test_sqlite_ledger_integrity_check_fails_closed_on_incomplete_schema(tmp_path):
    path = tmp_path / "incomplete-budget.db"
    ledger = SQLiteTenantBudgetLedger(str(path))
    with sqlite3.connect(str(path)) as connection:
        connection.execute("ALTER TABLE reservations RENAME COLUMN amount_usd TO amount_broken")
    with pytest.raises(TenantBudgetLedgerInvariantError) as error:
        ledger.integrity_check()
    assert error.value.reason_code == "tenant_budget_shared_backend_invariant_failed"
    with pytest.raises(TenantBudgetLedgerInvariantError):
        ledger.backup(str(tmp_path / "should-not-backup.db"))


def test_sqlite_ledger_integrity_check_classifies_malformed_file(tmp_path):
    path = tmp_path / "malformed-budget.db"
    ledger = SQLiteTenantBudgetLedger(str(path))
    path.write_bytes(b"not-a-sqlite-database")
    for suffix in ("-wal", "-shm"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            sidecar.unlink()
    with pytest.raises(TenantBudgetLedgerInvariantError) as error:
        ledger.integrity_check()
    assert error.value.reason_code == "tenant_budget_shared_backend_invariant_failed"


def test_sqlite_ledger_storage_status_is_safe_and_detects_read_only_volume(tmp_path, monkeypatch):
    path = tmp_path / "storage-budget.db"
    ledger = SQLiteTenantBudgetLedger(str(path))
    status = ledger.storage_status()
    assert status["ready"] is True
    assert status["writable"] is True
    assert status["free_bytes"] > 0
    assert status["raw_path_persisted"] is False
    read_only_flags = int(getattr(os, "ST_RDONLY", 1))
    monkeypatch.setattr(
        os,
        "statvfs",
        lambda _: SimpleNamespace(f_bavail=0, f_frsize=4096, f_flag=read_only_flags),
    )
    unavailable = ledger.storage_status()
    assert unavailable["ready"] is False
    assert unavailable["read_only"] is True
    with pytest.raises(TenantBudgetLedgerStorageUnavailable) as error:
        ledger.backup(str(tmp_path / "storage-backup.db"))
    assert error.value.reason_code == "tenant_budget_shared_backend_storage_unavailable"


def test_tenant_budget_ledger_diagnostic_cli_emits_safe_backup_receipt(tmp_path):
    source = tmp_path / "operator-budget.db"
    backup = tmp_path / "operator-budget.backup.db"
    output = tmp_path / "diagnostic.json"
    ledger = SQLiteTenantBudgetLedger(str(source))
    reservation = ledger.reserve(
        tenant_hash="tenant-hash",
        day="2026-09-19",
        amount_usd=0.10,
        budget_usd=1.00,
        reservation_key="operator-diagnostic",
    )
    ledger.settle(reservation_id=reservation.reservation_id, actual_cost_usd=0.08, success=True)
    result = fusion_cli_main(
        [
            "tenant-budget-ledger-diagnostic",
            "--path",
            str(source),
            "--backup",
            str(backup),
            "--required-free-bytes",
            "1",
            "--output",
            str(output),
        ]
    )
    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["ready"] is True
    assert payload["reason_code"] == ""
    assert payload["retryable"] is False
    assert payload["integrity"]["valid"] is True
    assert payload["storage"]["required_bytes"] == 1
    assert payload["backup"]["storage_ready"] is True
    assert str(source) not in serialized
    assert str(backup) not in serialized
    assert payload["secrets_persisted"] is False


def test_tenant_budget_ledger_diagnostic_cli_does_not_create_missing_source(tmp_path):
    source = tmp_path / "missing-budget.db"
    output = tmp_path / "missing-diagnostic.json"
    result = fusion_cli_main(
        [
            "tenant-budget-ledger-diagnostic",
            "--path",
            str(source),
            "--output",
            str(output),
        ]
    )
    assert result == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ready"] is False
    assert payload["reason_code"] == "tenant_budget_shared_backend_invariant_failed"
    assert payload["retryable"] is False
    assert not source.exists()
    assert str(source) not in json.dumps(payload, sort_keys=True)


def test_tenant_budget_ledger_diagnostic_cli_reports_storage_gate(tmp_path, monkeypatch):
    source = tmp_path / "storage-gated-budget.db"
    output = tmp_path / "storage-gated-diagnostic.json"
    SQLiteTenantBudgetLedger(str(source))
    monkeypatch.setattr(
        os,
        "statvfs",
        lambda _: SimpleNamespace(f_bavail=0, f_frsize=4096, f_flag=0),
    )
    result = fusion_cli_main(
        [
            "tenant-budget-ledger-diagnostic",
            "--path",
            str(source),
            "--required-free-bytes",
            "1",
            "--output",
            str(output),
        ]
    )
    assert result == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ready"] is False
    assert payload["reason_code"] == "tenant_budget_shared_backend_storage_unavailable"
    assert payload["retryable"] is True
    assert payload["storage"]["free_bytes"] == 0


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
