"""Investor-philosophy agents for the AI Hedge Fund."""

from .base import AgentSignal, BaseAgent  # noqa: F401
from .graham import GrahamAgent  # noqa: F401
from .buffett import BuffettAgent  # noqa: F401
from .munger import MungerAgent  # noqa: F401
from .ackman import AckmanAgent  # noqa: F401
from .wood import WoodAgent  # noqa: F401
from .fisher import FisherAgent  # noqa: F401
from .druckenmiller import DruckenmillerAgent  # noqa: F401

ALL_AGENTS: list[type[BaseAgent]] = [
    GrahamAgent,
    BuffettAgent,
    MungerAgent,
    AckmanAgent,
    WoodAgent,
    FisherAgent,
    DruckenmillerAgent,
]
