"""Risk Manager — aggregates agent signals and enforces prop-firm guardrails.

Sits between the agent layer and the Portfolio Manager.  Its job:
1. Collect all agent votes for a symbol.
2. Compute a weighted consensus (direction + aggregate confidence).
3. Block trades that would violate daily loss, max drawdown, or position limits.
4. Scale position size by aggregate confidence (higher conviction = larger size,
   but never exceeding the per-trade risk cap).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .agents.base import Action, AgentSignal

logger = logging.getLogger("ai_hedge_fund.risk_manager")


@dataclass
class RiskLimits:
    """Prop-firm risk parameters."""
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 5.0
    max_total_dd_pct: float = 10.0
    max_open_positions: int = 3
    max_portfolio_heat_pct: float = 6.0   # total open risk across all positions
    min_consensus_confidence: float = 0.4  # minimum to approve a trade
    min_agents_agree: int = 3              # at least N agents must agree on direction


@dataclass
class RiskVerdict:
    """Output of the Risk Manager for one symbol."""
    symbol: str
    approved: bool
    direction: Action                      # consensus direction
    consensus_confidence: float            # 0..1
    risk_pct: float                        # approved risk % of balance
    agents_agree: int
    agents_total: int
    votes_summary: list[dict]              # per-agent vote breakdown
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)


class RiskManagerAgent:
    """Aggregates agent signals, enforces guardrails, sizes risk."""

    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def evaluate(
        self,
        symbol: str,
        signals: list[AgentSignal],
        equity: float,
        day_start_equity: float,
        peak_equity: float,
        current_daily_pnl: float,
        open_position_count: int,
        open_risk_pct: float,
    ) -> RiskVerdict:
        lim = self.limits
        votes_summary = [
            {
                "agent": s.agent_name,
                "action": s.action.value,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
                "weight": s.weight,
            }
            for s in signals
        ]

        # weighted vote tallying
        buy_score = sum(s.confidence * s.weight for s in signals if s.action in (Action.BUY, Action.COVER))
        sell_score = sum(s.confidence * s.weight for s in signals if s.action in (Action.SELL, Action.SHORT))
        buy_count = sum(1 for s in signals if s.action in (Action.BUY, Action.COVER))
        sell_count = sum(1 for s in signals if s.action in (Action.SELL, Action.SHORT))

        if buy_score > sell_score:
            direction = Action.BUY
            consensus_confidence = buy_score / max(sum(s.weight for s in signals), 1.0)
            agents_agree = buy_count
        elif sell_score > buy_score:
            direction = Action.SELL
            consensus_confidence = sell_score / max(sum(s.weight for s in signals), 1.0)
            agents_agree = sell_count
        else:
            direction = Action.HOLD
            consensus_confidence = 0.0
            agents_agree = 0

        consensus_confidence = round(min(consensus_confidence, 1.0), 3)

        # pre-compute candidate risk for projected-impact checks
        if direction != Action.HOLD and consensus_confidence >= lim.min_consensus_confidence:
            scale = min(1.0, (consensus_confidence - 0.3) / 0.7)
            candidate_risk_pct = round(lim.max_risk_per_trade_pct * max(0.3, scale), 3)
        else:
            candidate_risk_pct = 0.0

        # risk checks
        blocked = []
        reasons = []

        # daily loss check
        if day_start_equity > 0:
            daily_loss_pct = max(0, (day_start_equity - equity) / day_start_equity * 100)
            if daily_loss_pct >= lim.max_daily_loss_pct:
                blocked.append(f"Daily loss {daily_loss_pct:.2f}% >= {lim.max_daily_loss_pct}%")
            else:
                remaining = lim.max_daily_loss_pct - daily_loss_pct
                reasons.append(f"Daily loss headroom: {remaining:.2f}%")

        # total drawdown check
        if peak_equity > 0:
            total_dd_pct = max(0, (peak_equity - equity) / peak_equity * 100)
            if total_dd_pct >= lim.max_total_dd_pct:
                blocked.append(f"Total DD {total_dd_pct:.2f}% >= {lim.max_total_dd_pct}%")
            else:
                remaining = lim.max_total_dd_pct - total_dd_pct
                reasons.append(f"DD headroom: {remaining:.2f}%")

        # position count
        if open_position_count >= lim.max_open_positions:
            blocked.append(f"Max positions reached ({open_position_count}/{lim.max_open_positions})")

        # portfolio heat (include projected impact of this trade)
        projected_heat = open_risk_pct + candidate_risk_pct
        if projected_heat > lim.max_portfolio_heat_pct:
            blocked.append(f"Portfolio heat {open_risk_pct:.2f}% + {candidate_risk_pct:.2f}% = {projected_heat:.2f}% > {lim.max_portfolio_heat_pct}%")

        # consensus checks
        if direction == Action.HOLD:
            blocked.append("No directional consensus")
        elif consensus_confidence < lim.min_consensus_confidence:
            blocked.append(f"Confidence {consensus_confidence:.2f} < {lim.min_consensus_confidence}")
        elif agents_agree < lim.min_agents_agree:
            blocked.append(f"Only {agents_agree} agents agree (need {lim.min_agents_agree})")

        approved = len(blocked) == 0

        # finalise risk
        risk_pct = candidate_risk_pct if approved else 0.0

        if approved:
            reasons.append(f"Approved: {direction.value} at {risk_pct}% risk, "
                           f"confidence={consensus_confidence}, {agents_agree}/{len(signals)} agents agree")
            logger.info("RISK APPROVED %s %s conf=%.2f risk=%.3f%%",
                        symbol, direction.value, consensus_confidence, risk_pct)
        else:
            logger.info("RISK BLOCKED %s: %s", symbol, "; ".join(blocked))

        return RiskVerdict(
            symbol=symbol,
            approved=approved,
            direction=direction,
            consensus_confidence=consensus_confidence,
            risk_pct=risk_pct,
            agents_agree=agents_agree,
            agents_total=len(signals),
            votes_summary=votes_summary,
            reasons=reasons,
            blocked_reasons=blocked,
        )
