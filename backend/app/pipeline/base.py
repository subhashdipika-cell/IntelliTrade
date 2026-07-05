"""Base class for pipeline stages. Concrete brokers / models / strategies are
plain subclasses for now. We intentionally do NOT introduce a plugin/registry
abstraction yet — that gets extracted once a third concrete strategy exists and
the real seams are known."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.logging_setup import get_logger
from app.pipeline.context import TradeContext


class Stage(ABC):
    name: str = "stage"

    def __init__(self) -> None:
        self.log = get_logger(f"pipeline.{self.name}")

    @abstractmethod
    def process(self, ctx: TradeContext) -> TradeContext:
        """Inspect/mutate the context and record a Decision."""
        raise NotImplementedError
