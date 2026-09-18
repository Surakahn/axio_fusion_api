"""跨进程租户预算账本的最小可替换契约。

生产服务当前仍使用 :class:`axio_fusion_api.runtime.RuntimeState` 的进程内
账本。这个模块只定义将来共享后端必须满足的原子性和故障语义，并提供一个
线程安全的内存 fake backend，供离线集成测试模拟多个 RuntimeState/副本。

fake backend 不会被环境变量自动发现，也不提供持久化或跨进程能力；生产配置
必须显式注入一个实现了 ``TenantBudgetLedger`` 的真实后端。这样可以避免把
``process_local`` 的安全投影误报成全局租户配额。
"""

from __future__ import annotations

import math
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol


LedgerReservationStatus = Literal["active", "settled", "released"]


class TenantBudgetLedgerError(RuntimeError):
    """账本后端无法安全完成操作时抛出的基类异常。"""

    def __init__(self, reason_code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.reason_code = str(reason_code)
        self.retryable = bool(retryable)


class TenantBudgetLedgerUnavailable(TenantBudgetLedgerError):
    """共享后端不可达或被显式标记为不可用。"""

    def __init__(self, message: str = "Tenant budget ledger is unavailable") -> None:
        super().__init__(
            "tenant_budget_shared_backend_unavailable",
            message,
            retryable=True,
        )


class TenantBudgetLedgerInvariantError(TenantBudgetLedgerError):
    """发现未知 reservation 或非法账本状态；调用方必须 fail closed。"""

    def __init__(self, message: str = "Tenant budget ledger invariant failed") -> None:
        super().__init__(
            "tenant_budget_shared_backend_invariant_failed",
            message,
            retryable=False,
        )


@dataclass(frozen=True)
class LedgerReservation:
    """一次原子预留的安全结果。

    ``tenant_hash`` 只接受调用方已经脱敏的租户标识。实现不得把原始 tenant
    或 API key 写入后端 receipt。
    """

    reservation_id: str
    tenant_hash: str
    day: str
    amount_usd: float
    budget_usd: float
    committed_usd: float
    reserved_usd: float
    allowed: bool
    reason_code: str = ""
    idempotent_replay: bool = False


@dataclass(frozen=True)
class LedgerSettlement:
    """settle/release 的不可变结果。"""

    reservation_id: str
    status: LedgerReservationStatus
    committed_usd: float
    reserved_usd: float
    actual_cost_usd: float | None
    overcommit: bool = False
    idempotent_replay: bool = False


class TenantBudgetLedger(Protocol):
    """真实共享账本必须实现的最小原子接口。

    ``reserve`` 的检查和预留必须由后端在同一个原子事务/脚本中完成；仅仅在
    应用进程读取 snapshot 后再写回不满足此协议。``reservation_key`` 用于
    网络重试去重，后端必须保证同 tenant/day/key 不会产生两个 active lease。
    """

    backend_name: str

    def reserve(
        self,
        *,
        tenant_hash: str,
        day: str,
        amount_usd: float,
        budget_usd: float,
        reservation_key: str,
    ) -> LedgerReservation:
        """原子检查并创建 active reservation；后端失败必须抛出异常。"""

    def settle(
        self,
        *,
        reservation_id: str,
        actual_cost_usd: float | None,
        success: bool,
    ) -> LedgerSettlement:
        """提交实际成本，或在失败/取消时释放 reservation；必须幂等。"""

    def release(self, *, reservation_id: str) -> LedgerSettlement:
        """显式释放 active reservation；重复调用必须返回相同终态。"""

    def snapshot(self, *, day: str, limit: int = 20) -> dict[str, Any]:
        """返回 hash-only 运维投影，不得包含原始 tenant、prompt 或 secret。"""


@dataclass
class _ReservationRecord:
    reservation_id: str
    tenant_hash: str
    day: str
    amount_usd: float
    budget_usd: float
    status: LedgerReservationStatus
    actual_cost_usd: float | None = None
    overcommit: bool = False
    settlement: LedgerSettlement | None = None


class InMemoryTenantBudgetLedger:
    """线程安全 fake backend，用于离线多副本一致性测试。

    该实现故意提供可控的 ``set_available`` 和 ``fail_next`` 故障注入。它
    模拟一个共享原子账本的语义，但不跨进程、不落盘，也不应直接用于生产。
    """

    backend_name = "in_memory_test_only"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._available = True
        self._fail_next_operations: dict[str, int] = {}
        self._committed: dict[tuple[str, str], float] = {}
        self._reserved: dict[tuple[str, str], float] = {}
        self._reservations: dict[str, _ReservationRecord] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}

    def set_available(self, available: bool) -> None:
        """切换 fake backend 可用性，供故障恢复测试使用。"""

        with self._lock:
            self._available = bool(available)

    def fail_next(self, operation: str, count: int = 1) -> None:
        """让后续指定操作抛出一次可重试的 unavailable 错误。"""

        normalized = str(operation or "").strip().lower()
        if normalized not in {"reserve", "settle", "release", "snapshot"}:
            raise ValueError("unsupported ledger operation")
        if int(count) <= 0:
            return
        with self._lock:
            self._fail_next_operations[normalized] = int(count)

    def reserve(
        self,
        *,
        tenant_hash: str,
        day: str,
        amount_usd: float,
        budget_usd: float,
        reservation_key: str,
    ) -> LedgerReservation:
        self._validate_inputs(tenant_hash, day, reservation_key, amount_usd, budget_usd)
        with self._lock:
            self._ensure_available_unlocked("reserve")
            idempotency_key = (str(tenant_hash), str(day), str(reservation_key))
            existing_id = self._idempotency.get(idempotency_key)
            if existing_id:
                return self._reservation_result_unlocked(
                    self._reservations[existing_id], idempotent_replay=True
                )
            account = (str(tenant_hash), str(day))
            committed = self._committed.get(account, 0.0)
            reserved = self._reserved.get(account, 0.0)
            if committed + reserved + float(amount_usd) > float(budget_usd) + 1e-12:
                return LedgerReservation(
                    reservation_id="",
                    tenant_hash=str(tenant_hash),
                    day=str(day),
                    amount_usd=float(amount_usd),
                    budget_usd=float(budget_usd),
                    committed_usd=_rounded(committed),
                    reserved_usd=_rounded(reserved),
                    allowed=False,
                    reason_code="tenant_budget_exhausted",
                )
            reservation_id = uuid.uuid4().hex
            record = _ReservationRecord(
                reservation_id=reservation_id,
                tenant_hash=str(tenant_hash),
                day=str(day),
                amount_usd=float(amount_usd),
                budget_usd=float(budget_usd),
                status="active",
            )
            self._reservations[reservation_id] = record
            self._idempotency[idempotency_key] = reservation_id
            self._reserved[account] = reserved + float(amount_usd)
            return self._reservation_result_unlocked(record)

    def settle(
        self,
        *,
        reservation_id: str,
        actual_cost_usd: float | None,
        success: bool,
    ) -> LedgerSettlement:
        with self._lock:
            self._ensure_available_unlocked("settle")
            record = self._get_record_unlocked(reservation_id)
            if record.settlement is not None:
                return _replayed_settlement(record.settlement)
            if not success:
                return self._release_unlocked(record, idempotent_replay=False)
            actual = record.amount_usd if actual_cost_usd is None else _finite_nonnegative(actual_cost_usd)
            if actual is None:
                raise TenantBudgetLedgerInvariantError("actual cost must be finite and non-negative")
            account = (record.tenant_hash, record.day)
            committed = self._committed.get(account, 0.0)
            reserved = max(0.0, self._reserved.get(account, 0.0) - record.amount_usd)
            overcommit = committed + float(actual) > record.budget_usd + 1e-12
            self._reserved[account] = reserved
            self._committed[account] = committed + float(actual)
            record.status = "settled"
            record.actual_cost_usd = float(actual)
            record.overcommit = overcommit
            result = LedgerSettlement(
                reservation_id=record.reservation_id,
                status="settled",
                committed_usd=_rounded(self._committed[account]),
                reserved_usd=_rounded(reserved),
                actual_cost_usd=_rounded(actual),
                overcommit=overcommit,
            )
            record.settlement = result
            return result

    def release(self, *, reservation_id: str) -> LedgerSettlement:
        with self._lock:
            self._ensure_available_unlocked("release")
            record = self._get_record_unlocked(reservation_id)
            if record.settlement is not None:
                return _replayed_settlement(record.settlement)
            return self._release_unlocked(record, idempotent_replay=False)

    def snapshot(self, *, day: str, limit: int = 20) -> dict[str, Any]:
        if int(limit) <= 0:
            limit = 1
        with self._lock:
            self._ensure_available_unlocked("snapshot")
            rows: list[dict[str, Any]] = []
            accounts = {
                account
                for account in set(self._committed) | set(self._reserved)
                if account[1] == str(day)
            }
            for tenant_hash, account_day in accounts:
                if account_day != str(day):
                    continue
                committed = max(0.0, self._committed.get((tenant_hash, account_day), 0.0))
                reserved = max(0.0, self._reserved.get((tenant_hash, account_day), 0.0))
                rows.append(
                    {
                        "tenant_sha256": str(tenant_hash),
                        "day": str(account_day),
                        "committed_usd": _rounded(committed),
                        "reserved_usd": _rounded(reserved),
                        "committed_plus_reserved_usd": _rounded(committed + reserved),
                        "raw_tenant_key_persisted": False,
                        "raw_api_key_persisted": False,
                        "secrets_persisted": False,
                    }
                )
            rows.sort(key=lambda row: (-float(row["committed_plus_reserved_usd"]), row["tenant_sha256"]))
            return {
                "schema": "axio_fusion_api.tenant_budget_ledger_snapshot.v1",
                "backend": self.backend_name,
                "available": self._available,
                "tenant_count": len(accounts),
                "rows": rows[: int(limit)],
                "raw_tenant_keys_persisted": False,
                "raw_api_keys_persisted": False,
                "secrets_persisted": False,
            }

    def _release_unlocked(self, record: _ReservationRecord, *, idempotent_replay: bool) -> LedgerSettlement:
        account = (record.tenant_hash, record.day)
        reserved = max(0.0, self._reserved.get(account, 0.0) - record.amount_usd)
        self._reserved[account] = reserved
        record.status = "released"
        result = LedgerSettlement(
            reservation_id=record.reservation_id,
            status="released",
            committed_usd=_rounded(self._committed.get(account, 0.0)),
            reserved_usd=_rounded(reserved),
            actual_cost_usd=None,
            idempotent_replay=idempotent_replay,
        )
        record.settlement = result
        return result

    def _reservation_result_unlocked(
        self,
        record: _ReservationRecord,
        *,
        idempotent_replay: bool = False,
    ) -> LedgerReservation:
        account = (record.tenant_hash, record.day)
        return LedgerReservation(
            reservation_id=record.reservation_id,
            tenant_hash=record.tenant_hash,
            day=record.day,
            amount_usd=_rounded(record.amount_usd),
            budget_usd=_rounded(record.budget_usd),
            committed_usd=_rounded(self._committed.get(account, 0.0)),
            reserved_usd=_rounded(self._reserved.get(account, 0.0)),
            allowed=record.status == "active",
            reason_code="" if record.status == "active" else "reservation_already_finalized",
            idempotent_replay=idempotent_replay,
        )

    def _get_record_unlocked(self, reservation_id: str) -> _ReservationRecord:
        identifier = str(reservation_id or "").strip()
        record = self._reservations.get(identifier)
        if record is None:
            raise TenantBudgetLedgerInvariantError("unknown reservation id")
        return record

    def _ensure_available_unlocked(self, operation: str) -> None:
        remaining_failures = self._fail_next_operations.get(operation, 0)
        if remaining_failures > 0:
            self._fail_next_operations[operation] = remaining_failures - 1
            raise TenantBudgetLedgerUnavailable(f"fake ledger {operation} failure")
        if not self._available:
            raise TenantBudgetLedgerUnavailable(f"fake ledger {operation} unavailable")

    @staticmethod
    def _validate_inputs(
        tenant_hash: str,
        day: str,
        reservation_key: str,
        amount_usd: float,
        budget_usd: float,
    ) -> None:
        if not str(tenant_hash).strip() or not str(day).strip() or not str(reservation_key).strip():
            raise TenantBudgetLedgerInvariantError("tenant hash, day and reservation key are required")
        if _finite_nonnegative(amount_usd) is None or _finite_nonnegative(budget_usd) is None:
            raise TenantBudgetLedgerInvariantError("budget values must be finite and non-negative")


def _replayed_settlement(value: LedgerSettlement) -> LedgerSettlement:
    return LedgerSettlement(
        reservation_id=value.reservation_id,
        status=value.status,
        committed_usd=value.committed_usd,
        reserved_usd=value.reserved_usd,
        actual_cost_usd=value.actual_cost_usd,
        overcommit=value.overcommit,
        idempotent_replay=True,
    )


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


def _rounded(value: float) -> float:
    return round(float(value), 8)


__all__ = [
    "InMemoryTenantBudgetLedger",
    "LedgerReservation",
    "LedgerReservationStatus",
    "LedgerSettlement",
    "TenantBudgetLedger",
    "TenantBudgetLedgerError",
    "TenantBudgetLedgerInvariantError",
    "TenantBudgetLedgerUnavailable",
]
