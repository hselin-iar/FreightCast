"""
api/routes/narrate.py — On-demand Groq narrative generation.

POST /narrate
  Takes the raw Prophet decomposition numbers (already in the DB as JSON)
  and returns a fresh LLM-generated analyst paragraph.

Called only when the user opens the Rate Driver panel — zero cost until viewed.
The GROQ_API_KEY never leaves the server.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class NarrateRequest(BaseModel):
    horizon_days: int
    trend_delta: float
    trend_direction: str                          # "rising" | "falling" | "flat"
    weekly_seasonality_amplitude: float
    regressor_effects: Dict[str, float]           # {source: $/day}
    available_regressors: list[str]


class NarrateResponse(BaseModel):
    narrative: str
    source: str                                   # "groq" | "template"


_REG_LABELS: Dict[str, str] = {
    "bdry": "BDI (Baltic Dry Index)",
    "brent": "Brent crude oil",
    "wti": "WTI crude oil",
    "iron_ore": "Iron ore price",
    "bunker_vlsfo": "Bunker fuel (VLSFO)",
    "bunker_mgo": "Bunker fuel (MGO)",
    "gscpi": "Global Supply Chain Pressure Index",
}


def _template(req: NarrateRequest) -> str:
    """Deterministic template fallback — used when Groq is unavailable."""
    _labels = {
        "bdry": "BDI", "brent": "Brent", "wti": "WTI",
        "iron_ore": "iron ore", "bunker_vlsfo": "bunker fuel", "gscpi": "supply chain pressure",
    }
    h = req.horizon_days
    d = req.trend_delta
    if req.trend_direction == "rising":
        trend_str = f"Rates up {abs(d):.0f} $/day over the {h}d window"
    elif req.trend_direction == "falling":
        trend_str = f"Rates easing {abs(d):.0f} $/day over the {h}d window"
    else:
        trend_str = f"Rates flat over the {h}d window"

    parts = [trend_str + "."]
    amp = req.weekly_seasonality_amplitude
    if amp > 1.0:
        parts.append(f"Weekly seasonality: ±{amp/2:.0f} $/day.")
    if req.regressor_effects:
        top = sorted(req.regressor_effects.items(), key=lambda x: abs(x[1]), reverse=True)
        drivers = []
        for name, eff in top[:4]:
            if abs(eff) < 0.5:
                continue
            label = _labels.get(name, name.replace("_", " "))
            sign = "+" if eff > 0 else ""
            drivers.append(f"{label} ({sign}{eff:.0f} $/day)")
        if drivers:
            parts.append("Drivers: " + ", ".join(drivers) + ".")
    if not req.available_regressors:
        parts.append("No macro data — trend and seasonality only.")
    return " ".join(parts)


@router.post("/narrate", response_model=NarrateResponse)
async def narrate(req: NarrateRequest) -> NarrateResponse:
    """
    Generate an analyst-quality narrative from Prophet decomposition numbers.

    Calls Groq if GROQ_API_KEY is set; falls back to template otherwise.
    This endpoint is called on-demand when the user opens the Rate Driver panel.
    The API key is never exposed to the frontend.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        logger.debug("/narrate: GROQ_API_KEY not set — using template")
        return NarrateResponse(narrative=_template(req), source="template")

    # Build structured fact block — LLM must interpret facts, not invent them
    facts: list[str] = [
        f"- Forecast horizon: {req.horizon_days} days",
        f"- Trend direction: {req.trend_direction}",
        f"- Trend magnitude: {'+' if req.trend_delta >= 0 else ''}{req.trend_delta:.1f} $/day over the horizon",
    ]
    amp = req.weekly_seasonality_amplitude
    if amp > 1.0:
        facts.append(f"- Weekly seasonality amplitude (peak-to-trough): {amp:.1f} $/day")
    if req.regressor_effects:
        facts.append("- Macro driver effects ($/day additive, from Prophet decomposition):")
        for name, eff in sorted(req.regressor_effects.items(), key=lambda x: abs(x[1]), reverse=True):
            label = _REG_LABELS.get(name, name.replace("_", " ").title())
            sign = "+" if eff >= 0 else ""
            facts.append(f"  * {label}: {sign}{eff:.1f} $/day")
    else:
        facts.append("- No macro regressors available (trend and seasonality decomposed only)")

    fact_block = "\n".join(facts)
    prompt = (
        "You are a senior dry-bulk freight analyst writing a brief market commentary "
        "for a live chartering dashboard.\n\n"
        "Below are exact numbers from a Prophet time-series decomposition model for a specific "
        "vessel route. Turn these into a clear, natural 2-3 sentence analytical paragraph that "
        "a trader can read at a glance.\n\n"
        "RULES:\n"
        "- Use only the numbers given. Do not invent or assume anything extra.\n"
        "- Specific $/day figures must appear where they add insight.\n"
        "- Active voice, present tense, plain English. No bullet points or markdown.\n"
        "- Do NOT open with 'Freight rates are' or 'The freight rates'. Vary your opener.\n"
        "- Maximum 70 words.\n\n"
        f"Facts (use exactly as given):\n{fact_block}\n\n"
        "Analyst commentary:"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "groq/compound-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 130,
                    "temperature": 0.4,
                    "top_p": 0.9,
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            if len(text) < 20:
                raise ValueError(f"Suspiciously short response: {text!r}")
            logger.info("/narrate: Groq narrative generated (%d chars)", len(text))
            return NarrateResponse(narrative=text, source="groq")

    except Exception as exc:
        logger.warning("/narrate: Groq call failed (%s) — using template fallback", exc)
        return NarrateResponse(narrative=_template(req), source="template")
