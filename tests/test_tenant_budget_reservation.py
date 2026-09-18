import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from axio_fusion_api.server import (
    _add_image_composer_cost,
    _estimate_image_composer_cost,
    _estimate_request_cost,
    _tenant_budget_admission_response,
)
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


def test_shared_budget_scope_fails_closed_without_backend(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_TENANT_DAILY_BUDGET_USD", "1.00")
    monkeypatch.setenv("AXIO_FUSION_TENANT_BUDGET_SCOPE", "shared_required")
    state = runtime_state()
    lease, admission = state.reserve_budget("shared-tenant", 0.10, now=1000.0)
    assert lease.allowed is False
    assert admission["allowed"] is False
    assert admission["scope"] == "shared_required"
    assert admission["scope_ready"] is False
    assert admission["reason_code"] == "tenant_budget_shared_backend_required"
    snapshot = state.snapshot(now=1000.0)
    assert snapshot["tenant_budget_scope"] == "shared_required"
    assert snapshot["tenant_budget_scope_ready"] is False
    assert snapshot["budget_reservation_tenant_count"] == 0


def test_shared_budget_scope_has_stable_service_unavailable_error():
    status, headers, body = _tenant_budget_admission_response(
        {
            "allowed": False,
            "reason_code": "tenant_budget_shared_backend_required",
            "scope": "shared_required",
            "scope_ready": False,
        }
    )
    assert status == 503
    assert "Retry-After" not in headers
    assert b"tenant_budget_shared_backend_required" in body


def test_request_budget_reservation_covers_bounded_optional_fallbacks():
    request = object()
    route_plan = {
        "budget": {"max_cost_usd": 0.02},
        "fusion_admission": {
            "initial_fusion_resource_admission": {
                "cost": {
                    "known": True,
                    "estimated_total_cost_usd": 0.004,
                    "execution": {"pricing_known": True},
                }
            }
        },
    }
    engine = SimpleNamespace(
        complete=lambda _request, live=False: SimpleNamespace(route_plan=route_plan)
    )
    assert _estimate_request_cost(engine, request) == 0.02


def test_request_budget_reservation_keeps_larger_initial_estimate():
    request = object()
    route_plan = {
        "budget": {"max_cost_usd": 0.02},
        "fusion_admission": {
            "initial_fusion_resource_admission": {
                "cost": {
                    "known": True,
                    "estimated_total_cost_usd": 0.04,
                    "execution": {"pricing_known": True},
                }
            }
        },
    }
    engine = SimpleNamespace(
        complete=lambda _request, live=False: SimpleNamespace(route_plan=route_plan)
    )
    assert _estimate_request_cost(engine, request) == 0.04


def test_image_budget_estimate_can_include_optional_text_composer_cap():
    engine = SimpleNamespace(
        profiles=[SimpleNamespace(enabled=True, text_model_eligible=True)],
        complete=lambda _request, live=False: SimpleNamespace(
            route_plan={
                "budget": {"max_cost_usd": 0.001},
                "fusion_admission": {
                    "initial_fusion_resource_admission": {
                        "cost": {
                            "known": True,
                            "estimated_total_cost_usd": 0.0004,
                            "execution": {"pricing_known": True},
                        }
                    }
                },
            }
        ),
    )
    composer_cost = _estimate_image_composer_cost(engine)
    assert composer_cost == 0.001
    assert _add_image_composer_cost(0.03, composer_cost) == 0.031
    assert _add_image_composer_cost(0.03, None) is None
