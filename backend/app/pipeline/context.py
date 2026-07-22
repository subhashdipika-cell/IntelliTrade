"""The TradeContext flows through every pipeline stage and accumulates a decision
log. This is what lets you answer 'Why did IntelliTrade buy Gold here?' — every
stage stamps its verdict, score and reason."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Verdict(str, Enum):
    PASS = "PASS"      # stage approves, continue
    BLOCK = "BLOCK"    # stage rejects, halt pipeline
    SKIP = "SKIP"      # stage disabled / not applicable
    INFO = "INFO"      # advisory only, never halts


class Outcome(str, Enum):
    OPEN = "OPEN"
    TGT = "TGT"        # take-profit hit
    SL = "SL"          # stop-loss hit
    TSL = "TSL"        # trailing-stop hit
    MANUAL = "MANUAL"  # closed by user / system


@dataclass
class Signal:
    asset: str                 # internal key: BTC | ETH | GOLD
    direction: Direction
    entry: float
    stop_loss: float
    target: float
    timeframe: str = "H1"
    lots: float = 0.0          # filled by the risk stage


@dataclass
class Decision:
    stage: str
    verdict: Verdict
    reason: str
    score: float | None = None
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "score": self.score,
            "at": self.at,
        }


@dataclass
class TradeContext:
    asset: str
    timeframe: str = "H1"
    strategy: str | None = None       # name of the strategy that produced the signal
    # Where this trade came FROM, as opposed to what strategy it ran.
    #   "scanner"  — originated by the pipeline in this process (the bot's own work)
    #   "adopted"  — found already open in MT5 under our magic and re-attached
    #                after a restart; this process did not decide to open it
    # Without this split, adopted positions are indistinguishable from scanner
    # trades in History. In July 2026 that hid the real picture: 12 adopted
    # trades made +376 while the scanner's own 54 lost -570, so the reported
    # -193 looked like mild underperformance instead of a bot losing ~29% of
    # capital in a month.
    origin: str = "scanner"
    market_data: Any = None          # pandas DataFrame of OHLCV
    signal: Signal | None = None
    decisions: list[Decision] = field(default_factory=list)
    blocked: bool = False
    blocked_by: str | None = None
    # execution / outcome
    ticket: int | None = None
    capital_deployed: float | None = None
    total_capital: float | None = None
    outcome: Outcome = Outcome.OPEN
    final_capital: float | None = None
    # trailing-stop state (managed by the monitor; signal.stop_loss stays ORIGINAL
    # so outcome classification can still detect a trailed exit as TSL)
    mfe_price: float | None = None    # best (most favorable) price seen since entry
    current_sl: float | None = None   # the live trailed stop (None until first move)
    trail_stage: str | None = None    # "BE" | "TRAIL" | "NEAR" — last stage applied

    def record(self, decision: Decision) -> None:
        self.decisions.append(decision)
        if decision.verdict is Verdict.BLOCK:
            self.blocked = True
            self.blocked_by = decision.stage

    def explain(self) -> list[dict[str, Any]]:
        """The full decision tree — feed this to the History/Replay view."""
        return [d.as_dict() for d in self.decisions]
