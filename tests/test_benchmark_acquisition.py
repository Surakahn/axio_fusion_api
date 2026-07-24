from __future__ import annotations

import csv
import hashlib
import io
import json
import stat
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from axio_fusion_api import benchmark_acquisition as acquisition
from axio_fusion_api.benchmark_acquisition import (
    BenchmarkAcquisitionError,
    acquire_gpqa_diamond,
)
from axio_fusion_api.cli import build_parser, main
from axio_fusion_api.evaluation import materialize_benchmark_datasets


class _Response:
    def __init__(
        self,
        payload: bytes,
        *,
        url: str = "https://huggingface.co/datasets/Idavidrein/gpqa/resolve/pinned/gpqa_diamond.csv",
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._body = io.BytesIO(payload)
        self._url = url
        self.status = status
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback


def _synthetic_gpqa_csv(row_count: int = 3) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "Question",
            "Correct Answer",
            "Incorrect Answer 1",
            "Incorrect Answer 2",
            "Incorrect Answer 3",
            "High-level domain",
        ],
    )
    writer.writeheader()
    for index in range(row_count):
        writer.writerow(
            {
                "Question": f"Synthetic question {index}",
                "Correct Answer": f"Synthetic correct {index}",
                "Incorrect Answer 1": f"Synthetic distractor A {index}",
                "Incorrect Answer 2": f"Synthetic distractor B {index}",
                "Incorrect Answer 3": f"Synthetic distractor C {index}",
                "High-level domain": "synthetic",
            }
        )
    return output.getvalue().encode("utf-8")


def _git_blob_sha1(payload: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(payload)}\0".encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


def _patch_artifact_contract(monkeypatch: pytest.MonkeyPatch, payload: bytes, *, rows: int) -> None:
    monkeypatch.setattr(acquisition, "GPQA_EXPECTED_BYTES", len(payload))
    monkeypatch.setattr(acquisition, "GPQA_EXPECTED_GIT_BLOB_SHA1", _git_blob_sha1(payload))
    monkeypatch.setattr(acquisition, "GPQA_EXPECTED_ROWS", rows)


def _write_download_manifest(path: Path, benchmark_root: Path) -> dict:
    suites = [
        {
            "suite_id": "gpqa_diamond",
            "category": "science_knowledge",
            "status": "blocked_gated",
            "evaluation_ready": False,
            "official_source": acquisition.GPQA_OFFICIAL_SOURCE,
            "local_paths": [str(benchmark_root / "raw/gpqa")],
            "files": [],
            "file_count": 0,
            "total_bytes": 0,
            "total_rows_if_countable": 0,
        }
    ]
    suites.extend(
        {
            "suite_id": f"synthetic_downloaded_{index:02d}",
            "status": "downloaded",
            "evaluation_ready": True,
            "files": [],
        }
        for index in range(20)
    )
    manifest = {
        "schema": "axio_fusion_benchmarks.download_manifest.v4",
        "benchmark_root": str(benchmark_root),
        "suite_count": 21,
        "downloaded_suite_count": 20,
        "blocked_gated_suite_count": 1,
        "blocked_suites": ["gpqa_diamond"],
        "suites": suites,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    benchmark_root = tmp_path / "benchmarks"
    destination = benchmark_root / acquisition.GPQA_RELATIVE_PATH
    manifest_path = benchmark_root / "manifests/downloads.json"
    _write_download_manifest(manifest_path, benchmark_root)
    return benchmark_root, destination, manifest_path


def test_gpqa_acquisition_commits_validated_artifact_and_hash_safe_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _synthetic_gpqa_csv(3)
    _patch_artifact_contract(monkeypatch, payload, rows=3)
    _, destination, manifest_path = _paths(tmp_path)
    secret = "hf_test_process_only_secret"
    requests: list[urllib.request.Request] = []

    def open_url(request, *, timeout):
        assert timeout == 12.0
        requests.append(request)
        return _Response(
            payload,
            headers={"Content-Length": str(len(payload)), "Content-Encoding": "identity"},
        )

    receipt = acquire_gpqa_diamond(
        accept_no_example_leakage_terms=True,
        destination=destination,
        download_manifest_path=manifest_path,
        timeout_seconds=12.0,
        secret_resolver=lambda name: secret if name == "HF_TOKEN" else None,
        _open_url=open_url,
    )

    assert receipt["status"] == "downloaded"
    assert receipt["network_download_performed"] is True
    assert receipt["artifact"]["bytes"] == len(payload)
    assert receipt["artifact"]["row_count"] == 3
    assert destination.read_bytes() == payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert len(requests) == 1
    assert requests[0].get_header("Authorization") == f"Bearer {secret}"
    assert secret not in requests[0].full_url

    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    gpqa = next(row for row in persisted["suites"] if row["suite_id"] == "gpqa_diamond")
    assert gpqa["status"] == "downloaded"
    assert gpqa["evaluation_ready"] is True
    assert gpqa["source_revision"] == acquisition.GPQA_REVISION
    assert gpqa["files"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert gpqa["files"][0]["git_blob_sha1"] == _git_blob_sha1(payload)
    assert gpqa["authorization_receipt"]["terms_contract_sha256"] == acquisition.GPQA_TERMS_CONTRACT_SHA256
    assert persisted["downloaded_suite_count"] == 21
    assert persisted["blocked_gated_suite_count"] == 0
    assert persisted["blocked_suites"] == []

    public_receipt = json.dumps(receipt, ensure_ascii=False)
    assert secret not in public_receipt
    assert "Synthetic question" not in public_receipt
    assert "https://" not in public_receipt
    assert secret not in manifest_path.read_text(encoding="utf-8")
    assert not list(destination.parent.glob(".gpqa_diamond.*.tmp"))
    assert not list(manifest_path.parent.glob(f".{manifest_path.name}.*.tmp"))

    repeated = acquire_gpqa_diamond(
        accept_no_example_leakage_terms=True,
        destination=destination,
        download_manifest_path=manifest_path,
        secret_resolver=lambda name: secret if name == "HF_TOKEN" else None,
        _open_url=lambda *args, **kwargs: pytest.fail("verified rerun must not use network"),
    )
    assert repeated["status"] == "already_downloaded_verified"
    assert repeated["network_download_performed"] is False
    assert repeated["download_manifest"]["updated"] is False

    monkeypatch.setenv("HF_TOKEN", secret)
    environment_replay = acquire_gpqa_diamond(
        accept_no_example_leakage_terms=True,
        destination=destination,
        download_manifest_path=manifest_path,
        _open_url=lambda *args, **kwargs: pytest.fail("verified environment replay must not use network"),
    )
    assert environment_replay["status"] == "already_downloaded_verified"
    assert environment_replay["credential_source"] == "process_environment"


def test_gpqa_acquisition_requires_explicit_terms_before_secret_or_network(tmp_path: Path) -> None:
    called = {"secret": False, "network": False}

    def secret_resolver(name: str) -> str:
        del name
        called["secret"] = True
        return "hf_should_not_be_read"

    def open_url(*args, **kwargs):
        del args, kwargs
        called["network"] = True
        raise AssertionError("network must not be used")

    with pytest.raises(BenchmarkAcquisitionError) as raised:
        acquire_gpqa_diamond(
            accept_no_example_leakage_terms=False,
            destination=tmp_path / "unused.csv",
            download_manifest_path=tmp_path / "unused.json",
            secret_resolver=secret_resolver,
            _open_url=open_url,
        )

    assert raised.value.reason_code == "terms_acceptance_required"
    assert raised.value.safe_receipt()["terms_explicitly_accepted"] is False
    assert called == {"secret": False, "network": False}


def test_gpqa_acquisition_requires_process_local_credential_before_manifest_access(
    tmp_path: Path,
) -> None:
    with pytest.raises(BenchmarkAcquisitionError) as raised:
        acquire_gpqa_diamond(
            accept_no_example_leakage_terms=True,
            destination=tmp_path / "unused.csv",
            download_manifest_path=tmp_path / "unused.json",
            secret_resolver=lambda name: None,
            _open_url=lambda *args, **kwargs: pytest.fail("network must not be used"),
        )
    assert raised.value.reason_code == "credential_missing"
    assert raised.value.safe_receipt()["credential_value_persisted"] is False


def test_gpqa_acquisition_sanitizes_authorization_failure_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _synthetic_gpqa_csv(1)
    _patch_artifact_contract(monkeypatch, payload, rows=1)
    _, destination, manifest_path = _paths(tmp_path)
    secret = "hf_sensitive_test_token"

    def rejected(request, *, timeout):
        del request, timeout
        raise urllib.error.HTTPError(
            f"https://huggingface.co/private?token={secret}",
            403,
            "forbidden",
            {},
            io.BytesIO(f"Synthetic question and {secret}".encode()),
        )

    with pytest.raises(BenchmarkAcquisitionError) as raised:
        acquire_gpqa_diamond(
            accept_no_example_leakage_terms=True,
            destination=destination,
            download_manifest_path=manifest_path,
            secret_resolver=lambda name: secret,
            _open_url=rejected,
        )

    receipt = raised.value.safe_receipt()
    serialized = json.dumps(receipt)
    assert raised.value.reason_code == "authorization_rejected"
    assert receipt["http_status"] == 403
    assert secret not in str(raised.value)
    assert secret not in serialized
    assert "Synthetic question" not in serialized
    assert not destination.exists()
    assert not list(destination.parent.glob(".gpqa_diamond.*.tmp"))
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["downloaded_suite_count"] == 20
    assert persisted["blocked_suites"] == ["gpqa_diamond"]


def test_gpqa_acquisition_rejects_invalid_csv_without_mutating_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"Question,Correct Answer\nSynthetic question,Synthetic answer\n"
    _patch_artifact_contract(monkeypatch, payload, rows=1)
    _, destination, manifest_path = _paths(tmp_path)
    before = manifest_path.read_bytes()

    with pytest.raises(BenchmarkAcquisitionError) as raised:
        acquire_gpqa_diamond(
            accept_no_example_leakage_terms=True,
            destination=destination,
            download_manifest_path=manifest_path,
            secret_resolver=lambda name: "hf_synthetic_secret",
            _open_url=lambda request, timeout: _Response(payload),
        )

    assert raised.value.reason_code == "csv_schema_missing_required_fields"
    assert manifest_path.read_bytes() == before
    assert not destination.exists()
    assert not list(destination.parent.glob(".gpqa_diamond.*.tmp"))


def test_gpqa_acquisition_rolls_back_artifact_when_manifest_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _synthetic_gpqa_csv(3)
    _patch_artifact_contract(monkeypatch, payload, rows=3)
    _, destination, manifest_path = _paths(tmp_path)
    before = manifest_path.read_bytes()
    original_replace = acquisition.os.replace

    def fail_manifest_replace(source, target):
        if Path(target) == manifest_path:
            raise OSError("synthetic manifest commit failure")
        return original_replace(source, target)

    monkeypatch.setattr(acquisition.os, "replace", fail_manifest_replace)
    with pytest.raises(BenchmarkAcquisitionError) as raised:
        acquire_gpqa_diamond(
            accept_no_example_leakage_terms=True,
            destination=destination,
            download_manifest_path=manifest_path,
            secret_resolver=lambda name: "hf_synthetic_secret",
            _open_url=lambda request, timeout: _Response(payload),
        )

    assert raised.value.reason_code == "download_manifest_commit_failed"
    assert not destination.exists()
    assert manifest_path.read_bytes() == before
    assert not list(destination.parent.glob(".gpqa_diamond.*.tmp"))
    assert not list(manifest_path.parent.glob(f".{manifest_path.name}.*.tmp"))


def test_gpqa_acquisition_stops_stream_larger_than_pinned_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _synthetic_gpqa_csv(2)
    monkeypatch.setattr(acquisition, "GPQA_EXPECTED_BYTES", len(payload) - 1)
    monkeypatch.setattr(acquisition, "GPQA_EXPECTED_ROWS", 2)
    _, destination, manifest_path = _paths(tmp_path)

    with pytest.raises(BenchmarkAcquisitionError) as raised:
        acquire_gpqa_diamond(
            accept_no_example_leakage_terms=True,
            destination=destination,
            download_manifest_path=manifest_path,
            secret_resolver=lambda name: "hf_synthetic_secret",
            _open_url=lambda request, timeout: _Response(payload),
        )

    assert raised.value.reason_code == "artifact_size_exceeded"
    assert not destination.exists()
    assert not list(destination.parent.glob(".gpqa_diamond.*.tmp"))


def test_gpqa_materialization_rechecks_authorized_artifact_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _synthetic_gpqa_csv(3)
    _patch_artifact_contract(monkeypatch, payload, rows=3)
    benchmark_root, destination, manifest_path = _paths(tmp_path)
    acquire_gpqa_diamond(
        accept_no_example_leakage_terms=True,
        destination=destination,
        download_manifest_path=manifest_path,
        secret_resolver=lambda name: "hf_synthetic_secret",
        _open_url=lambda request, timeout: _Response(payload),
    )
    tampered = bytearray(destination.read_bytes())
    tampered[-3] = ord("X") if tampered[-3] != ord("X") else ord("Y")
    destination.write_bytes(bytes(tampered))
    gpqa_row = next(
        row
        for row in json.loads(manifest_path.read_text(encoding="utf-8"))["suites"]
        if row["suite_id"] == "gpqa_diamond"
    )

    integrity = acquisition.audit_gpqa_authorized_artifact(
        artifact_path=destination,
        manifest_row=gpqa_row,
    )
    materialization = materialize_benchmark_datasets(
        raw_root=benchmark_root / "raw",
        output_dir=benchmark_root / "standardized",
        download_manifest_path=manifest_path,
        suite_ids=["gpqa_diamond"],
        min_cases_per_suite=3,
    )

    assert integrity["valid"] is False
    assert integrity["reason_codes"] == ["existing_artifact_blob_mismatch"]
    assert materialization["blocked_suite_count"] == 1
    row = materialization["suite_rows"][0]
    assert row["status"] == "blocked_gated"
    assert "gpqa_authorized_artifact_integrity_required" in row["reason_codes"]
    assert "gpqa_integrity_existing_artifact_blob_mismatch" in row["reason_codes"]
    assert not (benchmark_root / "standardized/gpqa_diamond.jsonl").exists()


def test_gpqa_redirect_policy_removes_authorization_off_origin_and_blocks_unknown_host() -> None:
    handler = acquisition._TrustedHuggingFaceRedirectHandler()
    request = urllib.request.Request(
        "https://huggingface.co/datasets/Idavidrein/gpqa/resolve/revision/gpqa_diamond.csv",
        headers={"Authorization": "Bearer hf_process_secret"},
    )

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://cdn-lfs.huggingface.co/signed-artifact",
    )
    assert redirected is not None
    assert redirected.get_header("Authorization") is None

    with pytest.raises(BenchmarkAcquisitionError) as raised:
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://untrusted.example/gpqa.csv",
        )
    assert raised.value.reason_code == "redirect_target_not_allowed"

    with pytest.raises(BenchmarkAcquisitionError):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://huggingface.co:8443/private-artifact",
        )


def test_gpqa_cli_has_no_token_argument_and_returns_safe_terms_failure(capsys) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["benchmark-acquire-gpqa-diamond", "--token", "hf_forbidden"])

    exit_code = main(["benchmark-acquire-gpqa-diamond"])
    receipt = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert receipt["reason_code"] == "terms_acceptance_required"
    assert receipt["secrets_persisted"] is False


def test_gpqa_production_pin_matches_audited_official_revision_metadata() -> None:
    assert acquisition.GPQA_DATASET_ID == "Idavidrein/gpqa"
    assert acquisition.GPQA_REVISION == "633f5ee89ab8ad4522a9f850766b73f62147ffdd"
    assert acquisition.GPQA_EXPECTED_BYTES == 1_373_492
    assert acquisition.GPQA_EXPECTED_GIT_BLOB_SHA1 == "7589e3e467d69a1dceb126a60c4108d6d4f1d166"
    assert acquisition.GPQA_EXPECTED_ROWS == 198
