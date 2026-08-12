"""IntelliTrade backend entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

# Windows/CPU compatibility: preload Torch before the AI route imports
# scikit-learn/joblib and their native OpenMP libraries. If the machine still
# cannot initialize Torch, the server must start and the AI stage will HOLD.
try:
    from app.ai_engine.hf_ensemble import _prepare_local_torch
    _prepare_local_torch()
except Exception:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    account, ai, backtest, history, journal, live, money, news, review, scanner,
    telegram,
)
from app.core.logging_setup import configure_logging, get_logger
from app.services.mt5_client import mt5_client
from app.workers.scheduler import start_scheduler, stop_scheduler

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    connected = mt5_client.connect()
    log.info("MT5 connected: %s", connected)
    if connected:
        try:  # re-attach open positions so a restart doesn't lose their tracking
            from app.pipeline.stages.monitoring import reattach_open_trades
            n = reattach_open_trades()
            if n:
                log.info("Re-attached %d open trade(s) to the monitor.", n)
        except Exception as exc:  # noqa: BLE001
            log.warning("Re-attach open trades failed: %s", exc)
    start_scheduler()  # begins polling open trades -> exit alerts on close
    yield
    stop_scheduler()
    mt5_client.shutdown()


app = FastAPI(title="IntelliTrade", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (live.router, backtest.router, account.router, journal.router,
          money.router, history.router, ai.router, scanner.router, news.router,
          telegram.router, review.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": "IntelliTrade"}
