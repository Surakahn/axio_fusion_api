from __future__ import annotations

"""Static, hash-safe audit for Axio's remote-API-only execution boundary."""

import ast
from importlib import metadata as importlib_metadata
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .providers import (
    HTTPProviderClient,
    PROVIDER_INPUT_ADAPTER_FORMATS,
    provider_base_url_readiness,
)
from .schemas import sha256_text, stable_json


REMOTE_PROVIDER_URL_SCHEMES = ("http", "https")
LOCAL_INFERENCE_IMPORT_ROOTS = frozenset(
    {
        "accelerate",
        "bitsandbytes",
        "diffusers",
        "flax",
        "jax",
        "keras",
        "llama_cpp",
        "llama_cpp_python",
        "onnxruntime",
        "peft",
        "sentence_transformers",
        "tensorflow",
        "torch",
        "torchaudio",
        "torchvision",
        "transformers",
        "vllm",
    }
)
LOCAL_MODEL_ARTIFACT_SUFFIXES = frozenset(
    {
        ".bin",
        ".ckpt",
        ".gguf",
        ".onnx",
        ".pt",
        ".pth",
        ".safetensors",
    }
)


def build_remote_api_execution_audit(
    *,
    source_root: str | Path | None = None,
    package_metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    """Audit the standalone package without importing models or using a network.

    The audit intentionally examines only the Fusion package source tree.  It
    makes the product boundary independently checkable without inspecting the
    sibling ASciFS workspace or persisting source text, local paths, endpoints,
    credentials, prompts, or provider output.
    """

    root = _resolve_source_root(source_root)
    root_ready = root.is_dir()
    source_files = _source_files(root) if root_ready else []
    source_summary = _source_audit(root, source_files) if root_ready else _empty_source_audit()
    artifact_summary = _model_artifact_audit(root) if root_ready else _empty_artifact_audit()
    dependency_summary = _dependency_audit(
        source_root=root,
        package_metadata_path=package_metadata_path,
    )
    transport_summary = _remote_transport_audit()

    reasons: list[str] = []
    if not root_ready:
        reasons.append("remote_api_execution_source_root_missing")
    if source_summary["read_error_count"]:
        reasons.append("remote_api_execution_source_read_error")
    if source_summary["parse_error_count"]:
        reasons.append("remote_api_execution_source_parse_error")
    if source_summary["forbidden_import_count"]:
        reasons.append("remote_api_execution_local_inference_import_detected")
    if source_summary["forbidden_dynamic_import_count"]:
        reasons.append("remote_api_execution_local_inference_dynamic_import_detected")
    if dependency_summary["metadata_available"] is not True:
        reasons.append("remote_api_execution_package_metadata_unavailable")
    if dependency_summary["forbidden_dependency_count"]:
        reasons.append("remote_api_execution_local_inference_dependency_detected")
    if artifact_summary["local_model_artifact_count"]:
        reasons.append("remote_api_execution_local_model_artifact_detected")
    if transport_summary["url_scheme_guard_ready"] is not True:
        reasons.append("remote_api_execution_http_scheme_guard_not_ready")
    if transport_summary["provider_input_format_contract_ready"] is not True:
        reasons.append("remote_api_execution_provider_input_format_contract_invalid")
    if transport_summary["http_provider_client_available"] is not True:
        reasons.append("remote_api_execution_http_provider_client_unavailable")
    reasons = sorted(set(reasons))

    return {
        "schema": "axio_fusion_api.remote_api_execution_audit.v1",
        "ready": not reasons,
        "execution_model": "remote_http_api_orchestration_only",
        "standalone_product": True,
        "decoupled_from_asci_fs": True,
        "source_audit": source_summary,
        "dependency_audit": dependency_summary,
        "local_model_artifact_audit": artifact_summary,
        "provider_transport_audit": transport_summary,
        "reason_codes": reasons,
        "contract": {
            "local_model_deployment_allowed": False,
            "local_weight_inference_allowed": False,
            "local_weight_training_allowed": False,
            "remote_http_provider_api_required": True,
            "network_calls_performed_by_audit": False,
        },
        "network_calls_performed": False,
        "raw_source_persisted": False,
        "raw_local_paths_persisted": False,
        "raw_provider_urls_persisted": False,
        "raw_provider_outputs_persisted": False,
        "secrets_persisted": False,
    }


def _resolve_source_root(value: str | Path | None) -> Path:
    raw = Path(value) if value is not None else Path(__file__).resolve().parent
    try:
        return raw.resolve()
    except OSError:
        return raw


def _source_files(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*.py") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def _source_audit(root: Path, source_files: Sequence[Path]) -> dict[str, Any]:
    source_digests: list[str] = []
    forbidden_imports: set[str] = set()
    forbidden_dynamic_imports: set[str] = set()
    read_error_count = 0
    parse_error_count = 0
    for path in source_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            read_error_count += 1
            continue
        relative_name = _relative_name(path, root)
        source_digests.append(sha256_text(f"{relative_name}\n{text}"))
        try:
            tree = ast.parse(text, filename=relative_name)
        except SyntaxError:
            parse_error_count += 1
            continue
        static_roots, dynamic_roots = _local_inference_import_roots(tree)
        forbidden_imports.update(static_roots)
        forbidden_dynamic_imports.update(dynamic_roots)
    return {
        "source_file_count": len(source_files),
        "source_set_sha256": sha256_text(stable_json(source_digests)) if source_digests else "",
        "read_error_count": read_error_count,
        "parse_error_count": parse_error_count,
        "forbidden_import_count": len(forbidden_imports),
        "forbidden_import_roots": sorted(forbidden_imports),
        "forbidden_dynamic_import_count": len(forbidden_dynamic_imports),
        "forbidden_dynamic_import_roots": sorted(forbidden_dynamic_imports),
        "raw_source_persisted": False,
        "raw_local_paths_persisted": False,
    }


def _empty_source_audit() -> dict[str, Any]:
    return {
        "source_file_count": 0,
        "source_set_sha256": "",
        "read_error_count": 0,
        "parse_error_count": 0,
        "forbidden_import_count": 0,
        "forbidden_import_roots": [],
        "forbidden_dynamic_import_count": 0,
        "forbidden_dynamic_import_roots": [],
        "raw_source_persisted": False,
        "raw_local_paths_persisted": False,
    }


def _local_inference_import_roots(tree: ast.AST) -> tuple[set[str], set[str]]:
    static_roots: set[str] = set()
    dynamic_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _normalized_module_root(alias.name)
                if root in LOCAL_INFERENCE_IMPORT_ROOTS:
                    static_roots.add(root)
        elif isinstance(node, ast.ImportFrom):
            root = _normalized_module_root(node.module)
            if root in LOCAL_INFERENCE_IMPORT_ROOTS:
                static_roots.add(root)
        elif isinstance(node, ast.Call) and _is_dynamic_import_call(node.func):
            if not node.args:
                continue
            value = node.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                root = _normalized_module_root(value.value)
                if root in LOCAL_INFERENCE_IMPORT_ROOTS:
                    dynamic_roots.add(root)
    return static_roots, dynamic_roots


def _normalized_module_root(value: Any) -> str:
    return str(value or "").split(".", 1)[0].strip().lower().replace("-", "_")


def _is_dynamic_import_call(value: ast.AST) -> bool:
    if isinstance(value, ast.Name):
        return value.id == "__import__"
    if isinstance(value, ast.Attribute):
        return value.attr == "import_module"
    return False


def _model_artifact_audit(root: Path) -> dict[str, Any]:
    suffix_counts: dict[str, int] = {}
    try:
        paths = list(root.rglob("*"))
    except OSError:
        paths = []
    for path in paths:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in LOCAL_MODEL_ARTIFACT_SUFFIXES:
            suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    return {
        "local_model_artifact_count": sum(suffix_counts.values()),
        "local_model_artifact_suffix_counts": dict(sorted(suffix_counts.items())),
        "raw_local_paths_persisted": False,
        "raw_model_artifacts_persisted": False,
    }


def _empty_artifact_audit() -> dict[str, Any]:
    return {
        "local_model_artifact_count": 0,
        "local_model_artifact_suffix_counts": {},
        "raw_local_paths_persisted": False,
        "raw_model_artifacts_persisted": False,
    }


def _dependency_audit(
    *,
    source_root: Path,
    package_metadata_path: str | Path | None,
) -> dict[str, Any]:
    values, metadata_source = _declared_dependency_values(
        source_root=source_root,
        package_metadata_path=package_metadata_path,
    )
    normalized = {_normalized_requirement_root(value) for value in values}
    forbidden = sorted(root for root in normalized if root in LOCAL_INFERENCE_IMPORT_ROOTS)
    return {
        "metadata_available": metadata_source != "unavailable",
        "metadata_source": metadata_source,
        "declared_dependency_count": len(normalized),
        "declared_dependency_set_sha256": sha256_text(stable_json(sorted(normalized))) if normalized else "",
        "forbidden_dependency_count": len(forbidden),
        "forbidden_dependency_roots": forbidden,
        "raw_dependency_values_persisted": False,
        "raw_local_paths_persisted": False,
    }


def _declared_dependency_values(
    *,
    source_root: Path,
    package_metadata_path: str | Path | None,
) -> tuple[list[str], str]:
    metadata_path = Path(package_metadata_path) if package_metadata_path is not None else source_root.parent.parent / "pyproject.toml"
    try:
        text = metadata_path.read_text(encoding="utf-8")
    except OSError:
        if package_metadata_path is not None:
            return [], "unavailable"
    else:
        return _quoted_values(text), "pyproject"
    try:
        requirements = importlib_metadata.requires("axio-fusion-api") or []
    except importlib_metadata.PackageNotFoundError:
        return [], "unavailable"
    return [str(value) for value in requirements], "installed_distribution"


def _quoted_values(value: str) -> list[str]:
    matches = re.findall(r'"([^"\n]+)"|\'([^\'\n]+)\'', value)
    return [first or second for first, second in matches if first or second]


def _normalized_requirement_root(value: Any) -> str:
    root = re.split(r"[\s<>=!~;\[\],]+", str(value or "").strip(), maxsplit=1)[0]
    return root.lower().replace("-", "_")


def _remote_transport_audit() -> dict[str, Any]:
    http_ready = provider_base_url_readiness("http://remote.example.invalid/v1").get("valid") is True
    https_ready = provider_base_url_readiness("https://remote.example.invalid/v1").get("valid") is True
    file_blocked = provider_base_url_readiness("file:///tmp/model").get("valid") is False
    unix_blocked = provider_base_url_readiness("unix:///tmp/provider.sock").get("valid") is False
    formats = tuple(sorted(str(value) for value in PROVIDER_INPUT_ADAPTER_FORMATS))
    expected_formats = ("anthropic", "chat", "gemini", "responses")
    return {
        "allowed_base_url_schemes": list(REMOTE_PROVIDER_URL_SCHEMES),
        "url_scheme_guard_ready": http_ready and https_ready and file_blocked and unix_blocked,
        "provider_input_api_formats": list(formats),
        "provider_input_format_contract_ready": formats == expected_formats,
        "http_provider_client_available": isinstance(HTTPProviderClient(), HTTPProviderClient),
        "network_calls_performed": False,
        "raw_provider_urls_persisted": False,
        "secrets_persisted": False,
    }


def _relative_name(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name
