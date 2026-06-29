"""AI Hedge Fund — multi-agent trading intelligence layer.

Seven investor-philosophy agents analyse the market independently, a Risk
Manager aggregates and filters their signals through prop-firm guardrails, and
a Portfolio Manager makes the final BUY / SELL / HOLD / SHORT / COVER decision
before handing off to the execution layer (TradeLocker / MT5).
"""
