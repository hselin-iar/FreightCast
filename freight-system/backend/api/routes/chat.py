"""
api/routes/chat.py — POST /chat

Server-side LLM tool-calling proxy supporting:
  1. Groq (GROQ_API_KEY) — models: llama-3.3-70b-versatile / mixtral-8x7b-32768
  2. Nvidia NIM (NVIDIA_API_KEY) — models: meta/llama-3.3-70b-instruct
  3. Anthropic (ANTHROPIC_API_KEY) — models: claude-3-5-sonnet-20241022 / claude-3-7-sonnet
  4. OpenAI (OPENAI_API_KEY) — models: gpt-4o / gpt-4o-mini

Architecture (DOC3 §FEATURE: Chatbot / DOC2 §3b, §3c, §16.2):
  - Single tool exposed to LLM: `get_recommendation`, wrapping the EXACT
    same decision.solve() path that /recommendation uses. No second code path.
  - Conversation history is stateless: client sends it, we echo back the
    updated history. Zero server-side session state.
  - cargo_context from the last dashboard form submission lets the chatbot
    resolve follow-up references (§3c step 1) without re-asking the manager.
  - When the LLM emits a tool call whose constraints differ from cargo_context's
    (or cargo_context is absent), we run a genuine re-solve and populate
    updated_recommendation so the React dashboard can update the open plan
    with a "changed because you asked" annotation.

AGENTIC RULE (DOC4 §4.2): The chatbot must never bypass the Constraint Engine
or Decision Engine — it calls the exact /recommendation logic, nothing else.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException

from backend.api.routes.recommendation import _build_overrides, _serialise_strategy, _validate_scope
from backend.api.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    HumanOverridesRequest,
    RecommendationRequest,
    RecommendationResponse,
)
from backend.engine import decision

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt builder — injects live scope so the LLM always knows the
# exact vessel class names, port names, and origin names.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_BASE = """You are the Decision Assistant for SAIL Freight Intelligence (SAIL PS3) — an intelligent freight forecasting & chartering system.

YOUR STRICT RULES:
1. Never state a number (freight rate, total cost, days, voyage count) that was not returned by a tool call. If you need numbers, you MUST call the get_recommendation tool.
2. If the user asks a question about their plan or what-if scenario (e.g. "what if only use capemax", "what if no Capesize", "what if I need this in 12 days"), IMMEDIATELY call the get_recommendation tool with the appropriate `constraints` object. DO NOT ask the user clarifying questions about what vessels exist or what to exclude — execute the re-solve immediately!
3. The SAIL fleet consists of EXACTLY 3 vessel classes:
   - "Capesize" (large bulk carrier, ~180k MT)
   - "Panamax/Kamsarmax" (medium bulk carrier, ~75k MT)
   - "Supramax/Ultramax" (geared bulk carrier, ~58k MT)
4. HOW TO MAP USER VESSEL CONSTRAINTS:
   - "only use capemax" / "only Capesize" / "force Capesize" -> constraints: {"allow_vessel": ["Capesize"]}
   - "only use panamax" / "only Panamax" -> constraints: {"allow_vessel": ["Panamax/Kamsarmax"]}
   - "only use supermax" / "only Supramax" -> constraints: {"allow_vessel": ["Supramax/Ultramax"]}
   - "no Capesize" / "exclude Capesize" -> constraints: {"exclude_vessel": ["Capesize"]}
   - "no Panamax" -> constraints: {"exclude_vessel": ["Panamax/Kamsarmax"]}
5. When the user asks "why?" or "what are the drivers?", explain using the cost_breakdown and voyage details from the tool result.
6. Compose every reply strictly from what the tool returns. Keep answers clear, professional, and concise for a chartering manager.

CRITICAL — READING TOOL RESULTS:
- Read ALL cost figures VERBATIM from the tool's JSON response fields.
- NEVER compute freight, tax, or cost yourself. Use exactly what is in the JSON.
- Freight cost is in `cost_breakdown.ocean_freight` (already computed, post-discount).
- Tax is in `cost_breakdown.tax` (already computed, do not apply any percentage yourself).
- Total cost is in `cost_breakdown.total`.
- Voyage count is in `recommendation.voyage_count`.

AVAILABLE TOOL: get_recommendation
  Wraps the MILP optimizer. Returns the optimal chartering strategy with full cost breakdown, vessel allocations, and scenario comparisons.
"""

_SYSTEM_PROMPT_SCOPE_TEMPLATE = """
SCOPE — USE EXACT NAMES ONLY:
  Vessel classes:
{vessel_classes_list}

  Valid discharge ports:
{ports_list}

  Valid origin ports:
{origins_list}
"""

_SYSTEM_PROMPT_MARKET_TEMPLATE = """
CURRENT MARKET DRIVER CONTEXT (from Prophet decomposition — use to answer 'why is the rate this way' questions):
{market_context}
"""


def _build_system_prompt() -> str:
    """
    Build the system prompt with live-injected scope (vessel classes, ports, origins)
    AND Prophet decomposition narrative from the latest available ForecastObjects.

    Called once per request so scope and market context are always current.
    Falls back to the base prompt if scope cannot be fetched.
    """
    try:
        from backend.warehouse import repository
        vessel_classes = repository.get_valid_vessel_classes() or []
        dest_ports = repository.get_valid_dest_ports() or []
        origins = repository.get_valid_origins() or []

        vc_list = "\n".join(f'    - "{v}"' for v in vessel_classes) or '    (none configured)'
        ports_list = "\n".join(f'    - "{p}"' for p in dest_ports) or '    (none configured)'
        origins_list = "\n".join(f'    - "{o}"' for o in origins) or '    (none configured)'

        scope_block = _SYSTEM_PROMPT_SCOPE_TEMPLATE.format(
            vessel_classes_list=vc_list,
            ports_list=ports_list,
            origins_list=origins_list,
        )

        # --- Inject Prophet market context (Phase 7) ---
        # Pull driver_explanation from the most recent ForecastObjects across
        # routes and extract Prophet narratives so the chatbot can reference them.
        market_context = _build_prophet_market_context()
        if market_context:
            market_block = _SYSTEM_PROMPT_MARKET_TEMPLATE.format(market_context=market_context)
        else:
            market_block = ""

        return _SYSTEM_PROMPT_BASE + scope_block + market_block
    except Exception:
        logger.warning("_build_system_prompt: could not fetch live scope — using base prompt")
        return _SYSTEM_PROMPT_BASE


def _build_prophet_market_context() -> str:
    """Extract Prophet narratives from the latest ForecastObjects for all routes.

    Returns a formatted string block for injection into the chatbot system prompt,
    or empty string if no Prophet decompositions are available.
    """
    import json
    try:
        from backend.warehouse import repository
        from backend.warehouse.db import get_session
        from backend.warehouse.models import ForecastObject
        from sqlalchemy import select, desc

        narratives: list[str] = []
        routes = repository.get_valid_routes() or []
        vessel_classes = repository.get_valid_vessel_classes() or []

        # Sample a representative set — cap at 6 to avoid prompt bloat
        combos_checked = 0
        with get_session() as session:
            for route in routes[:3]:
                for vc in vessel_classes[:2]:
                    if combos_checked >= 6:
                        break
                    row = session.execute(
                        select(ForecastObject.driver_explanation)
                        .where(
                            ForecastObject.route == route,
                            ForecastObject.vessel_class == vc,
                            ForecastObject.horizon_days == 30,
                        )
                        .order_by(desc(ForecastObject.generated_at))
                        .limit(1)
                    ).scalar_one_or_none()
                    if row:
                        try:
                            parsed = json.loads(row)
                            prophet = parsed.get("prophet_decomposition")
                            if prophet and prophet.get("narrative"):
                                narratives.append(
                                    f"  [{route} · {vc}]: {prophet['narrative']}"
                                )
                                combos_checked += 1
                        except Exception:
                            pass

        return "\n".join(narratives) if narratives else ""
    except Exception as exc:
        logger.debug("_build_prophet_market_context failed (non-blocking): %s", exc)
        return ""


# Keep backward-compatible module-level alias (used by Anthropic handler which
# reads _SYSTEM_PROMPT directly; we now rebuild per-request for Groq/OpenAI)
_SYSTEM_PROMPT = _SYSTEM_PROMPT_BASE


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_TOOL_PARAM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "cargo_quantity": {
            "type": "number",
            "description": "Cargo size in metric tonnes (e.g. 70000, 140000)",
        },
        "origin_port": {
            "type": "string",
            "description": "Origin load port name (e.g. 'Australia (Hay Point)', 'Richards Bay', 'Kalimantan')",
        },
        "discharge_ports": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of discharge ports (e.g. ['Paradip', 'Gangavaram', 'Vizag', 'Dhamra', 'Haldia'])",
        },
        "timing_flexibility_days": {
            "type": "integer",
            "description": "How many days the fix date can flex (1–90, default 30)",
        },
        "commitment_benchmark_pct": {
            "type": "number",
            "description": "Assumed locked-rate discount vs spot (50–100, default 95)",
        },
        "constraints": {
            "type": "object",
            "description": "Human override constraints applied as MILP variable-fixing",
            "properties": {
                "allow_vessel": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Allow ONLY these vessel classes, e.g. ['Capesize'] or ['Panamax/Kamsarmax']",
                },
                "require_vessel": {
                    "type": "string",
                    "description": "Require a single specific vessel class, e.g. 'Capesize'",
                },
                "exclude_vessel": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Vessel classes to exclude, e.g. ['Capesize'] or ['Panamax/Kamsarmax']",
                },
                "require_port": {
                    "type": "string",
                    "description": "Force all discharge to this port only",
                },
                "max_completion_day": {
                    "type": "integer",
                    "description": "Latest completion day allowed (e.g. 12)",
                },
                "force_mode": {
                    "type": "string",
                    "enum": ["spot", "locked"],
                    "description": "Force spot or locked commitment mode",
                },
                "min_fix_day": {
                    "type": "integer",
                    "description": "Earliest fix day allowed",
                },
            },
            "additionalProperties": False,
        },
    },
    "required": ["cargo_quantity", "origin_port", "discharge_ports", "timing_flexibility_days"],
}

# OpenAI / Groq / Nvidia tool format
_OPENAI_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_recommendation",
            "description": (
                "Get a MILP-optimised chartering strategy for a cargo request. "
                "Calls the exact same backend engine as the dashboard form. "
                "Returns optimal voyage count, vessel/port assignments, spot/locked mix, fix days, and 5-bucket cost breakdown."
            ),
            "parameters": _TOOL_PARAM_SCHEMA,
        },
    }
]

# Anthropic tool format
_ANTHROPIC_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_recommendation",
        "description": "Get a MILP-optimised chartering strategy for a cargo request.",
        "input_schema": _TOOL_PARAM_SCHEMA,
    }
]


# ---------------------------------------------------------------------------
# Engine Execution Helpers
# ---------------------------------------------------------------------------

def _normalize_constraints(constraints_raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize vessel class names and port names in constraints so loose LLM outputs
    (e.g., 'Cape Max', 'Super Max', 'Panamax', 'dhamra') map cleanly to the exact
    canonical warehouse scope strings, preventing 422 validation errors.
    """
    from backend.warehouse import repository
    valid_vessels = repository.get_valid_vessel_classes() or ["Capesize", "Panamax/Kamsarmax", "Supramax/Ultramax"]
    valid_ports = repository.get_valid_dest_ports() or ["Paradip", "Gangavaram", "Dhamra"]

    def _match_vessel(raw_v: str) -> Optional[str]:
        raw_v_clean = raw_v.strip()
        matched = next((v for v in valid_vessels if v.lower() == raw_v_clean.lower()), None)
        if matched:
            return matched
        low = raw_v_clean.lower().replace(" ", "").replace("-", "").replace("/", "")
        if "cape" in low:
            return next((v for v in valid_vessels if "capesize" in v.lower()), None)
        elif "panamax" in low or "kamsarmax" in low:
            return next((v for v in valid_vessels if "panamax" in v.lower() or "kamsarmax" in v.lower()), None)
        elif "supra" in low or "ultra" in low or "super" in low:
            return next((v for v in valid_vessels if "supramax" in v.lower() or "ultramax" in v.lower()), None)
        return None

    c = dict(constraints_raw)

    # 1. Normalize require_vessel
    if "require_vessel" in c and isinstance(c["require_vessel"], str):
        m = _match_vessel(c["require_vessel"])
        if m:
            c["require_vessel"] = m
        else:
            c.pop("require_vessel", None)

    # 2. Normalize allow_vessel list
    if "allow_vessel" in c and isinstance(c["allow_vessel"], list):
        normalized_allow = []
        for raw_v in c["allow_vessel"]:
            if isinstance(raw_v, str):
                m = _match_vessel(raw_v)
                if m:
                    normalized_allow.append(m)
        c["allow_vessel"] = list(dict.fromkeys(normalized_allow)) or None

    # 3. Normalize exclude_vessel list
    if "exclude_vessel" in c and isinstance(c["exclude_vessel"], list):
        normalized_exclude = []
        for raw_v in c["exclude_vessel"]:
            if isinstance(raw_v, str):
                m = _match_vessel(raw_v)
                if m:
                    normalized_exclude.append(m)
                else:
                    logger.warning("Unrecognized vessel class %r in exclude_vessel — omitted.", raw_v)
        c["exclude_vessel"] = list(dict.fromkeys(normalized_exclude)) or None

    # 4. Normalize require_port
    if "require_port" in c and isinstance(c["require_port"], str):
        raw_p = c["require_port"].strip()
        matched_p = next((p for p in valid_ports if p.lower() == raw_p.lower()), None)
        if matched_p:
            c["require_port"] = matched_p

    return {k: v for k, v in c.items() if v is not None}


def _run_recommendation(tool_input: Dict[str, Any]) -> RecommendationResponse:
    """
    Execute the same recommendation logic as the dashboard form.
    No second code path — calls decision.solve() via the same helpers used by
    /recommendation. DOC2 §16.2 / DOC4 §4.2 NEVER rule.
    """
    from backend.warehouse import repository
    valid_ports = repository.get_valid_dest_ports() or ["Paradip", "Gangavaram", "Dhamra"]
    valid_origins = repository.get_valid_origins() or ["Australia (Hay Point)", "Indonesia (East Kalimantan)", "South Africa (Richards Bay)"]

    constraints_raw = tool_input.get("constraints") or {}
    normalized_constraints = _normalize_constraints(constraints_raw)
    overrides_req = HumanOverridesRequest(**normalized_constraints) if normalized_constraints else None
    overrides = _build_overrides(overrides_req)

    # Normalize defaults if LLM omitted optional fields
    timing_flex = tool_input.get("timing_flexibility_days") or 30
    raw_ports = tool_input.get("discharge_ports")
    if isinstance(raw_ports, str):
        raw_ports = [raw_ports]
    if not raw_ports:
        raw_ports = ["Paradip"]

    # Fuzzy match discharge ports to valid port strings
    ports = []
    for rp in raw_ports:
        matched = next((p for p in valid_ports if p.lower() in rp.lower() or rp.lower() in p.lower()), rp)
        ports.append(matched)

    raw_origin = tool_input.get("origin_port") or "Australia (Hay Point)"
    origin = next((o for o in valid_origins if o.lower() in raw_origin.lower() or raw_origin.lower() in o.lower()), raw_origin)

    qty = float(tool_input.get("cargo_quantity") or 70000)

    rec_req = RecommendationRequest(
        cargo_quantity=qty,
        origin_port=origin,
        discharge_ports=ports,
        timing_flexibility_days=timing_flex,
        commitment_benchmark_pct=tool_input.get("commitment_benchmark_pct"),
        constraints=overrides_req,
    )
    _validate_scope(rec_req)

    best, comparisons = decision.solve(
        cargo_quantity=rec_req.cargo_quantity,
        origin_port=rec_req.origin_port,
        discharge_ports=rec_req.discharge_ports,
        timing_flexibility_days=rec_req.timing_flexibility_days,
        commitment_benchmark_pct=rec_req.commitment_benchmark_pct,
        constraints=overrides,
    )
    return RecommendationResponse(
        recommendation=_serialise_strategy(best),
        scenario_comparison=[_serialise_strategy(s) for s in comparisons],
    )


def _constraints_note(tool_input: Dict[str, Any]) -> Optional[str]:
    """Build a human-readable annotation of what constraints were applied."""
    c = tool_input.get("constraints") or {}
    parts: List[str] = []
    if c.get("require_vessel"):
        parts.append(f"only {c['require_vessel']}")
    elif c.get("allow_vessel"):
        parts.append(f"only {', '.join(c['allow_vessel'])}")
    if c.get("exclude_vessel"):
        parts.append(f"excluding {', '.join(c['exclude_vessel'])}")
    if c.get("require_port"):
        parts.append(f"port fixed to {c['require_port']}")
    if c.get("max_completion_day") is not None:
        parts.append(f"≤{c['max_completion_day']} days")
    if c.get("force_mode"):
        parts.append(f"{c['force_mode']} only")
    if c.get("min_fix_day") is not None:
        parts.append(f"fix day ≥{c['min_fix_day']}")
    return ", ".join(parts) if parts else None


def _is_constraint_change(
    tool_input: Dict[str, Any],
    cargo_context: Optional[RecommendationRequest],
) -> bool:
    """True if tool call changes constraints vs prior form submission."""
    if cargo_context is None:
        return True

    c = tool_input.get("constraints") or {}
    if c:
        return True

    try:
        qty = float(tool_input.get("cargo_quantity") or 0)
        origin = tool_input.get("origin_port")
        ports = set(tool_input.get("discharge_ports") or [])
        flex = tool_input.get("timing_flexibility_days")

        if (
            abs(qty - cargo_context.cargo_quantity) > 0.01
            or origin != cargo_context.origin_port
            or ports != set(cargo_context.discharge_ports)
            or flex != cargo_context.timing_flexibility_days
        ):
            return True
    except Exception:
        return True

    return False


# ---------------------------------------------------------------------------
# Multi-Provider LLM Calling
# ---------------------------------------------------------------------------

def _get_provider_config() -> Tuple[str, List[str], str, str]:
    """
    Detect configured LLM provider and credentials.
    Returns (provider_name, api_keys, base_url, model_name).
    """
    # 1. Nvidia NIM (Prioritized)
    nvidia_keys = [
        k for k in (
            os.environ.get("NVIDIA_API_KEY"),
            os.environ.get("NVIDIA_API_KEY_2"),
            os.environ.get("NVIDIA_API_KEY_3"),
            os.environ.get("NVIDIA_NIM_API_KEY"),
        ) if k and k.strip()
    ]
    if nvidia_keys:
        model = os.environ.get("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")
        return ("nvidia", nvidia_keys, "https://integrate.api.nvidia.com/v1", model)

    # 2. Groq
    groq_keys = [
        k for k in (
            os.environ.get("GROQ_API_KEY"),
            os.environ.get("GROQ_API_KEY_2"),
            os.environ.get("GROQ_API_KEY_3"),
        ) if k and k.strip()
    ]
    if groq_keys:
        model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        return ("groq", groq_keys, "https://api.groq.com/openai/v1", model)

    # 3. Anthropic Claude
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        return ("anthropic", [anthropic_key], "https://api.anthropic.com/v1", model)

    # 4. OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        return ("openai", [openai_key], "https://api.openai.com/v1", model)

    raise HTTPException(
        status_code=503,
        detail=(
            "No LLM API key configured on the server. "
            "Please set GROQ_API_KEY, NVIDIA_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY."
        ),
    )


def _call_openai_compatible(
    api_keys: List[str],
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Call OpenAI-compatible chat completions endpoint (Groq, Nvidia, OpenAI)."""
    payload = {
        "model": model,
        "messages": messages,
        "tools": _OPENAI_TOOLS,
        "tool_choice": "auto",
        "temperature": 1.0,  # User requested temperature=1
        "max_tokens": 16384, # User requested 16384
    }

    if "nvidia.com" in base_url:
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        payload["top_p"] = 0.95

    with httpx.Client(timeout=45.0) as client:
        last_error_resp = None
        # Try every configured key in sequence; if all fail, retry once with backoff
        total_attempts = len(api_keys) * 2
        for attempt in range(total_attempts):
            key_idx = attempt % len(api_keys)
            key_to_use = api_keys[key_idx]
            headers = {
                "Authorization": f"Bearer {key_to_use}",
                "Content-Type": "application/json",
            }
            try:
                resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            except Exception as e:
                logger.warning("Network error with key %d: %s. Rotating...", key_idx + 1, e)
                continue

            if resp.status_code == 200:
                if attempt > 0:
                    logger.info("Successfully recovered using rotated API key #%d", key_idx + 1)
                return resp.json()

            last_error_resp = resp

            # If rate-limited, quota-exhausted, temporarily overloaded/server error, or invalid/expired key (404), rotate immediately
            if resp.status_code in (404, 429, 402, 403, 500, 502, 503, 504):
                logger.warning(
                    "LLM key #%d/%d returned status %d (%s). Rotating to next key...",
                    key_idx + 1, len(api_keys), resp.status_code, resp.text[:120]
                )
                # Only sleep if we have already cycled through all keys once
                if attempt >= len(api_keys) - 1:
                    time.sleep(2.0)
                continue

            # Non-rotatable client/server error (e.g. 400 Bad Request, 404)
            logger.error("LLM provider error %d: %s", resp.status_code, resp.text)
            raise HTTPException(
                status_code=502,
                detail=f"LLM provider returned status {resp.status_code}: {resp.text}",
            )

        if last_error_resp is not None and last_error_resp.status_code in (429, 402, 403, 503):
            logger.warning("All %d LLM API keys exhausted / rate limited: %s", len(api_keys), last_error_resp.text)
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "All configured API keys are currently experiencing high traffic or rate limits. Please try again in a moment."
                    }
                }]
            }
        
        raise HTTPException(
            status_code=502,
            detail=f"All LLM keys failed. Last error: {last_error_resp.text if last_error_resp else 'Timeout'}",
        )


def _call_anthropic(
    api_keys: List[str],
    model: str,
    messages: List[Dict[str, Any]],
    system_prompt: str = _SYSTEM_PROMPT_BASE,
) -> Dict[str, Any]:
    """Call Anthropic messages endpoint."""
    payload = {
        "model": model,
        "system": system_prompt,
        "messages": messages,
        "tools": _ANTHROPIC_TOOLS,
        "max_tokens": 1024,
    }

    with httpx.Client(timeout=30.0) as client:
        for attempt in range(4):
            key_to_use = api_keys[attempt % len(api_keys)]
            headers = {
                "x-api-key": key_to_use,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            if resp.status_code == 429 and attempt < 3:
                time.sleep(2.5 * (attempt + 1))
                continue
            if resp.status_code == 429:
                return {
                    "content": [{
                        "type": "text",
                        "text": "I'm currently experiencing very high traffic and have reached my rate limit. Please wait a few minutes and try again."
                    }]
                }
        if resp.status_code != 200:
            logger.error("Anthropic error %d: %s", resp.status_code, resp.text)
            raise HTTPException(
                status_code=502,
                detail=f"Anthropic returned status {resp.status_code}: {resp.text}",
            )
        return resp.json()


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """
    Universal LLM tool-calling proxy (Groq, Nvidia, Anthropic, OpenAI).
    """
    provider, api_keys, base_url, model = _get_provider_config()

    tool_called = False
    updated_rec: Optional[RecommendationResponse] = None
    constraint_note: Optional[str] = None
    reply: str = ""

    # ── 1. Groq / Nvidia / OpenAI flow ─────────────────────────────────────
    if provider in ("groq", "nvidia", "openai"):
        # Build system prompt with live scope injected (vessel classes, ports, origins)
        live_system_prompt = _build_system_prompt()
        messages: List[Dict[str, Any]] = [{"role": "system", "content": live_system_prompt}]

        # Inject prior cargo context if available to help reference resolution
        if req.cargo_context:
            ctx_summary = (
                f"[Current Dashboard Cargo Context: Quantity={req.cargo_context.cargo_quantity} MT, "
                f"Origin={req.cargo_context.origin_port}, Discharge Ports={req.cargo_context.discharge_ports}, "
                f"Timing Flexibility={req.cargo_context.timing_flexibility_days} days]"
            )
            messages.append({"role": "system", "content": ctx_summary})

        for m in req.conversation_history:
            messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": req.message})

        # Turn 1: Check for tool calls
        llm_resp = _call_openai_compatible(api_keys, base_url, model, messages)
        choice = llm_resp.get("choices", [{}])[0]
        msg_obj = choice.get("message", {})

        tool_calls = msg_obj.get("tool_calls")
        if tool_calls:
            tool_called = True
            call_0 = tool_calls[0]
            func_name = call_0.get("function", {}).get("name")
            args_str = call_0.get("function", {}).get("arguments", "{}")

            try:
                tool_input = json.loads(args_str)
            except Exception:
                tool_input = {}

            # Execute recommendation solver
            try:
                tool_result = _run_recommendation(tool_input)
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Tool execution failed in /chat")
                raise HTTPException(status_code=500, detail=f"Recommendation engine error: {exc}") from exc

            if _is_constraint_change(tool_input, req.cargo_context):
                updated_rec = tool_result
                constraint_note = _constraints_note(tool_input)

            # Format tool result back into message thread (sanitize assistant message)
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": msg_obj.get("content") or "",
                "tool_calls": tool_calls,
            }
            messages.append(assistant_msg)
            tool_result_content = json.dumps(
                {
                    "recommendation": tool_result.recommendation.model_dump(mode="json"),
                    "scenario_comparison": [
                        s.model_dump(mode="json") for s in tool_result.scenario_comparison
                    ],
                },
                default=str,
            )
            messages.append({
                "role": "tool",
                "tool_call_id": call_0.get("id"),
                "content": tool_result_content,
            })

            # Turn 2: Get final assistant synthesis
            final_resp = _call_openai_compatible(api_keys, base_url, model, messages)
            final_choice = final_resp.get("choices", [{}])[0]
            final_msg = final_choice.get("message", {})
            raw_content = final_msg.get("content")
            if raw_content and str(raw_content).strip():
                reply = str(raw_content).strip()
            else:
                reply = (final_msg.get("reasoning_content") or "").strip()

        else:
            # Direct response (clarification or explanation)
            raw_content = msg_obj.get("content")
            if raw_content and str(raw_content).strip():
                reply = str(raw_content).strip()
            else:
                reply = (msg_obj.get("reasoning_content") or "").strip()

    # ── 2. Anthropic flow ──────────────────────────────────────────────────
    elif provider == "anthropic":
        # Build live-scope system prompt for Anthropic too
        live_system_prompt = _build_system_prompt()
        user_msgs = [
            {"role": m.role, "content": m.content}
            for m in req.conversation_history
        ]
        user_msgs.append({"role": "user", "content": req.message})

        llm_resp = _call_anthropic(api_keys, model, user_msgs, system_prompt=live_system_prompt)
        stop_reason = llm_resp.get("stop_reason")

        if stop_reason == "tool_use":
            tool_called = True
            content_blocks = llm_resp.get("content", [])
            tool_use_block = next((b for b in content_blocks if b.get("type") == "tool_use"), None)

            if tool_use_block:
                tool_input = tool_use_block.get("input", {})
                tool_result = _run_recommendation(tool_input)

                if _is_constraint_change(tool_input, req.cargo_context):
                    updated_rec = tool_result
                    constraint_note = _constraints_note(tool_input)

                tool_result_content = json.dumps(
                    {
                        "recommendation": tool_result.recommendation.model_dump(mode="json"),
                        "scenario_comparison": [
                            s.model_dump(mode="json") for s in tool_result.scenario_comparison
                        ],
                    },
                    default=str,
                )

                user_msgs.append({"role": "assistant", "content": content_blocks})
                user_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.get("id"),
                        "content": tool_result_content,
                    }],
                })

                final_resp = _call_anthropic(api_keys, model, user_msgs, system_prompt=live_system_prompt)
                final_blocks = final_resp.get("content", [])
                reply = " ".join(b.get("text", "") for b in final_blocks if b.get("text")).strip()
        else:
            content_blocks = llm_resp.get("content", [])
            reply = " ".join(b.get("text", "") for b in content_blocks if b.get("text")).strip()

    # ── Echo updated history back to caller ────────────────────────────────
    history_out: List[ChatMessage] = [
        ChatMessage(role=m.role, content=m.content)
        for m in req.conversation_history
    ]
    history_out.append(ChatMessage(role="user", content=req.message))
    if reply:
        history_out.append(ChatMessage(role="assistant", content=reply))
    history_out = history_out[-40:]

    return ChatResponse(
        reply=reply or "(no response)",
        tool_called=tool_called,
        updated_recommendation=updated_rec,
        constraint_note=constraint_note,
        conversation_history=history_out,
    )
