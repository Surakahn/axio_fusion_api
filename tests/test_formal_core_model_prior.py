from axio_fusion_api.registry import CAPABILITY_AXES, _apply_model_name_capability_priors


def _capability_average(model: str) -> float:
    caps = {axis: 0.35 for axis in CAPABILITY_AXES}
    _apply_model_name_capability_priors(caps, model)
    return sum(caps.values()) / len(caps)


def test_formal_core_prior_preserves_operator_model_hierarchy():
    fable = _capability_average("claude-fable-5")
    sol = _capability_average("gpt-5.6-sol")
    opus = _capability_average("claude-opus-5")
    terra = _capability_average("gpt-5.6-terra")
    sonnet = _capability_average("claude-sonnet-5")
    luna = _capability_average("gpt-5.6-luna")

    assert abs(sol - fable) < 0.02
    assert opus > terra
    assert sonnet > luna
    assert luna < terra < sol
