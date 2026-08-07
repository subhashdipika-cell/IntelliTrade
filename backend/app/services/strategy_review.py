"""LLM-assisted Strategy Review.

Aggregates REAL closed-trade performance per strategy (overall + per asset) and
asks the LLM for concrete, conservative refinement suggestions — the kind of
"this strategy is bleeding on ETH, drop it" / "raise the RR floor" advice you'd
get from a quant looking at the numbers.

Read-only and advisory: it never changes settings or places trades. The output
is structured so the UI can render it as cards (and so a future version can turn
a suggestion into a one-click Money-Mgmt/strategy tweak).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.api.routes.history import _trade_metrics  # reuse the existing analytics
from app.core.config import settings
from app.core.logging_setup import get_logger
from app.services import llm
from app.services.history_store import history_store

log = get_logger("services.strategy_review")

# Strategies that carry no real attribution (reconciled/backfilled trades).
_UNATTRIBUTED = {"—", "", None}


def _aggregate() -> tuple[int, dict, int]:
    """Returns (total_trades, per-strategy stats incl. by-asset, unattributed count)."""
    rows = history_store.all()
    strategies = sorted({r.get("strategy") or "—" for r in rows})
    per: dict[str, dict] = {}
    unattributed = 0
    for st in strategies:
        st_rows = [r for r in rows if (r.get("strategy") or "—") == st]
        if st in _UNATTRIBUTED:
            unattributed += len(st_rows)
            continue
        m = _trade_metrics(st_rows)
        assets = sorted({r.get("asset") or "—" for r in st_rows})
        m["by_asset"] = {
            a: _trade_metrics([r for r in st_rows if (r.get("asset") or "—") == a])
            for a in assets
        }
        per[st] = m
    return len(rows), per, unattributed


def _build_messages(per: dict, unattributed: int) -> list[dict]:
    system = (
        "You are a quantitative trading analyst reviewing the LIVE performance of "
        "automated strategies on BTC, ETH and Gold. You are given each strategy's "
        "real closed-trade statistics (overall and per asset). Find the biggest, "
        "statistically-grounded problems and propose CONCRETE, conservative "
        "refinements — prefer specific, testable changes (drop a losing asset, "
        "raise the R:R floor, tighten/trail the stop, add a session or trend "
        "filter, reduce size) over vague advice, and always cite the numbers. "
        "Samples under ~5 trades are unreliable: say so instead of over-fitting. "
        "Reply ONLY with JSON of this exact shape:\n"
        '{"summary":"<=40 words overall read",'
        '"suggestions":[{"strategy":"<name>","asset":"ALL|BTC|ETH|GOLD",'
        '"observation":"<=25 words citing numbers",'
        '"action":"<=25 words, one concrete change",'
        '"confidence":"low|medium|high"}]}'
    )
    # Compact the stats sent to the model (keep only decision-relevant fields, no
    # indentation) — far fewer tokens ⇒ much faster on a local model.
    compact = {
        st: {
            "trades": m.get("trades"), "win_rate_pct": m.get("win_rate_pct"),
            "profit_factor": m.get("profit_factor"), "expectancy": m.get("expectancy"),
            "net_pnl": m.get("net_pnl"), "by_outcome": m.get("by_outcome"),
            "by_asset": {a: {"trades": am.get("trades"), "win_rate_pct": am.get("win_rate_pct"),
                             "net_pnl": am.get("net_pnl"), "profit_factor": am.get("profit_factor")}
                         for a, am in (m.get("by_asset") or {}).items()},
        }
        for st, m in per.items()
    }
    user = (
        "STRATEGY PERFORMANCE (real closed trades):\n"
        f"{json.dumps(compact, default=str)}\n"
        f"(Plus {unattributed} unattributed/reconciled trades, excluded.)\n"
        "Review these strategies and return your JSON."
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _deterministic_suggestions(per: dict) -> tuple[str, list[dict]]:
    """Useful fallback when an LLM endpoint is unavailable or too slow."""
    if not per:
        return "No attributed strategy history is available yet.", []
    ranked = sorted(per.items(), key=lambda item: item[1].get("net_pnl", 0.0))
    worst_name, worst = ranked[0]
    suggestions = [{
        "strategy": worst_name, "asset": "ALL",
        "observation": f"{worst.get('trades', 0)} trades, PF {worst.get('profit_factor')}, net {worst.get('net_pnl'):+.2f}.",
        "action": "Keep disabled or alert-only until a fresh walk-forward test is profitable.",
        "confidence": "medium" if worst.get("trades", 0) >= 10 else "low",
    }]
    for name, stats in ranked:
        for asset, asset_stats in (stats.get("by_asset") or {}).items():
            if asset_stats.get("trades", 0) >= 5 and (asset_stats.get("profit_factor") or 0) < 0.8:
                suggestions.append({
                    "strategy": name, "asset": asset,
                    "observation": f"{asset_stats['trades']} trades, PF {asset_stats.get('profit_factor')}, net {asset_stats.get('net_pnl'):+.2f}.",
                    "action": "Remove this strategy-asset pair from autonomous execution.",
                    "confidence": "medium",
                })
    return f"Weakest attributed strategy is {worst_name}; deterministic safeguards are shown below.", suggestions[:6]


def review() -> dict:
    """Run a full review. Always returns a dict (never raises); on any LLM/infra
    problem it returns the stats with an explanatory note and empty suggestions."""
    total, per, unattributed = _aggregate()
    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": settings.review_provider or settings.llm_provider,
        "model": settings.review_model or settings.llm_model,
        "total_trades": total,
        "attributed_strategies": list(per.keys()),
        "unattributed_trades": unattributed,
        "stats": per,
        "summary": None,
        "suggestions": [],
    }

    if not per:
        out["note"] = ("No strategy-attributed trades yet — most history is "
                       "reconciled/unattributed. Run Live or the scanner with a "
                       "chosen strategy to build attributed history.")
        return out
    if not settings.llm_configured:
        out["note"] = ("No LLM configured. Set LLM_PROVIDER=ollama (free/local) "
                       "or add an OpenRouter key, then restart.")
        return out

    messages = _build_messages(per, unattributed)
    attempts = []
    primary_provider = settings.review_provider or settings.llm_provider
    primary_models = [settings.review_model] if settings.review_model else None
    attempts.append((primary_provider, primary_models))
    if primary_provider.lower() != settings.llm_provider.lower():
        attempts.append((settings.llm_provider, None))
    content = None
    failures = []
    for provider, models_override in attempts:
        try:
            content = llm.chat(messages, max_tokens=160, timeout=8,
                               provider=provider, models_override=models_override)
            out["provider_used"] = provider
            break
        except Exception as exc:  # noqa: BLE001 — try the next configured endpoint
            failures.append(f"{provider}: {exc}")
    if content is None:
        out["summary"], out["suggestions"] = _deterministic_suggestions(per)
        out["note"] = "LLM unavailable; deterministic review returned. " + " | ".join(failures)
        return out

    data = llm.extract_json(content)
    if isinstance(data, dict):
        out["summary"] = data.get("summary")
        sugg = data.get("suggestions")
        out["suggestions"] = sugg if isinstance(sugg, list) else []
    elif isinstance(data, list):
        out["suggestions"] = data
    else:
        out["note"] = "LLM reply could not be parsed as JSON."
        out["raw"] = content[:2000]
    return out
