from __future__ import annotations

"""Private execution worker for the pinned tau-bench environment.

The worker deliberately keeps the official environment, user simulator, task
goals, reward logic, visible conversation, and provider traffic out of public
benchmark artifacts.  It writes raw interaction transcripts only to the
operator-supplied private directory and emits a compact private result file
whose rows can later be normalized into hash-only scored evidence.
"""

import argparse
import contextlib
from importlib import import_module
import json
import os
from pathlib import Path
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request


@dataclass(frozen=True)
class CandidateTurn:
    text: str
    tool_calls: tuple[Mapping[str, Any], ...]
    cost: Mapping[str, Any]
    transport_receipt: Mapping[str, Any] = None


class TauBridgeRuntimeError(RuntimeError):
    pass


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        # The official user simulator or its SDK may log to stdout. Stdout is
        # reserved for callers, so redirect incidental harness logging away
        # from any machine-readable channel.
        with contextlib.redirect_stdout(sys.stderr):
            rows, interactions = _execute(args)
        _write_jsonl(Path(args.output), rows)
        _write_jsonl(Path(args.interactions_output), interactions)
        return 0
    except Exception as exc:  # noqa: BLE001 - private process boundary.
        error_path = Path(args.output).with_suffix(Path(args.output).suffix + ".error")
        _write_json(
            error_path,
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "raw_error_message_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            },
        )
        return 1


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a private pinned tau-bench interaction.")
    parser.add_argument("--harness-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--interactions-output", required=True)
    parser.add_argument("--candidate-kind", required=True, choices=("public_axio", "provider_native"))
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--api-format", required=True)
    parser.add_argument("--gateway-url", default="")
    parser.add_argument("--registry", default="")
    parser.add_argument("--environment", action="append", choices=("retail", "airline"), default=[])
    parser.add_argument("--user-model", required=True)
    parser.add_argument("--user-provider", required=True)
    parser.add_argument("--user-strategy", default="llm", choices=("llm", "react", "verify", "reflection"))
    parser.add_argument("--task-split", default="test")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    return parser.parse_args(list(argv) if argv is not None else None)


def _execute(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    harness_root = Path(args.harness_root)
    if not harness_root.is_dir():
        raise TauBridgeRuntimeError("tau_harness_root_missing")
    _prepend_import_path(harness_root)
    try:
        from tau_bench.envs import get_env
        from tau_bench.types import Action
    except Exception as exc:  # noqa: BLE001 - dependency version is an operator concern.
        raise TauBridgeRuntimeError("tau_harness_import_failed") from exc

    candidate = _candidate_adapter(args)
    domains = tuple(args.environment or ("retail", "airline"))

    def env_factory(domain: str, task_index: int):
        return get_env(
            domain,
            user_strategy=args.user_strategy,
            user_model=args.user_model,
            user_provider=args.user_provider,
            task_split=args.task_split,
            task_index=task_index,
        )

    return run_tau_bench_cases(
        env_factory=env_factory,
        action_factory=lambda name, kwargs: Action(name=name, kwargs=kwargs),
        candidate=candidate,
        domains=domains,
        case_limit=args.limit,
        max_steps=max(1, int(args.max_steps)),
        max_output_tokens=max(1, int(args.max_output_tokens)),
    )


def run_tau_bench_cases(
    *,
    env_factory: Callable[[str, int], Any],
    action_factory: Callable[[str, Mapping[str, Any]], Any],
    candidate: Any,
    domains: Sequence[str],
    case_limit: int | None,
    max_steps: int,
    max_output_tokens: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the official environment while exposing only observable state.

    This function is intentionally dependency-injected so its no-hidden-goal
    boundary can be tested with a local fake environment. ``env.task`` is used
    only indirectly by the official environment; task goals, action lists and
    reward criteria never enter ``candidate.complete``.
    """

    rows: list[dict[str, Any]] = []
    interactions: list[dict[str, Any]] = []
    remaining = None if case_limit is None else max(0, int(case_limit))
    for domain in domains:
        if remaining is not None and remaining <= 0:
            break
        probe = env_factory(str(domain), 0)
        task_count = len(getattr(probe, "tasks", ()) or ())
        for task_index in range(task_count):
            if remaining is not None and remaining <= 0:
                break
            started = time.monotonic()
            source_identifier = f"{domain}:{task_index}"
            transcript: list[dict[str, Any]] = []
            cost_totals = _empty_cost()
            tool_error_count = 0
            tool_action_count = 0
            candidate_call_count = 0
            discarded_tool_call_count = 0
            http_gateway_call_count = 0
            network_call_count = 0
            public_api_surface_used = False
            api_format_matches = True
            unsafe_transport_receipt_count = 0
            reward = 0.0
            done = False
            error_type = ""
            try:
                env = env_factory(str(domain), task_index)
                reset = env.reset(task_index=task_index)
                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": str(getattr(env, "wiki", ""))},
                    {"role": "user", "content": str(getattr(reset, "observation", ""))},
                ]
                tools = tuple(
                    dict(tool)
                    for tool in getattr(env, "tools_info", ())
                    if isinstance(tool, Mapping)
                )
                transcript.extend(_copy_messages(messages))
                for _ in range(max_steps):
                    turn = candidate.complete(
                        messages=tuple(_copy_messages(messages)),
                        tools=tools,
                        max_output_tokens=max_output_tokens,
                    )
                    candidate_call_count += 1
                    _accumulate_cost(cost_totals, turn.cost)
                    receipt = turn.transport_receipt if isinstance(turn.transport_receipt, Mapping) else {}
                    if receipt.get("public_api_surface_used") is True:
                        public_api_surface_used = True
                    if receipt.get("transport") == "http_gateway":
                        http_gateway_call_count += 1
                    if receipt.get("network_calls_performed") is True:
                        network_call_count += 1
                    if receipt and receipt.get("api_format_matches_candidate") is not True:
                        api_format_matches = False
                    if receipt and _contains_unsafe_transport_receipt(receipt):
                        unsafe_transport_receipt_count += 1
                    calls = [dict(call) for call in turn.tool_calls if isinstance(call, Mapping)]
                    if calls:
                        discarded_tool_call_count += max(0, len(calls) - 1)
                        call = calls[0]
                        name = str(call.get("name") or "").strip()
                        arguments = call.get("arguments") if isinstance(call.get("arguments"), Mapping) else {}
                        action = action_factory(name, dict(arguments))
                        response = env.step(action)
                        tool_action_count += 1
                        observation = str(getattr(response, "observation", ""))
                        if observation.startswith(("Error:", "Unknown action")):
                            tool_error_count += 1
                        assistant = {
                            "role": "assistant",
                            "content": str(turn.text or ""),
                            "tool_calls": [dict(call)],
                        }
                        result = {
                            "role": "tool",
                            "tool_result": {
                                "call_id": str(call.get("id") or ""),
                                "name": name,
                                "output": observation,
                            },
                        }
                        messages.extend((assistant, result))
                        transcript.extend((dict(assistant), dict(result)))
                    else:
                        action = action_factory("respond", {"content": str(turn.text or "")})
                        response = env.step(action)
                        assistant = {"role": "assistant", "content": str(turn.text or "")}
                        user = {"role": "user", "content": str(getattr(response, "observation", ""))}
                        messages.extend((assistant, user))
                        transcript.extend((dict(assistant), dict(user)))
                    reward = float(getattr(response, "reward", 0.0) or 0.0)
                    done = bool(getattr(response, "done", False))
                    if done:
                        break
            except Exception as exc:  # noqa: BLE001 - a single task must not erase the run.
                error_type = type(exc).__name__
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            trajectory_digest = _sha256_json(transcript)
            passed = bool(done and reward >= 1.0 - 1e-6 and not error_type)
            status = "completed" if not error_type else "failed"
            rows.append(
                {
                    "environment": str(domain),
                    "task_index": int(task_index),
                    "source_identifier": source_identifier,
                    "status": status,
                    "passed": passed,
                    "success": passed,
                    "score": 1.0 if passed else 0.0,
                    "metric": "task_success_rate",
                    "latency_ms": elapsed_ms,
                    "candidate_call_count": candidate_call_count,
                    "tool_action_count": tool_action_count,
                    "tool_error_count": tool_error_count,
                    "discarded_tool_call_count": discarded_tool_call_count,
                    "trajectory_sha256": trajectory_digest,
                    "prediction_sha256": trajectory_digest,
                    "output_sha256": trajectory_digest,
                    "error_type": error_type[:120],
                    "public_api_transport": {
                        "public_api_surface_used": public_api_surface_used,
                        "transport": "http_gateway" if candidate_call_count and http_gateway_call_count == candidate_call_count else "",
                        "network_calls_performed": bool(candidate_call_count) and network_call_count == candidate_call_count,
                        "http_gateway_call_count": http_gateway_call_count,
                        "network_call_count": network_call_count,
                        "candidate_call_count": candidate_call_count,
                        "api_format_matches_candidate": api_format_matches,
                        "unsafe_transport_receipt_count": unsafe_transport_receipt_count,
                        "raw_gateway_url_persisted": False,
                        "raw_prompt_persisted": False,
                        "raw_provider_outputs_persisted": False,
                        "secrets_persisted": False,
                    },
                    **cost_totals,
                    "raw_task_goal_persisted": False,
                    "raw_reward_criteria_persisted": False,
                    "raw_provider_outputs_persisted": False,
                    "secrets_persisted": False,
                }
            )
            interactions.append(
                {
                    "environment": str(domain),
                    "task_index": int(task_index),
                    "messages": transcript,
                    "reward": reward,
                    "done": done,
                    "candidate_call_count": candidate_call_count,
                    "tool_action_count": tool_action_count,
                    "tool_error_count": tool_error_count,
                }
            )
            if remaining is not None:
                remaining -= 1
    return rows, interactions


class _PublicAxioCandidate:
    def __init__(self, *, candidate_id: str, api_format: str, gateway_url: str, timeout_seconds: float) -> None:
        self.candidate_id = candidate_id
        self.api_format = api_format
        self.gateway_url = gateway_url.rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        max_output_tokens: int,
    ) -> CandidateTurn:
        evaluation = import_module("axio_fusion_api.evaluation")
        tool_contract = import_module("axio_fusion_api.tool_contract")

        endpoint, payload = evaluation._benchmark_public_api_payload(
            model=self.candidate_id,
            api_format=self.api_format,
            prompt="",
            system="",
            task_type="agentic_tool_calling",
            max_output_tokens=max_output_tokens,
            tools=tools,
            messages=messages,
        )
        request = urllib_request.Request(
            evaluation._benchmark_gateway_target_url(self.gateway_url, endpoint),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=evaluation._benchmark_public_api_headers(allow_local_server_key=False),
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", response.getcode()))
                body = response.read()
        except urllib_error.HTTPError as exc:
            raise TauBridgeRuntimeError(f"tau_public_api_http_{int(exc.code)}") from None
        except (urllib_error.URLError, TimeoutError, OSError):
            raise TauBridgeRuntimeError("tau_public_api_unreachable") from None
        if status != 200:
            raise TauBridgeRuntimeError(f"tau_public_api_status_{status}")
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TauBridgeRuntimeError("tau_public_api_invalid_json") from exc
        if not isinstance(decoded, Mapping):
            raise TauBridgeRuntimeError("tau_public_api_response_invalid")
        if not evaluation._benchmark_public_api_response_shape_valid(decoded, self.api_format):
            raise TauBridgeRuntimeError("tau_public_api_response_shape_invalid")
        if evaluation._benchmark_public_api_response_model(decoded, self.api_format) != self.candidate_id:
            raise TauBridgeRuntimeError("tau_public_api_model_mismatch")
        normalized = "chat" if self.api_format == "chat/completions" else self.api_format
        metadata = decoded.get("metadata") if isinstance(decoded.get("metadata"), Mapping) else {}
        trace = metadata.get("fusion_trace_summary") if isinstance(metadata.get("fusion_trace_summary"), Mapping) else {}
        return CandidateTurn(
            text=evaluation._benchmark_public_api_response_text(decoded, self.api_format),
            tool_calls=tool_contract.normalize_provider_tool_calls(decoded, api_format=normalized),
            cost={
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": float(trace.get("actual_cost_usd") or 0.0),
                "pricing_known": trace.get("actual_cost_usd") is not None,
                "provider_call_count": int(trace.get("provider_call_count") or 0),
            },
            transport_receipt={
                "public_api_surface_used": True,
                "api_format_matches_candidate": True,
                "transport": "http_gateway",
                "network_calls_performed": True,
                "raw_gateway_url_persisted": False,
                "raw_prompt_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            },
        )


class _ProviderCandidate:
    def __init__(self, *, candidate_id: str, registry_path: str, timeout_seconds: float) -> None:
        registry = import_module("axio_fusion_api.registry")
        schemas = import_module("axio_fusion_api.schemas")

        prefix = "provider::"
        if not candidate_id.startswith(prefix):
            raise TauBridgeRuntimeError("tau_provider_candidate_alias_invalid")
        suffix = candidate_id[len(prefix) :].strip().lower()
        profiles = registry.load_registry(registry_path)
        self.profile = next((profile for profile in profiles if schemas.sha256_text(profile.profile_id) == suffix), None)
        if self.profile is None:
            raise TauBridgeRuntimeError("tau_provider_candidate_not_in_registry")
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
        max_output_tokens: int,
    ) -> CandidateTurn:
        compat = import_module("axio_fusion_api.compat")
        evaluation = import_module("axio_fusion_api.evaluation")
        providers = import_module("axio_fusion_api.providers")

        api_format = compat.normalize_api_format(self.profile.api_format)
        _, payload = evaluation._benchmark_public_api_payload(
            model="axio-fast",
            api_format=api_format,
            prompt="",
            system="",
            task_type="agentic_tool_calling",
            max_output_tokens=max_output_tokens,
            tools=tools,
            messages=messages,
        )
        request = compat.canonicalize_payload(payload, api_format=api_format)
        turn = providers.ensure_strict_streaming_client(None).complete_turn(
            self.profile,
            request,
            prompt=request.prompt,
            system=request.system,
            timeout=self.timeout_seconds,
        )
        return CandidateTurn(
            text=turn.text,
            tool_calls=turn.tool_calls,
            cost=evaluation._estimate_benchmark_provider_call_cost(
                self.profile,
                prompt=request.prompt,
                system=request.system,
                output_text=turn.text,
                expected_output_tokens=max_output_tokens,
            ),
            transport_receipt={
                "public_api_surface_used": False,
                "api_format_matches_candidate": True,
                "transport": "provider_native",
                "network_calls_performed": True,
                "raw_gateway_url_persisted": False,
                "raw_prompt_persisted": False,
                "raw_provider_outputs_persisted": False,
                "secrets_persisted": False,
            },
        )


def _candidate_adapter(args: argparse.Namespace) -> Any:
    if args.candidate_kind == "public_axio":
        if not str(args.gateway_url or "").strip():
            raise TauBridgeRuntimeError("tau_public_gateway_required")
        return _PublicAxioCandidate(
            candidate_id=str(args.candidate_id),
            api_format=str(args.api_format),
            gateway_url=str(args.gateway_url),
            timeout_seconds=float(args.timeout_seconds),
        )
    if not str(args.registry or "").strip():
        raise TauBridgeRuntimeError("tau_provider_registry_required")
    return _ProviderCandidate(
        candidate_id=str(args.candidate_id),
        registry_path=str(args.registry),
        timeout_seconds=float(args.timeout_seconds),
    )


def _empty_cost() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "pricing_known": True,
        "provider_call_count": 0,
    }


def _accumulate_cost(total: dict[str, Any], value: Mapping[str, Any]) -> None:
    total["input_tokens"] += _as_int(value.get("input_tokens"))
    total["output_tokens"] += _as_int(value.get("output_tokens"))
    total["estimated_cost_usd"] = round(
        float(total["estimated_cost_usd"]) + max(0.0, _as_float(value.get("estimated_cost_usd"))),
        8,
    )
    total["pricing_known"] = bool(total["pricing_known"]) and value.get("pricing_known") is True
    total["provider_call_count"] += _as_int(value.get("provider_call_count"))


def _copy_messages(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(json.dumps(dict(message), ensure_ascii=False, default=str)) for message in messages if isinstance(message, Mapping)]


def _sha256_json(value: Any) -> str:
    import hashlib

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _try_private_permissions(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":"), default=str))
            handle.write("\n")
    os.replace(temporary, path)
    _try_private_permissions(path)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _try_private_permissions(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
    _try_private_permissions(path)


def _try_private_permissions(path: Path) -> None:
    try:
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    except OSError:
        pass


def _prepend_import_path(path: Path) -> None:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _contains_unsafe_transport_receipt(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, raw in value.items():
            if str(key).startswith("raw_") and str(key).endswith("_persisted") and raw is True:
                return True
            if _contains_unsafe_transport_receipt(raw):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_unsafe_transport_receipt(item) for item in value)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
