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
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
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
    reason_code: str = ""


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

    def recover(
        self,
        *,
        reservation_id: str,
        recovery_key: str,
        reason: str,
    ) -> LedgerSettlement:
        """由 operator 明确回收疑似崩溃遗留的 active reservation。"""

    def snapshot(
        self,
        *,
        day: str,
        limit: int = 20,
        tenant_hash: str | None = None,
    ) -> dict[str, Any]:
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

    def recover(
        self,
        *,
        reservation_id: str,
        recovery_key: str,
        reason: str,
    ) -> LedgerSettlement:
        _validate_recovery_inputs(reservation_id, recovery_key, reason)
        with self._lock:
            self._ensure_available_unlocked("release")
            record = self._get_record_unlocked(reservation_id)
            if record.settlement is not None:
                return _replayed_settlement(record.settlement)
            return self._release_unlocked(
                record,
                idempotent_replay=False,
                reason_code="tenant_budget_reservation_recovered",
            )

    def snapshot(
        self,
        *,
        day: str,
        limit: int = 20,
        tenant_hash: str | None = None,
    ) -> dict[str, Any]:
        if int(limit) <= 0:
            limit = 1
        with self._lock:
            self._ensure_available_unlocked("snapshot")
            rows: list[dict[str, Any]] = []
            accounts = {
                account
                for account in set(self._committed) | set(self._reserved)
                if account[1] == str(day)
                and (tenant_hash is None or account[0] == str(tenant_hash))
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

    def _release_unlocked(
        self,
        record: _ReservationRecord,
        *,
        idempotent_replay: bool,
        reason_code: str = "",
    ) -> LedgerSettlement:
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
            reason_code=reason_code,
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


class SQLiteTenantBudgetLedger:
    """基于 SQLite 的跨进程账本适配器。

    SQLite 适合单主机多进程部署：每次写操作使用 ``BEGIN IMMEDIATE``，把预算
    检查、预留/结算和幂等状态变更放在同一个事务中。它不是跨主机分布式账本，
    因此生产部署必须把数据库文件放在可靠的共享本地卷，并继续由部署合同明确
    该边界；不能把本适配器宣传成 Redis/SQL 集群的替代品。
    """

    backend_name = "sqlite_shared_file"

    def __init__(self, path: str, *, timeout_seconds: float = 5.0) -> None:
        normalized = os.path.abspath(os.path.expanduser(str(path or "").strip()))
        if not normalized or normalized == os.path.abspath(os.sep):
            raise ValueError("a dedicated sqlite ledger path is required")
        timeout = _finite_nonnegative(timeout_seconds)
        if timeout is None or timeout <= 0.0:
            raise ValueError("sqlite timeout must be finite and positive")
        parent = os.path.dirname(normalized)
        if not parent or not os.path.isdir(parent):
            raise ValueError("sqlite ledger parent directory must already exist")
        self.path = normalized
        self._timeout_seconds = float(timeout)
        self._initialize()

    def reserve(
        self,
        *,
        tenant_hash: str,
        day: str,
        amount_usd: float,
        budget_usd: float,
        reservation_key: str,
    ) -> LedgerReservation:
        _validate_ledger_inputs(tenant_hash, day, reservation_key, amount_usd, budget_usd)
        amount = float(amount_usd)
        budget = float(budget_usd)
        try:
            with self._transaction() as connection:
                existing = connection.execute(
                    "SELECT * FROM reservations WHERE tenant_hash=? AND day=? AND reservation_key=?",
                    (str(tenant_hash), str(day), str(reservation_key)),
                ).fetchone()
                if existing is not None:
                    return self._reservation_result(connection, existing, idempotent_replay=True)
                account = self._account(connection, str(tenant_hash), str(day), budget)
                committed = float(account["committed_usd"])
                reserved = float(account["reserved_usd"])
                if committed + reserved + amount > budget + 1e-12:
                    return LedgerReservation(
                        reservation_id="",
                        tenant_hash=str(tenant_hash),
                        day=str(day),
                        amount_usd=_rounded(amount),
                        budget_usd=_rounded(budget),
                        committed_usd=_rounded(committed),
                        reserved_usd=_rounded(reserved),
                        allowed=False,
                        reason_code="tenant_budget_exhausted",
                    )
                reservation_id = uuid.uuid4().hex
                connection.execute(
                    "INSERT INTO reservations "
                    "(reservation_id, tenant_hash, day, reservation_key, amount_usd, budget_usd, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
                    (reservation_id, str(tenant_hash), str(day), str(reservation_key), amount, budget, time.time()),
                )
                connection.execute(
                    "UPDATE accounts SET reserved_usd=?, updated_at=? WHERE tenant_hash=? AND day=?",
                    (reserved + amount, time.time(), str(tenant_hash), str(day)),
                )
                row = connection.execute(
                    "SELECT * FROM reservations WHERE reservation_id=?", (reservation_id,)
                ).fetchone()
                return self._reservation_result(connection, row)
        except TenantBudgetLedgerError:
            raise
        except sqlite3.IntegrityError as error:
            raise TenantBudgetLedgerInvariantError("sqlite ledger reservation invariant failed") from error
        except sqlite3.Error as error:
            raise TenantBudgetLedgerUnavailable("sqlite ledger reserve failed") from error

    def settle(
        self,
        *,
        reservation_id: str,
        actual_cost_usd: float | None,
        success: bool,
    ) -> LedgerSettlement:
        try:
            with self._transaction() as connection:
                row = self._reservation(connection, reservation_id)
                if row["status"] != "active":
                    return self._settlement_result(connection, row, idempotent_replay=True)
                if not success:
                    return self._release_row(connection, row, idempotent_replay=False)
                actual = row["amount_usd"] if actual_cost_usd is None else _finite_nonnegative(actual_cost_usd)
                if actual is None:
                    raise TenantBudgetLedgerInvariantError("actual cost must be finite and non-negative")
                account = self._account(connection, row["tenant_hash"], row["day"], row["budget_usd"])
                committed = float(account["committed_usd"])
                reserved = max(0.0, float(account["reserved_usd"]) - float(row["amount_usd"]))
                overcommit = committed + float(actual) > float(row["budget_usd"]) + 1e-12
                connection.execute(
                    "UPDATE accounts SET committed_usd=?, reserved_usd=?, updated_at=? WHERE tenant_hash=? AND day=?",
                    (committed + float(actual), reserved, time.time(), row["tenant_hash"], row["day"]),
                )
                connection.execute(
                    "UPDATE reservations SET status='settled', actual_cost_usd=?, overcommit=?, settled_at=? "
                    " , settled_committed_usd=?, settled_reserved_usd=? WHERE reservation_id=?",
                    (
                        float(actual),
                        int(overcommit),
                        time.time(),
                        committed + float(actual),
                        reserved,
                        row["reservation_id"],
                    ),
                )
                updated = self._reservation(connection, row["reservation_id"])
                return self._settlement_result(connection, updated)
        except TenantBudgetLedgerError:
            raise
        except sqlite3.Error as error:
            raise TenantBudgetLedgerUnavailable("sqlite ledger settle failed") from error

    def release(self, *, reservation_id: str) -> LedgerSettlement:
        try:
            with self._transaction() as connection:
                row = self._reservation(connection, reservation_id)
                if row["status"] != "active":
                    return self._settlement_result(connection, row, idempotent_replay=True)
                return self._release_row(connection, row, idempotent_replay=False)
        except TenantBudgetLedgerError:
            raise
        except sqlite3.Error as error:
            raise TenantBudgetLedgerUnavailable("sqlite ledger release failed") from error

    def recover(
        self,
        *,
        reservation_id: str,
        recovery_key: str,
        reason: str,
    ) -> LedgerSettlement:
        _validate_recovery_inputs(reservation_id, recovery_key, reason)
        try:
            with self._transaction() as connection:
                row = self._reservation(connection, reservation_id)
                if row["status"] != "active":
                    return self._settlement_result(connection, row, idempotent_replay=True)
                return self._release_row(
                    connection,
                    row,
                    idempotent_replay=False,
                    reason_code="tenant_budget_reservation_recovered",
                )
        except TenantBudgetLedgerError:
            raise
        except sqlite3.Error as error:
            raise TenantBudgetLedgerUnavailable("sqlite ledger recovery failed") from error

    def snapshot(
        self,
        *,
        day: str,
        limit: int = 20,
        tenant_hash: str | None = None,
    ) -> dict[str, Any]:
        if not str(day).strip():
            raise TenantBudgetLedgerInvariantError("day is required")
        bounded_limit = max(1, min(int(limit), 1000))
        try:
            with self._connect() as connection:
                if tenant_hash is None:
                    rows = connection.execute(
                        "SELECT tenant_hash, day, committed_usd, reserved_usd, budget_usd "
                        "FROM accounts WHERE day=? ORDER BY (committed_usd + reserved_usd) DESC, tenant_hash LIMIT ?",
                        (str(day), bounded_limit),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT tenant_hash, day, committed_usd, reserved_usd, budget_usd "
                        "FROM accounts WHERE day=? AND tenant_hash=? LIMIT 1",
                        (str(day), str(tenant_hash)),
                    ).fetchall()
                safe_rows = [
                    {
                        "tenant_sha256": str(row["tenant_hash"]),
                        "day": str(row["day"]),
                        "budget_usd": _rounded(row["budget_usd"]),
                        "committed_usd": _rounded(row["committed_usd"]),
                        "reserved_usd": _rounded(row["reserved_usd"]),
                        "committed_plus_reserved_usd": _rounded(
                            float(row["committed_usd"]) + float(row["reserved_usd"])
                        ),
                        "raw_tenant_key_persisted": False,
                        "raw_api_key_persisted": False,
                        "secrets_persisted": False,
                    }
                    for row in rows
                ]
                return {
                    "schema": "axio_fusion_api.tenant_budget_ledger_snapshot.v1",
                    "backend": self.backend_name,
                    "available": True,
                    "tenant_count": len(safe_rows),
                    "rows": safe_rows,
                    "raw_tenant_keys_persisted": False,
                    "raw_api_keys_persisted": False,
                    "secrets_persisted": False,
                }
        except sqlite3.Error as error:
            raise TenantBudgetLedgerUnavailable("sqlite ledger snapshot failed") from error

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    "CREATE TABLE IF NOT EXISTS accounts ("
                    "tenant_hash TEXT NOT NULL, day TEXT NOT NULL, budget_usd REAL NOT NULL, "
                    "committed_usd REAL NOT NULL DEFAULT 0, reserved_usd REAL NOT NULL DEFAULT 0, "
                    "updated_at REAL NOT NULL, PRIMARY KEY (tenant_hash, day));"
                    "CREATE TABLE IF NOT EXISTS reservations ("
                    "reservation_id TEXT PRIMARY KEY, tenant_hash TEXT NOT NULL, day TEXT NOT NULL, "
                    "reservation_key TEXT NOT NULL, amount_usd REAL NOT NULL, budget_usd REAL NOT NULL, "
                    "status TEXT NOT NULL, actual_cost_usd REAL, overcommit INTEGER NOT NULL DEFAULT 0, "
                    "created_at REAL NOT NULL, settled_at REAL, settled_committed_usd REAL, "
                    "settled_reserved_usd REAL, settlement_reason_code TEXT NOT NULL DEFAULT '', "
                    "UNIQUE (tenant_hash, day, reservation_key));"
                    "CREATE INDEX IF NOT EXISTS reservations_status_idx ON reservations(status, day);"
                )
                columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(reservations)").fetchall()
                }
                for column in (
                    "settled_committed_usd",
                    "settled_reserved_usd",
                    "settlement_reason_code",
                ):
                    if column not in columns:
                        column_type = "TEXT NOT NULL DEFAULT ''" if column == "settlement_reason_code" else "REAL"
                        connection.execute(f"ALTER TABLE reservations ADD COLUMN {column} {column_type}")
        except sqlite3.Error as error:
            raise TenantBudgetLedgerUnavailable("sqlite ledger initialization failed") from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=self._timeout_seconds, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {int(self._timeout_seconds * 1000)}")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def _transaction(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @staticmethod
    def _account(connection: sqlite3.Connection, tenant_hash: str, day: str, budget: float) -> sqlite3.Row:
        connection.execute(
            "INSERT INTO accounts (tenant_hash, day, budget_usd, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(tenant_hash, day) DO UPDATE SET budget_usd=excluded.budget_usd, updated_at=excluded.updated_at",
            (tenant_hash, day, budget, time.time()),
        )
        return connection.execute(
            "SELECT * FROM accounts WHERE tenant_hash=? AND day=?", (tenant_hash, day)
        ).fetchone()

    @staticmethod
    def _reservation(connection: sqlite3.Connection, reservation_id: str) -> sqlite3.Row:
        identifier = str(reservation_id or "").strip()
        if not identifier:
            raise TenantBudgetLedgerInvariantError("reservation id is required")
        row = connection.execute(
            "SELECT * FROM reservations WHERE reservation_id=?", (identifier,)
        ).fetchone()
        if row is None:
            raise TenantBudgetLedgerInvariantError("unknown reservation id")
        return row

    @staticmethod
    def _reservation_result(
        connection: sqlite3.Connection, row: sqlite3.Row, *, idempotent_replay: bool = False
    ) -> LedgerReservation:
        account = SQLiteTenantBudgetLedger._account(connection, row["tenant_hash"], row["day"], row["budget_usd"])
        return LedgerReservation(
            reservation_id=str(row["reservation_id"]),
            tenant_hash=str(row["tenant_hash"]),
            day=str(row["day"]),
            amount_usd=_rounded(row["amount_usd"]),
            budget_usd=_rounded(row["budget_usd"]),
            committed_usd=_rounded(account["committed_usd"]),
            reserved_usd=_rounded(account["reserved_usd"]),
            allowed=row["status"] == "active",
            reason_code="" if row["status"] == "active" else "reservation_already_finalized",
            idempotent_replay=idempotent_replay,
        )

    @staticmethod
    def _settlement_result(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        idempotent_replay: bool = False,
    ) -> LedgerSettlement:
        account = SQLiteTenantBudgetLedger._account(connection, row["tenant_hash"], row["day"], row["budget_usd"])
        committed_value = row["settled_committed_usd"]
        reserved_value = row["settled_reserved_usd"]
        if committed_value is None or reserved_value is None:
            committed_value = account["committed_usd"]
            reserved_value = account["reserved_usd"]
        return LedgerSettlement(
            reservation_id=str(row["reservation_id"]),
            status=str(row["status"]),
            committed_usd=_rounded(committed_value),
            reserved_usd=_rounded(reserved_value),
            actual_cost_usd=(
                None if row["actual_cost_usd"] is None else _rounded(row["actual_cost_usd"])
            ),
            overcommit=bool(row["overcommit"]),
            idempotent_replay=idempotent_replay,
            reason_code=str(row["settlement_reason_code"] or ""),
        )

    @staticmethod
    def _release_row(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        idempotent_replay: bool,
        reason_code: str = "",
    ) -> LedgerSettlement:
        account = SQLiteTenantBudgetLedger._account(connection, row["tenant_hash"], row["day"], row["budget_usd"])
        reserved = max(0.0, float(account["reserved_usd"]) - float(row["amount_usd"]))
        connection.execute(
            "UPDATE accounts SET reserved_usd=?, updated_at=? WHERE tenant_hash=? AND day=?",
            (reserved, time.time(), row["tenant_hash"], row["day"]),
        )
        connection.execute(
            "UPDATE reservations SET status='released', settled_at=?, settled_committed_usd=?, "
            "settled_reserved_usd=?, settlement_reason_code=? WHERE reservation_id=?",
            (
                time.time(),
                float(account["committed_usd"]),
                reserved,
                reason_code,
                row["reservation_id"],
            ),
        )
        updated = SQLiteTenantBudgetLedger._reservation(connection, row["reservation_id"])
        account = SQLiteTenantBudgetLedger._account(connection, row["tenant_hash"], row["day"], row["budget_usd"])
        return LedgerSettlement(
            reservation_id=str(updated["reservation_id"]),
            status="released",
            committed_usd=_rounded(account["committed_usd"]),
            reserved_usd=_rounded(account["reserved_usd"]),
            actual_cost_usd=None,
            overcommit=False,
            idempotent_replay=idempotent_replay,
            reason_code=reason_code,
        )


def _replayed_settlement(value: LedgerSettlement) -> LedgerSettlement:
    return LedgerSettlement(
        reservation_id=value.reservation_id,
        status=value.status,
        committed_usd=value.committed_usd,
        reserved_usd=value.reserved_usd,
        actual_cost_usd=value.actual_cost_usd,
        overcommit=value.overcommit,
        idempotent_replay=True,
        reason_code=value.reason_code,
    )


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None


def _validate_ledger_inputs(
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


def _validate_recovery_inputs(reservation_id: str, recovery_key: str, reason: str) -> None:
    if not str(reservation_id).strip() or not str(recovery_key).strip():
        raise TenantBudgetLedgerInvariantError("recovery reservation id and key are required")
    if len(str(reason).strip()) < 8:
        raise TenantBudgetLedgerInvariantError("recovery reason must contain at least 8 characters")


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
    "SQLiteTenantBudgetLedger",
]
