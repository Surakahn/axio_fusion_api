import json

from axio_fusion_api.server import public_deployment_contract


def test_loopback_deployment_contract_remains_compatible(monkeypatch):
    monkeypatch.delenv("AXIO_FUSION_PUBLIC_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AXIO_FUSION_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("AXIO_FUSION_API_KEYS", raising=False)
    monkeypatch.delenv("AXIO_FUSION_OPERATOR_API_KEYS", raising=False)
    monkeypatch.delenv("AXIO_FUSION_TENANT_DAILY_BUDGET_USD", raising=False)
    contract = public_deployment_contract()
    assert contract["public_mode"] is False
    assert contract["ready"] is True
    assert contract["blockers"] == []


def test_public_deployment_requires_auth_and_operator_key(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_PUBLIC_DEPLOYMENT", "true")
    monkeypatch.delenv("AXIO_FUSION_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("AXIO_FUSION_API_KEYS", raising=False)
    monkeypatch.delenv("AXIO_FUSION_OPERATOR_API_KEYS", raising=False)
    contract = public_deployment_contract()
    assert contract["ready"] is False
    assert set(contract["blockers"]) == {
        "public_deployment_requires_auth",
        "public_deployment_public_key_required",
        "public_deployment_operator_key_required",
    }
    serialized = json.dumps(contract)
    assert "public-key" not in serialized
    assert "operator-key" not in serialized


def test_public_budget_requires_shared_scope(monkeypatch):
    monkeypatch.setenv("AXIO_FUSION_PUBLIC_DEPLOYMENT", "true")
    monkeypatch.setenv("AXIO_FUSION_REQUIRE_AUTH", "true")
    monkeypatch.setenv("AXIO_FUSION_API_KEYS", "public-key")
    monkeypatch.setenv("AXIO_FUSION_OPERATOR_API_KEYS", "operator-key")
    monkeypatch.setenv("AXIO_FUSION_TENANT_DAILY_BUDGET_USD", "1.00")
    monkeypatch.setenv("AXIO_FUSION_TENANT_BUDGET_SCOPE", "process_local")
    contract = public_deployment_contract()
    assert contract["ready"] is False
    assert contract["blockers"] == ["public_deployment_shared_budget_required"]
    monkeypatch.setenv("AXIO_FUSION_TENANT_BUDGET_SCOPE", "shared_required")
    assert public_deployment_contract()["ready"] is True
