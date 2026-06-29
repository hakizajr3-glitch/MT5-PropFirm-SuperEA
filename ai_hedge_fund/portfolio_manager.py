"""Portfolio Manager — makes final trading decisions.

Receives risk-approved verdicts and decides the exact action:
- BUY / SELL: open a new position
- COVER: close an existing short
- SHORT: open a short position
- HOLD: do nothing

Also determines position sizing (quantity), stop loss, and take profit based
on ATR and the risk budget allocated by the Risk Manager.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from tradelocker_bot.strategy import atr as calc_atr

from .agents.base import Action, MarketSnapshot
from .risk_manager import RiskVerdict

logger = logging.getLogger("ai_hedge_fund.portfolio_manager")


@dataclass
class TradeOrder:
    """A concrete order ready for the execution layer."""
    symbol: str
    action: Action
    side: str           # "buy" or "sell"
    quantity: float
    entry_price: float  # approximate (market order)
    stop_loss: float
    take_profit: float
    risk_pct: float
    confidence: float
    reasoning: str
    agent_votes: list[dict] = field(default_factory=list)


@dataclass
class PortfolioDecision:
    """Output of the Portfolio Manager for one symbol."""
    symbol: str
    action: Action
    order: TradeOrder | None = None
    reasoning: str = ""
    risk_verdict: RiskVerdict | None = None


class PortfolioManagerAgent:
    """Makes the final call and constructs executable orders."""

    def __init__(
        self,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.5,
        atr_period: int = 14,
        contract_size: float = 100_000.0,
    ):
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.atr_period = atr_period
        self.contract_size = contract_size

    def decide(
        self,
        verdict: RiskVerdict,
        snapshot: MarketSnapshot,
        balance: float,
    ) -> PortfolioDecision:
        if not verdict.approved:
            return PortfolioDecision(
                symbol=verdict.symbol,
                action=Action.HOLD,
                reasoning="Blocked by Risk Manager: " + "; ".join(verdict.blocked_reasons),
                risk_verdict=verdict,
            )

        df = snapshot.bars
        price = float(df["close"].iloc[-1])
        atr_val = float(calc_atr(df, self.atr_period).iloc[-1])

        if atr_val <= 0:
            return PortfolioDecision(
                symbol=verdict.symbol, action=Action.HOLD,
                reasoning="ATR is zero — cannot calculate stops",
                risk_verdict=verdict,
            )

        direction = verdict.direction
        side = "buy" if direction in (Action.BUY, Action.COVER) else "sell"

        # compute SL/TP
        sl_dist = atr_val * self.sl_atr_mult
        tp_dist = atr_val * self.tp_atr_mult

        if side == "buy":
            sl = price - sl_dist
            tp = price + tp_dist
        else:
            sl = price + sl_dist
            tp = price - tp_dist

        # position sizing from risk budget
        risk_money = balance * verdict.risk_pct / 100.0
        loss_per_qty = sl_dist * self.contract_size
        if loss_per_qty > 0:
            qty = risk_money / loss_per_qty
        else:
            qty = 0.01

        # floor to 0.01 lots
        qty = max(0.01, round(qty, 2))

        reasoning = (f"PM decision: {direction.value} {snapshot.symbol} "
                     f"qty={qty:.2f} @ ~{price:.5f}, "
                     f"SL={sl:.5f}, TP={tp:.5f}, "
                     f"risk={verdict.risk_pct}%, "
                     f"confidence={verdict.consensus_confidence:.2f}, "
                     f"{verdict.agents_agree}/{verdict.agents_total} agents agree")

        order = TradeOrder(
            symbol=snapshot.symbol,
            action=direction,
            side=side,
            quantity=qty,
            entry_price=round(price, 5),
            stop_loss=round(sl, 5),
            take_profit=round(tp, 5),
            risk_pct=verdict.risk_pct,
            confidence=verdict.consensus_confidence,
            reasoning=reasoning,
            agent_votes=verdict.votes_summary,
        )

        logger.info("PM ORDER: %s %s qty=%.2f SL=%.5f TP=%.5f",
                    direction.value, snapshot.symbol, qty, sl, tp)

        return PortfolioDecision(
            symbol=verdict.symbol,
            action=direction,
            order=order,
            reasoning=reasoning,
            risk_verdict=verdict,
        )
