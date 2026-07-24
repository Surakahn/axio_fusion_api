"""Authorized acquisition for gated benchmark artifacts.

This module deliberately handles only sources whose access contract cannot be
represented by a generic downloader.  It never accepts an arbitrary URL or a
credential on the command line, and every public receipt is content-free and
secret-free.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .network import NetworkPolicyError, build_network_opener, provider_proxy_runtime_summary
from .schemas import sha256_text, stable_json


GPQA_DATASET_ID = "Idavidrein/gpqa"
GPQA_REVISION = "633f5ee89ab8ad4522a9f850766b73f62147ffdd"
GPQA_FILENAME = "gpqa_diamond.csv"
GPQA_EXPECTED_BYTES = 1_373_492
GPQA_EXPECTED_GIT_BLOB_SHA1 = "7589e3e467d69a1dceb126a60c4108d6d4f1d166"
GPQA_EXPECTED_ROWS = 198
GPQA_RELATIVE_PATH = "raw/gpqa/gpqa_diamond.csv"
GPQA_OFFICIAL_SOURCE = "https://huggingface.co/datasets/Idavidrein/gpqa"
GPQA_DEFAULT_DESTINATION = "/mnt/storage/axio_fusion_benchmarks/raw/gpqa/gpqa_diamond.csv"
GPQA_DEFAULT_DOWNLOAD_MANIFEST = (
    "/mnt/storage/axio_fusion_benchmarks/manifests/"
    "benchmark_download_manifest_v4_21_suites_2026-07-16.json"
)

_GPQA_REQUIRED_FIELDS = frozenset(
    {
        "Question",
        "Correct Answer",
        "Incorrect Answer 1",
        "Incorrect Answer 2",
        "Incorrect Answer 3",
    }
)
_GPQA_TERMS_CONTRACT = {
    "dataset_id": GPQA_DATASET_ID,
    "revision": GPQA_REVISION,
    "contract": "upstream_gated_terms_accepted_and_examples_will_not_be_publicly_disclosed",
}
GPQA_TERMS_CONTRACT_SHA256 = sha256_text(stable_json(_GPQA_TERMS_CONTRACT))
_TRUSTED_HUGGING_FACE_HOSTS = frozenset({"huggingface.co", "hf.co"})
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_DOWNLOAD_CHUNK_BYTES = 64 * 1024

SecretResolver = Callable[[str], Optional[str]]
UrlOpener = Callable[..., Any]


class BenchmarkAcquisitionError(RuntimeError):
    """A gated acquisition failure whose public representation is safe."""

    def __init__(
        self,
        reason_code: str,
        *,
        terms_explicitly_accepted: bool,
        credential_present: bool = False,
        http_status: int | None = None,
    ) -> None:
        self.reason_code = str(reason_code or "acquisition_failed")
        self.terms_explicitly_accepted = bool(terms_explicitly_accepted)
        self.credential_present = bool(credential_present)
        self.http_status = int(http_status) if http_status is not None else None
        super().__init__(f"benchmark_acquisition_failed:{self.reason_code}")

    def safe_receipt(self) -> dict[str, Any]:
        return {
            "schema": "axio_fusion_api.gpqa_acquisition_receipt.v1",
            "suite_id": "gpqa_diamond",
            "status": "failed",
            "reason_code": self.reason_code,
            "http_status": self.http_status,
            "source_kind": "official_huggingface_gated",
            "source_revision": GPQA_REVISION,
            "terms_explicitly_accepted": self.terms_explicitly_accepted,
            "terms_contract_sha256": GPQA_TERMS_CONTRACT_SHA256,
            "credential_present": self.credential_present,
            "credential_value_persisted": False,
            "download_url_persisted": False,
            "dataset_examples_persisted": False,
            "answer_labels_persisted": False,
            "artifact_installed_by_attempt": False,
            "download_manifest_updated_by_attempt": False,
            "secrets_persisted": False,
        }


class _TrustedHuggingFaceRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow HTTPS redirects only within Hugging Face controlled hostnames.

    Authorization is retained only for the exact original host.  Signed asset
    redirects therefore cannot receive the gated-repository bearer token.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del fp
        try:
            parsed = urllib.parse.urlsplit(str(newurl or ""))
        except ValueError as exc:
            raise BenchmarkAcquisitionError(
                "redirect_target_not_allowed",
                terms_explicitly_accepted=True,
                credential_present=True,
            ) from exc
        if not _trusted_hugging_face_url(parsed):
            raise BenchmarkAcquisitionError(
                "redirect_target_not_allowed",
                terms_explicitly_accepted=True,
                credential_present=True,
            )
        redirected = super().redirect_request(req, None, code, msg, headers, newurl)
        if redirected is None:
            return None
        original_host = (urllib.parse.urlsplit(req.full_url).hostname or "").casefold()
        redirected_host = (parsed.hostname or "").casefold()
        if redirected_host != original_host:
            _remove_request_header(redirected, "authorization")
        return redirected


def audit_gpqa_authorized_artifact(
    *,
    artifact_path: str | Path,
    manifest_row: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the gated authorization receipt and pinned local artifact.

    This audit performs no network or secret access and returns no examples,
    answers, URLs, or raw paths.  Evaluation calls it immediately before GPQA
    materialization so a stale ``status=downloaded`` flag cannot authorize a
    replaced file.
    """

    path = Path(artifact_path).expanduser()
    try:
        if path.is_symlink():
            raise _acquisition_error(
                "artifact_symlink_not_allowed",
                accepted=True,
            )
        if not path.is_file():
            raise _acquisition_error("artifact_missing", accepted=True)
        authorization = manifest_row.get("authorization_receipt")
        files = manifest_row.get("files")
        file_receipt = (
            files[0]
            if isinstance(files, list)
            and len(files) == 1
            and isinstance(files[0], Mapping)
            else {}
        )
        authorized = (
            str(manifest_row.get("status") or "") == "downloaded"
            and str(manifest_row.get("official_source") or "") == GPQA_OFFICIAL_SOURCE
            and str(manifest_row.get("source_revision") or "") == GPQA_REVISION
            and str(manifest_row.get("source_git_blob_sha1") or "")
            == GPQA_EXPECTED_GIT_BLOB_SHA1
            and isinstance(authorization, Mapping)
            and authorization.get("accepted") is True
            and str(authorization.get("terms_contract_sha256") or "")
            == GPQA_TERMS_CONTRACT_SHA256
        )
        if not authorized:
            raise _acquisition_error(
                "authorized_manifest_receipt_invalid",
                accepted=True,
            )
        if str(file_receipt.get("path") or "") != GPQA_RELATIVE_PATH:
            raise _acquisition_error(
                "artifact_manifest_path_mismatch",
                accepted=True,
            )
        artifact = _hash_existing_artifact(path)
        artifact["row_count"] = _validate_gpqa_csv(path)
        if (
            _safe_int(file_receipt.get("bytes")) != artifact["bytes"]
            or str(file_receipt.get("sha256") or "") != artifact["sha256"]
            or str(file_receipt.get("git_blob_sha1") or "")
            != artifact["git_blob_sha1"]
            or _safe_int(file_receipt.get("rows")) != artifact["row_count"]
        ):
            raise _acquisition_error(
                "artifact_manifest_identity_mismatch",
                accepted=True,
            )
    except BenchmarkAcquisitionError as exc:
        return {
            "schema": "axio_fusion_api.gpqa_artifact_integrity.v1",
            "valid": False,
            "reason_codes": [exc.reason_code],
            "source_revision": GPQA_REVISION,
            "terms_contract_sha256": GPQA_TERMS_CONTRACT_SHA256,
            "artifact_path_sha256": _path_identity_sha256(path),
            "raw_artifact_path_persisted": False,
            "dataset_examples_persisted": False,
            "answer_labels_persisted": False,
            "secrets_persisted": False,
        }
    return {
        "schema": "axio_fusion_api.gpqa_artifact_integrity.v1",
        "valid": True,
        "reason_codes": [],
        "source_revision": GPQA_REVISION,
        "terms_contract_sha256": GPQA_TERMS_CONTRACT_SHA256,
        "artifact": dict(artifact),
        "artifact_path_sha256": _path_identity_sha256(path),
        "raw_artifact_path_persisted": False,
        "dataset_examples_persisted": False,
        "answer_labels_persisted": False,
        "secrets_persisted": False,
    }


def acquire_gpqa_diamond(
    *,
    accept_no_example_leakage_terms: bool,
    destination: str | Path = GPQA_DEFAULT_DESTINATION,
    download_manifest_path: str | Path = GPQA_DEFAULT_DOWNLOAD_MANIFEST,
    timeout_seconds: float = 90.0,
    secret_resolver: SecretResolver | None = None,
    _open_url: UrlOpener | None = None,
) -> dict[str, Any]:
    """Download and register the pinned GPQA Diamond artifact.

    The explicit terms flag and a process-local Hugging Face token are both
    mandatory.  The token is never returned, logged, written to disk, placed in
    a URL, or included in an exception message.
    """

    accepted = bool(accept_no_example_leakage_terms)
    if not accepted:
        raise _acquisition_error("terms_acceptance_required", accepted=False)
    try:
        normalized_timeout = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise _acquisition_error("timeout_invalid", accepted=True) from exc
    if not 1.0 <= normalized_timeout <= 900.0:
        raise _acquisition_error("timeout_out_of_range", accepted=True)

    token, credential_source = _resolve_hugging_face_token(secret_resolver)
    if not token:
        raise _acquisition_error("credential_missing", accepted=True)

    manifest_path = Path(download_manifest_path).expanduser()
    destination_path = Path(destination).expanduser()
    manifest, gpqa_row = _load_and_validate_manifest(
        manifest_path,
        destination=destination_path,
        secret_value=token,
    )
    proxy_receipt = provider_proxy_runtime_summary()
    if _open_url is None and proxy_receipt.get("selected_transport") == "error":
        raise _acquisition_error(
            str(proxy_receipt.get("reason_code") or "proxy_unavailable"),
            accepted=True,
            credential_present=True,
        )

    if destination_path.is_symlink():
        raise _acquisition_error("destination_symlink_not_allowed", accepted=True, credential_present=True)
    if destination_path.exists():
        return _verify_existing_authorized_artifact(
            destination_path,
            manifest_path=manifest_path,
            gpqa_row=gpqa_row,
            proxy_receipt=proxy_receipt,
            credential_source=credential_source,
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        destination_path.parent.chmod(0o700)
    except OSError:
        pass

    temporary_artifact: Path | None = None
    temporary_manifest: Path | None = None
    artifact_installed = False
    try:
        temporary_artifact, artifact = _download_gpqa_to_private_temporary(
            destination_path.parent,
            token=token,
            timeout_seconds=normalized_timeout,
            open_url=_open_url,
        )
        row_count = _validate_gpqa_csv(temporary_artifact)
        artifact["row_count"] = row_count
        updated_manifest = _updated_download_manifest(
            manifest,
            artifact=artifact,
            destination=destination_path,
        )
        serialized_manifest = json.dumps(
            updated_manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        if token in serialized_manifest:
            raise _acquisition_error(
                "credential_persistence_guard_triggered",
                accepted=True,
                credential_present=True,
            )
        temporary_manifest = _stage_private_bytes(
            manifest_path.parent,
            serialized_manifest.encode("utf-8"),
            prefix=f".{manifest_path.name}.",
        )

        try:
            os.link(temporary_artifact, destination_path, follow_symlinks=False)
        except FileExistsError as exc:
            raise _acquisition_error(
                "destination_appeared_during_commit",
                accepted=True,
                credential_present=True,
            ) from exc
        artifact_installed = True
        temporary_artifact.unlink()
        temporary_artifact = None
        try:
            os.replace(temporary_manifest, manifest_path)
        except OSError as exc:
            _unlink_quietly(destination_path)
            artifact_installed = False
            raise _acquisition_error(
                "download_manifest_commit_failed",
                accepted=True,
                credential_present=True,
            ) from exc
        temporary_manifest = None
        _fsync_directory(destination_path.parent)
        _fsync_directory(manifest_path.parent)
    except BenchmarkAcquisitionError:
        raise
    except OSError as exc:
        if artifact_installed:
            _unlink_quietly(destination_path)
        raise _acquisition_error(
            "artifact_io_failed",
            accepted=True,
            credential_present=True,
        ) from exc
    finally:
        _unlink_quietly(temporary_artifact)
        _unlink_quietly(temporary_manifest)

    return _success_receipt(
        status="downloaded",
        artifact=artifact,
        manifest_path=manifest_path,
        destination=destination_path,
        proxy_receipt=proxy_receipt,
        credential_source=credential_source,
        network_download_performed=True,
    )


def _download_gpqa_to_private_temporary(
    directory: Path,
    *,
    token: str,
    timeout_seconds: float,
    open_url: UrlOpener | None,
) -> tuple[Path, dict[str, Any]]:
    url = (
        f"https://huggingface.co/datasets/{GPQA_DATASET_ID}/resolve/"
        f"{GPQA_REVISION}/{GPQA_FILENAME}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/csv,application/octet-stream;q=0.9",
            "Accept-Encoding": "identity",
            "Authorization": f"Bearer {token}",
            "User-Agent": "axio-fusion-api/0.1 gated-benchmark-acquisition",
        },
        method="GET",
    )
    temporary = _empty_private_temporary(directory, prefix=".gpqa_diamond.")
    opener = open_url or _open_hugging_face_url
    byte_count = 0
    sha256 = hashlib.sha256()
    git_blob_sha1 = _new_git_blob_sha1()
    git_blob_sha1.update(f"blob {GPQA_EXPECTED_BYTES}\0".encode("ascii"))
    try:
        try:
            response = opener(request, timeout=timeout_seconds)
        except urllib.error.HTTPError as exc:
            _discard_http_error_body(exc)
            raise _http_acquisition_error(exc.code) from exc
        except BenchmarkAcquisitionError:
            raise
        except (TimeoutError, urllib.error.URLError) as exc:
            raise _acquisition_error(
                "network_transport_failed",
                accepted=True,
                credential_present=True,
            ) from exc

        with response:
            status = _response_status(response)
            if status != 200:
                raise _http_acquisition_error(status)
            _validate_final_response_url(response)
            headers = getattr(response, "headers", {})
            encoding = str(_header_value(headers, "Content-Encoding") or "").strip().casefold()
            if encoding not in {"", "identity"}:
                raise _acquisition_error(
                    "content_encoding_not_allowed",
                    accepted=True,
                    credential_present=True,
                )
            content_length = _header_value(headers, "Content-Length")
            if content_length not in (None, ""):
                try:
                    declared_bytes = int(str(content_length).strip())
                except ValueError as exc:
                    raise _acquisition_error(
                        "content_length_invalid",
                        accepted=True,
                        credential_present=True,
                    ) from exc
                if declared_bytes != GPQA_EXPECTED_BYTES:
                    raise _acquisition_error(
                        "content_length_mismatch",
                        accepted=True,
                        credential_present=True,
                    )

            with temporary.open("wb") as handle:
                os.chmod(temporary, 0o600)
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise _acquisition_error(
                            "response_chunk_type_invalid",
                            accepted=True,
                            credential_present=True,
                        )
                    byte_count += len(chunk)
                    if byte_count > GPQA_EXPECTED_BYTES:
                        raise _acquisition_error(
                            "artifact_size_exceeded",
                            accepted=True,
                            credential_present=True,
                        )
                    handle.write(chunk)
                    sha256.update(chunk)
                    git_blob_sha1.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())
    except BenchmarkAcquisitionError:
        _unlink_quietly(temporary)
        raise
    except OSError as exc:
        _unlink_quietly(temporary)
        raise _acquisition_error(
            "download_stream_io_failed",
            accepted=True,
            credential_present=True,
        ) from exc

    if byte_count != GPQA_EXPECTED_BYTES:
        _unlink_quietly(temporary)
        raise _acquisition_error(
            "artifact_size_mismatch",
            accepted=True,
            credential_present=True,
        )
    blob_id = git_blob_sha1.hexdigest()
    if blob_id != GPQA_EXPECTED_GIT_BLOB_SHA1:
        _unlink_quietly(temporary)
        raise _acquisition_error(
            "official_blob_identity_mismatch",
            accepted=True,
            credential_present=True,
        )
    return temporary, {
        "bytes": byte_count,
        "sha256": sha256.hexdigest(),
        "git_blob_sha1": blob_id,
    }


def _validate_gpqa_csv(path: Path) -> int:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = {str(field or "").strip() for field in (reader.fieldnames or [])}
            if not _GPQA_REQUIRED_FIELDS.issubset(fields):
                raise _acquisition_error(
                    "csv_schema_missing_required_fields",
                    accepted=True,
                    credential_present=True,
                )
            row_count = 0
            for row in reader:
                if not isinstance(row, Mapping) or any(
                    not str(row.get(field) or "").strip() for field in _GPQA_REQUIRED_FIELDS
                ):
                    raise _acquisition_error(
                        "csv_row_missing_required_value",
                        accepted=True,
                        credential_present=True,
                    )
                row_count += 1
    except BenchmarkAcquisitionError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise _acquisition_error(
            "csv_validation_failed",
            accepted=True,
            credential_present=True,
        ) from exc
    if row_count != GPQA_EXPECTED_ROWS:
        raise _acquisition_error(
            "csv_row_count_mismatch",
            accepted=True,
            credential_present=True,
        )
    return row_count


def _load_and_validate_manifest(
    path: Path,
    *,
    destination: Path,
    secret_value: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if path.is_symlink():
        raise _acquisition_error("download_manifest_symlink_not_allowed", accepted=True, credential_present=True)
    try:
        if not path.is_file() or path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise _acquisition_error("download_manifest_missing_or_oversized", accepted=True, credential_present=True)
        raw = path.read_text(encoding="utf-8")
        if secret_value and secret_value in raw:
            raise _acquisition_error("download_manifest_contains_credential", accepted=True, credential_present=True)
        payload = json.loads(raw)
    except BenchmarkAcquisitionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _acquisition_error("download_manifest_invalid", accepted=True, credential_present=True) from exc
    if not isinstance(payload, Mapping) or payload.get("schema") != "axio_fusion_benchmarks.download_manifest.v4":
        raise _acquisition_error("download_manifest_schema_mismatch", accepted=True, credential_present=True)
    suites = payload.get("suites")
    if (
        not isinstance(suites, list)
        or _safe_int(payload.get("suite_count")) != 21
        or len(suites) != 21
    ):
        raise _acquisition_error("download_manifest_suite_contract_mismatch", accepted=True, credential_present=True)
    gpqa_rows = [
        row
        for row in suites
        if isinstance(row, Mapping) and str(row.get("suite_id") or "") == "gpqa_diamond"
    ]
    if len(gpqa_rows) != 1:
        raise _acquisition_error("download_manifest_gpqa_row_mismatch", accepted=True, credential_present=True)
    gpqa_row = dict(gpqa_rows[0])
    if str(gpqa_row.get("official_source") or "") != GPQA_OFFICIAL_SOURCE:
        raise _acquisition_error("download_manifest_official_source_mismatch", accepted=True, credential_present=True)
    raw_benchmark_root = str(payload.get("benchmark_root") or "").strip()
    if not raw_benchmark_root:
        raise _acquisition_error("download_manifest_benchmark_root_missing", accepted=True, credential_present=True)
    benchmark_root = Path(raw_benchmark_root).expanduser()
    expected_destination = benchmark_root / GPQA_RELATIVE_PATH
    try:
        destination_matches = (
            expected_destination.resolve(strict=False) == destination.resolve(strict=False)
        )
    except OSError as exc:
        raise _acquisition_error(
            "destination_resolution_failed",
            accepted=True,
            credential_present=True,
        ) from exc
    if not destination_matches:
        raise _acquisition_error("destination_not_bound_to_manifest", accepted=True, credential_present=True)
    return dict(payload), gpqa_row


def _updated_download_manifest(
    manifest: Mapping[str, Any],
    *,
    artifact: Mapping[str, Any],
    destination: Path,
) -> dict[str, Any]:
    updated = dict(manifest)
    suites: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for raw_row in manifest.get("suites", []):
        row = dict(raw_row) if isinstance(raw_row, Mapping) else {}
        if str(row.get("suite_id") or "") == "gpqa_diamond":
            row.update(
                {
                    "status": "downloaded",
                    "evaluation_ready": True,
                    "file_count": 1,
                    "files": [
                        {
                            "path": GPQA_RELATIVE_PATH,
                            "bytes": int(artifact["bytes"]),
                            "rows": int(artifact["row_count"]),
                            "sha256": str(artifact["sha256"]),
                            "git_blob_sha1": str(artifact["git_blob_sha1"]),
                        }
                    ],
                    "local_paths": [str(destination.parent)],
                    "notes": "Authorized gated download completed after explicit operator terms acceptance.",
                    "source_revision": GPQA_REVISION,
                    "source_git_blob_sha1": GPQA_EXPECTED_GIT_BLOB_SHA1,
                    "total_bytes": int(artifact["bytes"]),
                    "total_rows_if_countable": int(artifact["row_count"]),
                    "authorization_receipt": {
                        "accepted": True,
                        "terms_contract_sha256": GPQA_TERMS_CONTRACT_SHA256,
                        "accepted_at_utc": now,
                        "credential_value_persisted": False,
                        "download_url_persisted": False,
                        "dataset_examples_persisted": False,
                    },
                }
            )
        suites.append(row)
    updated["suites"] = suites
    blocked = sorted(
        str(row.get("suite_id") or "")
        for row in suites
        if str(row.get("status") or "").startswith("blocked")
    )
    updated["blocked_suites"] = blocked
    updated["blocked_gated_suite_count"] = sum(
        1 for row in suites if str(row.get("status") or "") == "blocked_gated"
    )
    updated["downloaded_suite_count"] = sum(
        1 for row in suites if str(row.get("status") or "") == "downloaded"
    )
    updated["updated_at_utc"] = now
    return updated


def _verify_existing_authorized_artifact(
    destination: Path,
    *,
    manifest_path: Path,
    gpqa_row: Mapping[str, Any],
    proxy_receipt: Mapping[str, Any],
    credential_source: str,
) -> dict[str, Any]:
    integrity = audit_gpqa_authorized_artifact(
        artifact_path=destination,
        manifest_row=gpqa_row,
    )
    if integrity.get("valid") is not True:
        reasons = integrity.get("reason_codes")
        reason = str(reasons[0]) if isinstance(reasons, list) and reasons else "existing_artifact_invalid"
        raise _acquisition_error(
            reason,
            accepted=True,
            credential_present=True,
        )
    artifact = dict(integrity.get("artifact") or {})
    return _success_receipt(
        status="already_downloaded_verified",
        artifact=artifact,
        manifest_path=manifest_path,
        destination=destination,
        proxy_receipt=proxy_receipt,
        credential_source=credential_source,
        network_download_performed=False,
    )


def _hash_existing_artifact(path: Path) -> dict[str, Any]:
    try:
        byte_count = path.stat().st_size
        if byte_count != GPQA_EXPECTED_BYTES:
            raise _acquisition_error("existing_artifact_size_mismatch", accepted=True, credential_present=True)
        sha256 = hashlib.sha256()
        git_blob_sha1 = _new_git_blob_sha1()
        git_blob_sha1.update(f"blob {GPQA_EXPECTED_BYTES}\0".encode("ascii"))
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                sha256.update(chunk)
                git_blob_sha1.update(chunk)
    except BenchmarkAcquisitionError:
        raise
    except OSError as exc:
        raise _acquisition_error("existing_artifact_read_failed", accepted=True, credential_present=True) from exc
    blob_id = git_blob_sha1.hexdigest()
    if blob_id != GPQA_EXPECTED_GIT_BLOB_SHA1:
        raise _acquisition_error("existing_artifact_blob_mismatch", accepted=True, credential_present=True)
    return {"bytes": byte_count, "sha256": sha256.hexdigest(), "git_blob_sha1": blob_id}


def _success_receipt(
    *,
    status: str,
    artifact: Mapping[str, Any],
    manifest_path: Path,
    destination: Path,
    proxy_receipt: Mapping[str, Any],
    credential_source: str,
    network_download_performed: bool,
) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.gpqa_acquisition_receipt.v1",
        "suite_id": "gpqa_diamond",
        "status": status,
        "reason_code": "",
        "source_kind": "official_huggingface_gated",
        "source_revision": GPQA_REVISION,
        "source_git_blob_sha1": GPQA_EXPECTED_GIT_BLOB_SHA1,
        "terms_explicitly_accepted": True,
        "terms_contract_sha256": GPQA_TERMS_CONTRACT_SHA256,
        "credential_present": True,
        "credential_source": credential_source,
        "credential_value_persisted": False,
        "network_download_performed": bool(network_download_performed),
        "artifact": {
            "bytes": int(artifact["bytes"]),
            "row_count": int(artifact["row_count"]),
            "sha256": str(artifact["sha256"]),
            "git_blob_sha1": str(artifact["git_blob_sha1"]),
            "destination_path_sha256": _path_identity_sha256(destination),
        },
        "download_manifest": {
            "updated": status == "downloaded",
            "path_sha256": _path_identity_sha256(manifest_path),
            "schema": "axio_fusion_benchmarks.download_manifest.v4",
        },
        "proxy": dict(proxy_receipt),
        "download_url_persisted": False,
        "raw_dataset_path_persisted": False,
        "dataset_examples_persisted": False,
        "answer_labels_persisted": False,
        "secrets_persisted": False,
    }


def _resolve_hugging_face_token(secret_resolver: SecretResolver | None) -> tuple[str, str]:
    try:
        if secret_resolver is not None:
            for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
                value = str(secret_resolver(name) or "").strip()
                if value:
                    return _validated_token(value), "process_secret_resolver"
            return "", "process_secret_resolver"
        for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
            value = os.getenv(name, "").strip()
            if value:
                return _validated_token(value), "process_environment"
    except BenchmarkAcquisitionError:
        raise
    except Exception as exc:
        raise _acquisition_error("credential_resolution_failed", accepted=True) from exc
    return "", "process_environment"


def _validated_token(value: str) -> str:
    if len(value) < 8 or len(value) > 4096 or any(character.isspace() for character in value):
        raise _acquisition_error("credential_invalid", accepted=True, credential_present=True)
    return value


def _open_hugging_face_url(request: urllib.request.Request, *, timeout: float):
    try:
        opener = build_network_opener(_TrustedHuggingFaceRedirectHandler())
    except NetworkPolicyError as exc:
        raise _acquisition_error(
            exc.reason_code,
            accepted=True,
            credential_present=True,
        ) from exc
    return opener.open(request, timeout=timeout)


def _validate_final_response_url(response: Any) -> None:
    getter = getattr(response, "geturl", None)
    final_url = str(getter() if callable(getter) else "")
    try:
        parsed = urllib.parse.urlsplit(final_url)
    except ValueError as exc:
        raise _acquisition_error(
            "final_response_origin_not_allowed",
            accepted=True,
            credential_present=True,
        ) from exc
    if not _trusted_hugging_face_url(parsed):
        raise _acquisition_error(
            "final_response_origin_not_allowed",
            accepted=True,
            credential_present=True,
        )


def _trusted_hugging_face_host(hostname: str | None) -> bool:
    host = str(hostname or "").strip().casefold().rstrip(".")
    return any(host == root or host.endswith(f".{root}") for root in _TRUSTED_HUGGING_FACE_HOSTS)


def _trusted_hugging_face_url(parsed: urllib.parse.SplitResult) -> bool:
    try:
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme.casefold() == "https"
        and _trusted_hugging_face_host(parsed.hostname)
        and port in {None, 443}
        and parsed.username is None
        and parsed.password is None
    )


def _remove_request_header(request: urllib.request.Request, header_name: str) -> None:
    expected = str(header_name).casefold()
    for headers in (request.headers, request.unredirected_hdrs):
        for key in list(headers):
            if str(key).casefold() == expected:
                del headers[key]


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None:
        getter = getattr(response, "getcode", None)
        status = getter() if callable(getter) else None
    try:
        return int(status)
    except (TypeError, ValueError) as exc:
        raise _acquisition_error(
            "http_status_missing",
            accepted=True,
            credential_present=True,
        ) from exc


def _header_value(headers: Any, name: str) -> Any:
    getter = getattr(headers, "get", None)
    return getter(name) if callable(getter) else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _path_identity_sha256(path: Path) -> str:
    return sha256_text(os.path.abspath(os.fspath(path)))


def _http_acquisition_error(status: int | None) -> BenchmarkAcquisitionError:
    normalized = int(status or 0)
    if normalized in {401, 403}:
        reason = "authorization_rejected"
    elif normalized == 429:
        reason = "upstream_rate_limited"
    elif 300 <= normalized < 400:
        reason = "redirect_not_completed"
    elif normalized >= 500:
        reason = "upstream_server_error"
    else:
        reason = "upstream_http_error"
    return _acquisition_error(
        reason,
        accepted=True,
        credential_present=True,
        http_status=normalized or None,
    )


def _discard_http_error_body(exc: urllib.error.HTTPError) -> None:
    try:
        exc.read()
    except Exception:
        pass
    finally:
        try:
            exc.close()
        except Exception:
            pass


def _new_git_blob_sha1():
    try:
        return hashlib.sha1(usedforsecurity=False)
    except TypeError:
        # Python 3.8 builds do not universally expose the OpenSSL policy hint.
        return hashlib.sha1()


def _empty_private_temporary(directory: Path, *, prefix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    return Path(raw_path)


def _stage_private_bytes(directory: Path, payload: bytes, *, prefix: str) -> Path:
    path = _empty_private_temporary(directory, prefix=prefix)
    try:
        with path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        _unlink_quietly(path)
        raise
    return path


def _unlink_quietly(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _acquisition_error(
    reason_code: str,
    *,
    accepted: bool,
    credential_present: bool = False,
    http_status: int | None = None,
) -> BenchmarkAcquisitionError:
    return BenchmarkAcquisitionError(
        reason_code,
        terms_explicitly_accepted=accepted,
        credential_present=credential_present,
        http_status=http_status,
    )
