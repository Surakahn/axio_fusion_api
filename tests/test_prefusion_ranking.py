from __future__ import annotations

from axio_fusion_api.prefusion_ranking import (
    PREFUSION_OPERATIONAL_EVIDENCE_SCHEMA,
    operational_evidence_confidence,
    operational_rank_rows,
)


def test_operational_evidence_confidence_is_conservative_and_hash_safe():
    receipt = operational_evidence_confidence(
        research_confidence=0.9,
        stream_reliability=0.6,
        available_replica_count=1,
        physical_replica_count=2,
    )

    assert receipt["schema"] == PREFUSION_OPERATIONAL_EVIDENCE_SCHEMA
    assert receipt["research_confidence"] == 0.9
    assert receipt["stream_reliability"] == 0.6
    assert receipt["replica_coverage"] == 0.5
    assert receipt["operational_confidence"] == 0.5
    assert receipt["operational_uncertainty"] == 0.5
    assert receipt["statistical_confidence_interval"] is False
    assert receipt["benchmark_quality_evidence"] is False


def test_operational_evidence_confidence_fail_closed_for_invalid_replica_counts():
    receipt = operational_evidence_confidence(
        research_confidence=2.0,
        stream_reliability=-1.0,
        available_replica_count="invalid",
        physical_replica_count=0,
    )

    assert receipt["replica_coverage"] == 0.0
    assert receipt["operational_confidence"] == 0.0
    assert receipt["operational_uncertainty"] == 1.0


def test_operational_rank_rows_uses_evidence_confidence_as_stable_tiebreak():
    rows = [
        {
            "canonical_identity_sha256": "a",
            "operational_score": 0.8,
            "research_quality_score": 0.8,
            "stream_reliability_score": 1.0,
            "fastest_observed_latency_ms": 100,
            "operational_evidence_confidence": {
                "operational_confidence": 0.2,
            },
        },
        {
            "canonical_identity_sha256": "z",
            "operational_score": 0.8,
            "research_quality_score": 0.8,
            "stream_reliability_score": 1.0,
            "fastest_observed_latency_ms": 100,
            "operational_evidence_confidence": {
                "operational_confidence": 0.9,
            },
        },
    ]

    ranked = operational_rank_rows(rows)

    assert [row["canonical_identity_sha256"] for row in ranked] == ["z", "a"]
    assert [row["operational_rank"] for row in ranked] == [1, 2]

