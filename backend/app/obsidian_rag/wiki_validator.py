"""Obsidian Wiki gatekeeper.

Retrieves the most relevant notes from your vault for a given signal and asks an
LLM (OpenAI-compatible — OpenRouter cloud or a local Ollama server, selected by
`LLM_PROVIDER`; primary model, fallback on error/rate-limit) whether the trade
complies with your playbook. Returns (approved, reason).

Retrieval is deliberately dependency-free: keyword/recency scoring over the
markdown files, no embeddings/ChromaDB. Good enough to surface the relevant
rules; swap in semantic search later without changing this interface.

Fail-open by design: if there's no key, no notes, or the LLM is unreachable,
it returns approved=True with an explanatory reason. The pipeline stage decides
whether to act on a 'no' (advisory vs blocking) — infra failure must never
silently block trades."""
from __future__ import annotations

import os

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.services import llm

log = get_logger("obsidian_rag.validator")

_MAX_NOTES = 3
_MAX_CHARS = 1500

_ASSET_TERMS = {
    "GOLD": ["gold", "xauusd", "xau"],
    "BTC": ["btc", "bitcoin", "btcusd"],
    "ETH": ["eth", "ethereum", "ethusd"],
}
_DIR_TERMS = {
    "BUY": ["buy", "long", "bull"],
    "SELL": ["sell", "short", "bear"],
}
_GENERIC = ["risk", "stop", "trend", "session", "news", "setup"]


def validate(asset: str, direction: str, entry: float, sl: float, tp: float,
             timeframe: str) -> tuple[bool, str]:
    if not settings.llm_configured:
        return True, "no LLM key configured (advisory pass)"

    context = _retrieve_context(asset, direction)
    if not context.strip():
        return True, "no matching notes in vault (advisory pass)"

    signal_desc = (
        f"{direction} {asset} on {timeframe}: entry {entry}, stop {sl}, target {tp}."
    )
    verdict = _ask_llm(signal_desc, context)
    return verdict


def _retrieve_context(asset: str, direction: str) -> str:
    vault = settings.obsidian_vault_path
    if not vault or not os.path.isdir(vault):
        return ""
    terms = (_ASSET_TERMS.get(asset.upper(), [asset.lower()])
             + _DIR_TERMS.get(direction.upper(), []) + _GENERIC)

    scored: list[tuple[int, float, str]] = []  # (score, mtime, text)
    for root, _, files in os.walk(vault):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except Exception:  # noqa: BLE001
                continue
            low = text.lower()
            score = sum(low.count(t) for t in terms)
            if score > 0:
                scored.append((score, os.path.getmtime(path), text[:_MAX_CHARS]))

    if not scored:
        return ""
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return "\n\n---\n\n".join(t for _, _, t in scored[:_MAX_NOTES])


def _ask_llm(signal_desc: str, context: str) -> tuple[bool, str]:
    system = (
        "You are a risk-management gatekeeper for an algorithmic trading system. "
        "Decide whether the proposed trade complies with the trader's personal "
        "playbook notes. Reply ONLY with JSON: "
        '{"approved": true|false, "reason": "<=20 words}.'
    )
    user = (
        f"PROPOSED TRADE:\n{signal_desc}\n\n"
        f"RELEVANT PLAYBOOK NOTES:\n\"\"\"\n{context}\n\"\"\"\n\n"
        "Does this trade comply with the notes?"
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    try:
        content = llm.chat(messages)
    except Exception as exc:  # noqa: BLE001 — fail open, never block on infra
        log.warning("Wiki LLM unreachable: %s", exc)
        return True, "LLM unreachable (advisory pass)"

    data = llm.extract_json(content)
    if not isinstance(data, dict):
        return True, "unparseable LLM response (advisory pass)"
    approved = bool(data.get("approved", True))
    reason = str(data.get("reason", "no reason given"))
    model = settings.llm_model or "llm"
    return approved, f"[{model}] {reason}"
