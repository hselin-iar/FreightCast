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

    Prioritizes NVIDIA NIM API (using NVIDIA_API_KEY in .env), falls back to Groq,
    and finally to a deterministic template if offline.
    """
    # 1. Gather NVIDIA NIM Keys
    nvidia_keys = [
        k for k in (
            os.environ.get("NVIDIA_API_KEY"),
            os.environ.get("NVIDIA_API_KEY_2"),
            os.environ.get("NVIDIA_API_KEY_3"),
            os.environ.get("NVIDIA_NIM_API_KEY"),
        ) if k and k.strip()
    ]

    # 2. Gather Groq Keys
    groq_keys = [
        k for k in (
            os.environ.get("GROQ_API_KEY"),
            os.environ.get("GROQ_API_KEY_2"),
            os.environ.get("GROQ_API_KEY_3"),
        ) if k and k.strip()
    ]

    # Build structured fact block — LLM must interpret facts, not invent them
    facts: list[str] = [
        f"- Forecast horizon: {req.horizon_days} days",
        f"- Trend direction: {req.trend_direction}",
        f"- Trend magnitude: {'+' if req.trend_delta >= 0 else ''}{req.trend_delta:.1f} $/day over the horizon",
    ]
    amp = req.weekly_seasonality_amplitude
    if amp > 1.0:
        facts.append(f"- Weekly seasonality amplitude: {amp:.1f} $/day peak-to-trough")
    if req.regressor_effects:
        facts.append("- Macro driver effects ($/day additive from Prophet decomposition):")
        for name, eff in sorted(req.regressor_effects.items(), key=lambda x: abs(x[1]), reverse=True):
            label = _REG_LABELS.get(name, name.replace("_", " ").title())
            sign = "+" if eff >= 0 else ""
            facts.append(f"  * {label}: {sign}{eff:.1f} $/day")
    else:
        facts.append("- No macro regressors available (trend and seasonality decomposed only)")

    fact_block = "\n".join(facts)
    prompt = (
        "You are an expert commercial dry-bulk chartering analyst providing an instant executive briefing.\n"
        "Below are exact decomposition numbers from a Prophet time-series model for this vessel route.\n"
        "Synthesize these facts into EXACTLY two concise, punchy sentences:\n"
        "Sentence 1: State the dominant market force driving freight rate momentum and its operational cause.\n"
        "Sentence 2: State the direct commercial recommendation for the charterer (whether to lock forward or float spot).\n\n"
        "STRICT RULES:\n"
        "- Maximum 45 words total.\n"
        "- Plain English. No markdown, no asterisks, no bullet points, no preamble.\n"
        "- Do NOT start with 'The freight rates' or 'Freight rates'.\n\n"
        f"Facts:\n{fact_block}\n\n"
        "Briefing:"
    )

    import asyncio

    # Try NVIDIA NIM first
    if nvidia_keys:
        model = os.environ.get("NVIDIA_MODEL", "google/diffusiongemma-26b-a4b-it")
        for attempt in range(len(nvidia_keys)):
            key = nvidia_keys[attempt]
            try:
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.post(
                        "https://integrate.api.nvidia.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": "You are a senior maritime chartering strategist. Output exactly two concise sentences directly without bullet points or preamble."},
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": 180,
                            "temperature": 0.2,
                        },
                    )
                    if resp.status_code == 200:
                        msg = resp.json()["choices"][0]["message"]
                        text = (msg.get("content") or "").strip()
                        if not text and msg.get("reasoning"):
                            raw_r = msg.get("reasoning").strip()
                            import re
                            m1 = re.search(r'Sentence 1:\s*"?([^"\n\r]+)"?', raw_r)
                            m2 = re.search(r'Sentence 2:\s*"?([^"\n\r]+)"?', raw_r)
                            if m1 and m2:
                                text = f"{m1.group(1).strip()} {m2.group(1).strip()}"
                            else:
                                text = raw_r
                        text = text.strip('"\'')
                        if len(text) > 20:
                            logger.info("/narrate: NVIDIA NIM synthesis generated (%d chars)", len(text))
                            return NarrateResponse(narrative=text, source="nvidia")
            except Exception as e:
                logger.warning("/narrate: NVIDIA NIM attempt %d failed (%s)", attempt + 1, e)

    # Try Groq fallback
    if groq_keys:
        model = os.environ.get("GROQ_MODEL", "groq/compound-mini")
        for attempt in range(len(groq_keys)):
            key = groq_keys[attempt]
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 120,
                            "temperature": 0.3,
                        },
                    )
                    if resp.status_code == 200:
                        text = resp.json()["choices"][0]["message"]["content"].strip().strip('"\'')
                        if len(text) > 20:
                            logger.info("/narrate: Groq synthesis generated (%d chars)", len(text))
                            return NarrateResponse(narrative=text, source="groq")
            except Exception as e:
                logger.warning("/narrate: Groq attempt %d failed (%s)", attempt + 1, e)

    # Deterministic template fallback
    return NarrateResponse(narrative=_template(req), source="template")
