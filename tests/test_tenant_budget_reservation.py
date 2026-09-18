import threading
from concurrent.futures import ThreadPoolExecutor

from axio_fusion_api.runtime import reset_runtime_state_for_tests, runtime_state


def setup_function() -> None:
    reset_runtime_state_for_tests()


def teardown_function() -> None:
    reset_runtime_state_for_tests()


def test_known_cost_reservation_is_atomic_and_settlement_is_idempotent(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_TENANT_DAILY_BUDGET_USD", "1.00")
    state = runtime_state()
    tenant = "tenant-budget-race"
    barrier = threading.Barrier(8)

    def reserve():
        barrier.wait()
        return state.reserve_budget(tenant, 0.20, now=1000.0)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))
    admitted = [(lease, receipt) for lease, receipt in results if receipt["allowed"]]
    assert len(admitted) == 5
    assert state.check_budget(tenant, now=1000.0)["allowed"] is False
    assert state.snapshot(now=1000.0)["budget_tenants"][0]["reserved_usd"] == 1.0

    for lease, _receipt in admitted[:2]:
        lease.settle(0.20, success=True, now=1000.0)
        lease.settle(0.20, success=True, now=1000.0)
    for lease, _receipt in admitted[2:]:
        lease.settle(success=False, now=1000.0)
    budget = state.check_budget(tenant, now=1000.0)
    assert budget["spent_usd"] == 0.4
    assert budget["reserved_usd"] == 0.0
    assert budget["allowed"] is True


def test_unknown_cost_does_not_become_free_but_releases_without_spend(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_TENANT_DAILY_BUDGET_USD", "0.50")
    state = runtime_state()
    lease, receipt = state.reserve_budget("unknown-price", None, now=1000.0)
    assert receipt["allowed"] is False
    assert receipt["pricing_known"] is False
    lease.observe(float("nan"))
    lease.settle(success=False, now=1000.0)
    assert state.check_budget("unknown-price", now=1000.0)["spent_usd"] == 0.0
    assert state.snapshot(now=1000.0)["budget_tenants"] == []


def test_success_without_usage_receipt_commits_preflight_reservation(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_TENANT_DAILY_BUDGET_USD", "0.50")
    state = runtime_state()
    lease, receipt = state.reserve_budget("missing-usage", 0.25, now=1000.0)
    assert receipt["allowed"] is True
    lease.settle(success=True, now=1000.0)
    assert state.check_budget("missing-usage", now=1000.0)["spent_usd"] == 0.25
    assert state.snapshot(now=1000.0)["budget_tenants"][0]["reserved_usd"] == 0.0


def test_budget_day_rollover_prunes_reservation_and_preserves_safe_projection(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_TENANT_DAILY_BUDGET_USD", "0.50")
    state = runtime_state()
    lease, _receipt = state.reserve_budget("rollover", 0.25, now=86_399.0)
    snapshot = state.snapshot(now=86_399.0)
    assert snapshot["budget_tenants"][0]["reserved_usd"] == 0.25
    assert snapshot["raw_tenant_keys_persisted"] is False
    lease.settle(success=False)
    assert state.snapshot(now=86_400.0)["budget_tenants"] == []
