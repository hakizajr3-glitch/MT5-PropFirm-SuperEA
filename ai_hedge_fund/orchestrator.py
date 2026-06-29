"""Orchestrator — runs the full AI Hedge Fund pipeline.

Pipeline flow (matches the user's diagram):
  [1] Pick agents  ->  All 7 investor agents analyse each symbol
  [2] Trading signals  ->  Each agent emits a signal
  [3] Risk Manager  ->  Aggregates, filters, applies guardrails
  [4] Portfolio Manager  ->  Final decision: BUY / SELL / SHORT / COVER / HOLD
  [5] Execution  ->  Send to TradeLocker / MT5

The orchestrator is the glue. It instantiates all agents, feeds them market
data, collects signals, routes through risk and portfolio management, and
returns executable orders (or passes them to the execution layer).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .agents import ALL_AGENTS
from .agents.base import Action, AgentSignal, BaseAgent, MarketSnapshot
from .risk_manager import RiskLimits, RiskManagerAgent, RiskVerdict
from .portfolio_manager import PortfolioDecision, PortfolioManagerAgent, TradeOrder

logger = logging.getLogger("ai_hedge_fund.orchestrator")


@dataclass
class PipelineResult:
    """Full result of one orchestrator cycle for one symbol."""
    symbol: str
    agent_signals: list[AgentSignal]
    risk_verdict: RiskVerdict
    portfolio_decision: PortfolioDecision
    order: TradeOrder | None = None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "agent_signals": [
                {
                    "agent": s.agent_name,
                    "action": s.action.value,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                    "indicators": s.indicators,
                    "weight": s.weight,
                }
                for s in self.agent_signals
            ],
            "risk_verdict": {
                "approved": self.risk_verdict.approved,
                "direction": self.risk_verdict.direction.value,
                "consensus_confidence": self.risk_verdict.consensus_confidence,
                "risk_pct": self.risk_verdict.risk_pct,
                "agents_agree": self.risk_verdict.agents_agree,
                "agents_total": self.risk_verdict.agents_total,
                "reasons": self.risk_verdict.reasons,
                "blocked_reasons": self.risk_verdict.blocked_reasons,
            },
            "portfolio_decision": {
                "action": self.portfolio_decision.action.value,
                "reasoning": self.portfolio_decision.reasoning,
            },
            "order": {
                "side": self.order.side,
                "quantity": self.order.quantity,
                "entry_price": self.order.entry_price,
                "stop_loss": self.order.stop_loss,
                "take_profit": self.order.take_profit,
                "risk_pct": self.order.risk_pct,
                "confidence": self.order.confidence,
            } if self.order else None,
        }


@dataclass
class CycleReport:
    """Result of a full orchestrator cycle across all symbols."""
    results: list[PipelineResult] = field(default_factory=list)
    orders: list[TradeOrder] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "results": [r.as_dict() for r in self.results],
            "orders": [
                {
                    "symbol": o.symbol,
                    "action": o.action.value,
                    "side": o.side,
                    "quantity": o.quantity,
                    "entry_price": o.entry_price,
                    "stop_loss": o.stop_loss,
                    "take_profit": o.take_profit,
                    "risk_pct": o.risk_pct,
                    "confidence": o.confidence,
                }
                for o in self.orders
            ],
        }


class Orchestrator:
    """Runs the multi-agent pipeline for a set of symbols."""

    def __init__(
        self,
        risk_limits: RiskLimits | None = None,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.5,
        contract_size: float = 100_000.0,
    ):
        self.agents: list[BaseAgent] = [cls() for cls in ALL_AGENTS]
        self.risk_manager = RiskManagerAgent(risk_limits)
        self.portfolio_manager = PortfolioManagerAgent(
            sl_atr_mult=sl_atr_mult,
            tp_atr_mult=tp_atr_mult,
            contract_size=contract_size,
        )

    def run_symbol(
        self,
        snapshot: MarketSnapshot,
        equity: float,
        balance: float,
        day_start_equity: float,
        peak_equity: float,
        current_daily_pnl: float = 0.0,
        open_position_count: int = 0,
        open_risk_pct: float = 0.0,
    ) -> PipelineResult:
        """Run the full pipeline for a single symbol."""

        # Step 1+2: all agents analyse independently
        signals: list[AgentSignal] = []
        for agent in self.agents:
            try:
                sig = agent.analyze(snapshot)
                signals.append(sig)
            except Exception as exc:
                logger.error("Agent %s failed on %s: %s", agent.name, snapshot.symbol, exc)
                signals.append(AgentSignal(
                    agent_name=agent.name, symbol=snapshot.symbol,
                    action=Action.HOLD, confidence=0.0,
                    reasoning=f"Agent error: {exc}", weight=agent.default_weight,
                ))

        # Step 3: Risk Manager
        verdict = self.risk_manager.evaluate(
            symbol=snapshot.symbol,
            signals=signals,
            equity=equity,
            day_start_equity=day_start_equity,
            peak_equity=peak_equity,
            current_daily_pnl=current_daily_pnl,
            open_position_count=open_position_count,
            open_risk_pct=open_risk_pct,
        )

        # Step 4: Portfolio Manager
        decision = self.portfolio_manager.decide(
            verdict=verdict,
            snapshot=snapshot,
            balance=balance,
        )

        return PipelineResult(
            symbol=snapshot.symbol,
            agent_signals=signals,
            risk_verdict=verdict,
            portfolio_decision=decision,
            order=decision.order,
        )

    def run_cycle(
        self,
        snapshots: list[MarketSnapshot],
        equity: float,
        balance: float,
        day_start_equity: float,
        peak_equity: float,
        current_daily_pnl: float = 0.0,
        open_position_count: int = 0,
        open_risk_pct: float = 0.0,
    ) -> CycleReport:
        """Run the full pipeline for multiple symbols."""
        report = CycleReport()

        for snapshot in snapshots:
            result = self.run_symbol(
                snapshot=snapshot,
                equity=equity,
                balance=balance,
                day_start_equity=day_start_equity,
                peak_equity=peak_equity,
                current_daily_pnl=current_daily_pnl,
                open_position_count=open_position_count,
                open_risk_pct=open_risk_pct,
            )
            report.results.append(result)
            if result.order is not None:
                report.orders.append(result.order)
                # update running counts for next symbol
                open_position_count += 1
                open_risk_pct += result.order.risk_pct

        if report.orders:
            logger.info("Cycle complete: %d orders across %d symbols",
                        len(report.orders), len(snapshots))
        else:
            logger.info("Cycle complete: no orders (all symbols HOLD)")

        return report
