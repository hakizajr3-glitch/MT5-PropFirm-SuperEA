"""Execution layer — sends AI Hedge Fund orders to TradeLocker.

Bridges the portfolio manager's TradeOrder objects to the existing TradeLocker
bot's API connection. Supports both live and dry-run modes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .agents.base import Action
from .portfolio_manager import TradeOrder

logger = logging.getLogger("ai_hedge_fund.executor")


@dataclass
class ExecutionResult:
    """Result of executing a single order."""
    symbol: str
    action: str
    success: bool
    order_id: str | None = None
    error: str | None = None
    dry_run: bool = False
    executed_at: str = ""


class TradeLockerExecutor:
    """Sends orders to TradeLocker via the existing API connection."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.api = None
        self._instrument_ids: dict[str, int | None] = {}
        self.execution_log: list[ExecutionResult] = []

    def connect(self, api) -> None:
        """Accept an existing TLAPI instance (shared with the dashboard/bot)."""
        self.api = api

    def _get_instrument_id(self, symbol: str) -> int | None:
        cached = self._instrument_ids.get(symbol)
        if cached is not None:
            return cached
        if self.api is None:
            return None
        for name in (symbol, f"{symbol}.R", f"{symbol}.r"):
            try:
                iid = self.api.get_instrument_id_from_symbol_name(name)
            except Exception:
                iid = None
            if iid is not None:
                self._instrument_ids[symbol] = iid
                return iid
        # don't cache misses — transient API errors shouldn't poison later calls
        return None

    def execute(self, order: TradeOrder) -> ExecutionResult:
        """Execute a single TradeOrder."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if self.dry_run:
            result = ExecutionResult(
                symbol=order.symbol, action=order.action.value,
                success=True, dry_run=True, executed_at=now,
            )
            logger.info("[DRY-RUN] %s %s qty=%.2f SL=%.5f TP=%.5f",
                        order.action.value, order.symbol, order.quantity,
                        order.stop_loss, order.take_profit)
            self.execution_log.append(result)
            return result

        if self.api is None:
            result = ExecutionResult(
                symbol=order.symbol, action=order.action.value,
                success=False, error="No API connection", executed_at=now,
            )
            self.execution_log.append(result)
            return result

        iid = self._get_instrument_id(order.symbol)
        if iid is None:
            result = ExecutionResult(
                symbol=order.symbol, action=order.action.value,
                success=False, error=f"Symbol {order.symbol} not found", executed_at=now,
            )
            self.execution_log.append(result)
            return result

        try:
            order_id = self.api.create_order(
                iid,
                quantity=order.quantity,
                side=order.side,
                type_="market",
                stop_loss=round(order.stop_loss, 5),
                stop_loss_type="absolute",
                take_profit=round(order.take_profit, 5),
                take_profit_type="absolute",
            )
            result = ExecutionResult(
                symbol=order.symbol, action=order.action.value,
                success=True, order_id=str(order_id), executed_at=now,
            )
            logger.info("EXECUTED: %s %s qty=%.2f order_id=%s",
                        order.action.value, order.symbol, order.quantity, order_id)
        except Exception as exc:
            result = ExecutionResult(
                symbol=order.symbol, action=order.action.value,
                success=False, error=str(exc), executed_at=now,
            )
            logger.error("EXECUTION FAILED: %s %s — %s",
                         order.action.value, order.symbol, exc)

        self.execution_log.append(result)
        return result

    def execute_batch(self, orders: list[TradeOrder]) -> list[ExecutionResult]:
        """Execute a list of orders sequentially."""
        return [self.execute(order) for order in orders]
