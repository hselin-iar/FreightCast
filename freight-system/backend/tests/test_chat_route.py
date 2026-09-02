"""
tests/test_chat_route.py — Test Chat route, schemas, and constraint-change logic.
DOC3 §FEATURE: Chatbot
DOC4 Step 13
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.chat import _constraints_note, _is_constraint_change
from backend.api.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    HumanOverridesRequest,
    RecommendationRequest,
)

client = TestClient(app)


def test_chat_schema_validation():
    """Test ChatRequest and ChatResponse schemas."""
    req = ChatRequest(
        message="What is the best chartering strategy?",
        conversation_history=[
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="How can I help?"),
        ],
    )
    assert req.message == "What is the best chartering strategy?"
    assert len(req.conversation_history) == 2


def test_constraint_note_formatting():
    """Test human-readable constraint annotation builder."""
    tool_input = {
        "constraints": {
            "exclude_vessel": ["Capesize"],
            "max_completion_day": 12,
            "force_mode": "spot",
        }
    }
    note = _constraints_note(tool_input)
    assert "excluding Capesize" in note
    assert "≤12 days" in note
    assert "spot only" in note

    # Empty constraints → None
    assert _constraints_note({}) is None
    assert _constraints_note({"constraints": {}}) is None


def test_is_constraint_change():
    """Test detection of constraint changes vs repeating the same query."""
    base_ctx = RecommendationRequest(
        cargo_quantity=70000,
        origin_port="Australia (Hay Point)",
        discharge_ports=["Paradip"],
        timing_flexibility_days=30,
    )

    # 1. New constraints attached -> change = True
    input_with_constraints = {
        "cargo_quantity": 70000,
        "origin_port": "Australia (Hay Point)",
        "discharge_ports": ["Paradip"],
        "timing_flexibility_days": 30,
        "constraints": {"exclude_vessel": ["Capesize"]},
    }
    assert _is_constraint_change(input_with_constraints, base_ctx) is True

    # 2. Same inputs without constraints -> change = False
    input_identical = {
        "cargo_quantity": 70000,
        "origin_port": "Australia (Hay Point)",
        "discharge_ports": ["Paradip"],
        "timing_flexibility_days": 30,
    }
    assert _is_constraint_change(input_identical, base_ctx) is False

    # 3. Cargo quantity changed -> change = True
    input_diff_qty = {
        "cargo_quantity": 140000,
        "origin_port": "Australia (Hay Point)",
        "discharge_ports": ["Paradip"],
        "timing_flexibility_days": 30,
    }
    assert _is_constraint_change(input_diff_qty, base_ctx) is True

    # 4. No previous context -> always True
    assert _is_constraint_change(input_identical, None) is True


def test_chat_endpoint_missing_api_key(monkeypatch):
    """POST /chat without any API key returns 503 explaining the key requirement."""
    for key in [
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3",
        "NVIDIA_API_KEY", "NVIDIA_API_KEY_2", "NVIDIA_API_KEY_3", "NVIDIA_NIM_API_KEY",
        "OPENAI_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    resp = client.post("/chat", json={"message": "What is the best vessel?"})
    assert resp.status_code == 503
    assert "No LLM API key configured" in resp.json()["detail"]


def test_chat_endpoint_invalid_payload():
    """POST /chat with empty message or bad structure returns 422 validation error."""
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422
