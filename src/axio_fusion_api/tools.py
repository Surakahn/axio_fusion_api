from __future__ import annotations

import ast
import json
import operator
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from .schemas import sha256_text


SAFE_BUILTIN_TOOLS = ("math_eval", "json_get", "text_search")


class ToolExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def execute_tool_batch(
    calls: Sequence[Mapping[str, Any]],
    *,
    role: str = "primary_solver",
    max_tool_calls: int | None = None,
    artifact_path: str | Path | None = None,
    tool_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    limit = max(0, int(max_tool_calls if max_tool_calls is not None else os.getenv("AXIO_FUSION_MAX_TOOL_CALLS") or 8))
    selected = list(calls[:limit])
    blocked_by_limit = max(0, len(calls) - len(selected))
    results = []
    started = time.monotonic()
    policy = _role_tool_policy(tool_policy, role)
    for index, call in enumerate(selected):
        results.append(execute_tool_call(call, role=role, call_index=index, tool_policy=policy))
    payload = {
        "schema": "axio_fusion_api.tool_execution_batch.v1",
        "role": role,
        "requested_call_count": len(calls),
        "executed_or_blocked_call_count": len(results),
        "blocked_by_limit_count": blocked_by_limit,
        "success_count": sum(1 for row in results if row.get("status") == "completed"),
        "blocked_count": sum(1 for row in results if row.get("status") == "blocked") + blocked_by_limit,
        "failed_count": sum(1 for row in results if row.get("status") == "failed"),
        "results": results,
        "latency_ms": round((time.monotonic() - started) * 1000, 3),
        "route_tool_policy": _tool_policy_receipt(policy),
        "raw_tool_arguments_persisted": False,
        "raw_tool_result_persisted": False,
        "raw_prompt_persisted": False,
        "secrets_persisted": False,
    }
    _append_tool_artifact(payload, artifact_path)
    return payload


def execute_tool_call(
    call: Mapping[str, Any],
    *,
    role: str = "primary_solver",
    call_index: int = 0,
    tool_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    name = _tool_name(call)
    category = classify_tool(name, str(call.get("type") or "function"))
    arguments = _tool_arguments(call)
    tool_hash = _route_tool_hash(call, call_index)
    receipt = {
        "schema": "axio_fusion_api.tool_execution_receipt.v1",
        "call_index": call_index,
        "tool_hash": tool_hash,
        "tool_name_sha256": sha256_text(name),
        "tool_category": category,
        "role": role,
        "argument_sha256": sha256_text(json.dumps(arguments, ensure_ascii=False, sort_keys=True)),
        "approval_required": _approval_required(category),
        "approved": bool(call.get("approved") or call.get("approval_token")),
        "route_tool_policy_enforced": bool(tool_policy and tool_policy.get("enforced")),
        "raw_tool_arguments_persisted": False,
        "raw_tool_result_persisted": False,
        "raw_tool_schema_persisted": False,
        "secrets_persisted": False,
    }
    try:
        _enforce_route_tool_policy(tool_hash, tool_policy)
        _enforce_permission(role, category, receipt["approved"])
        result = _execute_builtin(name, arguments)
        receipt.update(
            {
                "status": "completed",
                "result": result,
                "result_sha256": sha256_text(json.dumps(result, ensure_ascii=False, sort_keys=True)),
                "error_code": "",
            }
        )
    except ToolExecutionError as exc:
        receipt.update(
            {
                "status": "blocked" if exc.code.startswith("blocked") or exc.code.endswith("required") else "failed",
                "result": None,
                "result_sha256": "",
                "error_code": exc.code,
                "error_sha256": sha256_text(str(exc)),
            }
        )
    except Exception as exc:  # noqa: PERF203 - tool boundary
        receipt.update(
            {
                "status": "failed",
                "result": None,
                "result_sha256": "",
                "error_code": type(exc).__name__,
                "error_sha256": sha256_text(str(exc)),
            }
        )
    receipt["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
    return receipt


def classify_tool(name: str, tool_type: str = "function") -> str:
    text = f"{name} {tool_type}".lower()
    normalized_name = name.strip().lower()
    normalized_type = tool_type.strip().lower()
    if (
        normalized_type == "fusion"
        or normalized_name in {"fusion", "openrouter:fusion", "axio_fusion", "axio-fusion"}
        or "openrouter:fusion" in text
    ):
        return "fusion_plugin"
    if any(token in text for token in ("delete", "write", "patch", "deploy", "exec", "shell", "command", "mutation")):
        return "destructive_execution" if any(token in text for token in ("exec", "shell", "command")) else "write_action"
    if any(token in text for token in ("search", "web", "browser", "http", "fetch")):
        return "network_search" if "web" in text or "http" in text or "fetch" in text else "function_call"
    if any(token in text for token in ("repo", "code", "file", "read")):
        return "repo_read"
    return "function_call" if tool_type or name else "unknown"


def _execute_builtin(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    normalized = name.strip().lower()
    if normalized == "math_eval":
        expression = str(arguments.get("expression") or "")
        value = _safe_math_eval(expression)
        return {
            "kind": "math_eval",
            "value": value,
            "value_text": str(value),
            "raw_expression_persisted": False,
        }
    if normalized == "json_get":
        document = arguments.get("document")
        path = str(arguments.get("path") or "")
        value = _json_get(document, path)
        return {
            "kind": "json_get",
            "value": value,
            "value_sha256": sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True)),
            "raw_document_persisted": False,
        }
    if normalized == "text_search":
        text = str(arguments.get("text") or "")
        query = str(arguments.get("query") or "")
        positions = _text_search(text, query)
        return {
            "kind": "text_search",
            "match_count": len(positions),
            "positions": positions[:50],
            "text_sha256": sha256_text(text),
            "query_sha256": sha256_text(query),
            "raw_text_persisted": False,
        }
    raise ToolExecutionError("blocked_unknown_tool", f"Tool is not in the safe builtin allowlist: {name}")


def _enforce_permission(role: str, category: str, approved: bool) -> None:
    if category == "fusion_plugin":
        raise ToolExecutionError("blocked_fusion_plugin_route_only", "Fusion plugin requests are route-control signals, not executable tools.")
    if category in {"destructive_execution", "write_action", "deployment_action"}:
        if not approved:
            raise ToolExecutionError("blocked_external_approval_required", "Destructive or write tool requires external approval.")
        if os.getenv("AXIO_FUSION_ALLOW_DESTRUCTIVE_TOOLS", "").lower() not in {"1", "true", "yes"}:
            raise ToolExecutionError("blocked_destructive_tools_disabled", "Destructive tools are disabled by runtime policy.")
    if role in {"judge", "synthesizer"}:
        raise ToolExecutionError("blocked_role_read_only", "Judge and synthesizer roles are read-only.")
    if role == "critic" and category not in {"repo_read", "function_call"}:
        raise ToolExecutionError("blocked_role_tool_scope", "Critic role can only use repo-read or safe function tools.")
    if category == "network_search" and os.getenv("AXIO_FUSION_ALLOW_NETWORK_TOOLS", "").lower() not in {"1", "true", "yes"}:
        raise ToolExecutionError("blocked_network_tools_disabled", "Network tools require AXIO_FUSION_ALLOW_NETWORK_TOOLS=1.")


def _safe_math_eval(expression: str) -> int | float:
    if len(expression) > 512:
        raise ToolExecutionError("blocked_expression_too_long", "Expression is too long.")
    node = ast.parse(expression, mode="eval")
    return _eval_ast(node.body)


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_ast(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Num):  # pragma: no cover - compatibility path
        return node.n
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ToolExecutionError("blocked_exponent_too_large", "Exponent is too large.")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_ast(node.operand))
    raise ToolExecutionError("blocked_unsafe_expression", "Only numeric arithmetic expressions are allowed.")


def _json_get(document: Any, path: str) -> Any:
    value = document
    if not path:
        return value
    for part in path.split("."):
        if isinstance(value, Mapping):
            value = value[part]
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            value = value[int(part)]
        else:
            raise ToolExecutionError("failed_json_path", "Path cannot be resolved.")
    return value


def _text_search(text: str, query: str) -> list[int]:
    if not query:
        raise ToolExecutionError("failed_empty_query", "Query must not be empty.")
    positions = []
    start = 0
    lowered_text = text.lower()
    lowered_query = query.lower()
    while True:
        index = lowered_text.find(lowered_query, start)
        if index < 0:
            return positions
        positions.append(index)
        start = index + max(1, len(lowered_query))


def _tool_name(call: Mapping[str, Any]) -> str:
    function = call.get("function") if isinstance(call.get("function"), Mapping) else {}
    return str(call.get("name") or function.get("name") or call.get("tool_name") or "")


def _tool_arguments(call: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(call.get("arguments"), Mapping):
        return call["arguments"]
    function = call.get("function") if isinstance(call.get("function"), Mapping) else {}
    raw = function.get("arguments") if "arguments" in function else call.get("arguments")
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError("failed_invalid_json_arguments", "Tool arguments must be a JSON object.") from exc
        if isinstance(value, Mapping):
            return value
    return {}


def _approval_required(category: str) -> bool:
    return category in {"destructive_execution", "write_action", "deployment_action"}


def _route_tool_hash(call: Mapping[str, Any], call_index: int) -> str:
    function = call.get("function") if isinstance(call.get("function"), Mapping) else {}
    tool_type = str(call.get("type") or "").strip().lower()
    name = str(call.get("name") or function.get("name") or call.get("tool_name") or tool_type or f"tool_{call_index}")
    route_index = call.get("tool_index", call_index)
    try:
        index = int(route_index)
    except (TypeError, ValueError):
        index = call_index
    return sha256_text(f"{index}:{tool_type}:{name}")


def _role_tool_policy(tool_policy: Mapping[str, Any] | None, role: str) -> dict[str, Any]:
    if not isinstance(tool_policy, Mapping):
        return {
            "enforced": False,
            "role": role,
            "role_found": False,
            "allowed_tool_hashes": set(),
            "denied_tool_hashes": set(),
        }
    permissions = tool_policy.get("role_permissions") if isinstance(tool_policy.get("role_permissions"), list) else []
    selected = next(
        (row for row in permissions if isinstance(row, Mapping) and str(row.get("role") or "") == role),
        None,
    )
    allowed = set(str(item) for item in selected.get("allowed_tool_hashes", []) if str(item)) if isinstance(selected, Mapping) and isinstance(selected.get("allowed_tool_hashes"), list) else set()
    denied = set(str(item) for item in selected.get("denied_tool_hashes", []) if str(item)) if isinstance(selected, Mapping) and isinstance(selected.get("denied_tool_hashes"), list) else set()
    return {
        "enforced": True,
        "role": role,
        "role_found": selected is not None,
        "allowed_tool_hashes": allowed,
        "denied_tool_hashes": denied,
    }


def _tool_policy_receipt(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "axio_fusion_api.tool_policy_enforcement.v1",
        "enforced": bool(policy.get("enforced")),
        "role": str(policy.get("role") or "")[:80],
        "role_found": bool(policy.get("role_found")),
        "allowed_tool_count": len(policy.get("allowed_tool_hashes") or []),
        "denied_tool_count": len(policy.get("denied_tool_hashes") or []),
        "default_deny_when_enforced": True,
        "raw_tool_schema_persisted": False,
        "secrets_persisted": False,
    }


def _enforce_route_tool_policy(tool_hash: str, policy: Mapping[str, Any] | None) -> None:
    if not policy or not policy.get("enforced"):
        return
    if not policy.get("role_found"):
        raise ToolExecutionError("blocked_route_tool_policy_missing_role", "Route tool policy did not define permissions for this role.")
    allowed = policy.get("allowed_tool_hashes") or set()
    denied = policy.get("denied_tool_hashes") or set()
    if tool_hash in denied or tool_hash not in allowed:
        raise ToolExecutionError("blocked_by_route_tool_policy", "Tool is not allowed for this role by the route plan.")


def _append_tool_artifact(payload: Mapping[str, Any], artifact_path: str | Path | None) -> None:
    path = _tool_artifact_path(artifact_path)
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_artifact_payload(payload), ensure_ascii=False, sort_keys=True) + "\n")


def _tool_artifact_path(path: str | Path | None = None) -> Path | None:
    if path:
        return Path(path)
    explicit = os.getenv("AXIO_FUSION_TOOL_LOG", "").strip()
    if explicit:
        return Path(explicit)
    artifact_dir = os.getenv("AXIO_FUSION_ARTIFACT_DIR", "").strip()
    if artifact_dir:
        return Path(artifact_dir) / "tool_executions.jsonl"
    return None


def _artifact_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for row in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "schema": row.get("schema"),
                "call_index": row.get("call_index"),
                "tool_hash": row.get("tool_hash"),
                "tool_name_sha256": row.get("tool_name_sha256"),
                "tool_category": row.get("tool_category"),
                "role": row.get("role"),
                "argument_sha256": row.get("argument_sha256"),
                "status": row.get("status"),
                "result_sha256": row.get("result_sha256"),
                "error_code": row.get("error_code"),
                "latency_ms": row.get("latency_ms"),
                "route_tool_policy_enforced": bool(row.get("route_tool_policy_enforced")),
                "raw_tool_arguments_persisted": False,
                "raw_tool_result_persisted": False,
                "raw_tool_schema_persisted": False,
            }
        )
    return {
        "schema": payload.get("schema"),
        "role": payload.get("role"),
        "requested_call_count": payload.get("requested_call_count"),
        "success_count": payload.get("success_count"),
        "blocked_count": payload.get("blocked_count"),
        "failed_count": payload.get("failed_count"),
        "route_tool_policy": payload.get("route_tool_policy"),
        "results": rows,
        "raw_tool_arguments_persisted": False,
        "raw_tool_result_persisted": False,
        "raw_tool_schema_persisted": False,
        "secrets_persisted": False,
    }
