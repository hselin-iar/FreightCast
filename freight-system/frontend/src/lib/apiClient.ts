/**
 * apiClient.ts — every frontend→backend call goes through here, nowhere else.
 * DOC3 Agentic Coding Rule: "Route every frontend→backend call through
 *   /frontend/src/lib/apiClient.ts."
 *
 * Design:
 *   - Single fetch() wrapper with consistent {data, error} shape
 *   - Typed function per endpoint — no raw fetch() anywhere else in the codebase
 *   - AbortController support for stale-request cancellation (WhatIfSliders, Step 12)
 */

import type {
  ApiError,
  ChatRequest,
  ChatResponse,
  ForecastResponse,
  HealthResponse,
  PortStatusResponse,
  RecommendationRequest,
  RecommendationResponse,
  ScopeResponse,
} from './types';

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

/* ── Core fetch wrapper ──────────────────────────────────── */

interface Result<T> {
  data: T | null;
  error: ApiError | null;
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
  signal?: AbortSignal,
): Promise<Result<T>> {
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
      signal,
      ...options,
    });

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        // Pydantic 422: detail is an array of error dicts
        if (Array.isArray(body.detail)) {
          message = body.detail.map((e: { msg: string }) => e.msg).join('; ');
        } else if (typeof body.detail === 'string') {
          message = body.detail;
        }
      } catch {
        /* leave default message */
      }
      return { data: null, error: { status: res.status, message } };
    }

    const data = (await res.json()) as T;
    return { data, error: null };
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      // Cancelled by caller — surface as null/null so caller can ignore
      return { data: null, error: null };
    }
    const message = err instanceof Error ? err.message : 'Network error';
    return { data: null, error: { status: 0, message } };
  }
}

/* ── Typed endpoint functions ────────────────────────────── */

/**
 * GET /health — liveness + readiness probe.
 * Never throws; always returns a structured HealthResponse.
 */
export async function getHealth(): Promise<Result<HealthResponse>> {
  return apiFetch<HealthResponse>('/health');
}

/**
 * GET /scope — live verified origins / dest_ports / vessel_classes.
 * Returns empty lists on cold start (not an error).
 */
export async function getScope(): Promise<Result<ScopeResponse>> {
  return apiFetch<ScopeResponse>('/scope');
}

/**
 * POST /recommendation — main chartering recommendation.
 * Latency is solver-bound (up to MILP_SOLVE_TIMEOUT_SECONDS).
 * Pass an AbortSignal to cancel stale in-flight requests.
 */
export async function getRecommendation(
  req: RecommendationRequest,
  signal?: AbortSignal,
): Promise<Result<RecommendationResponse>> {
  return apiFetch<RecommendationResponse>(
    '/recommendation',
    { method: 'POST', body: JSON.stringify(req) },
    signal,
  );
}

/**
 * GET /forecast?route=…&vessel_class=…&horizon_days=…
 */
export async function getForecast(
  route: string,
  vesselClass: string,
  horizonDays: number,
  signal?: AbortSignal,
): Promise<Result<ForecastResponse>> {
  const params = new URLSearchParams({
    route,
    vessel_class: vesselClass,
    horizon_days: String(horizonDays),
  });
  return apiFetch<ForecastResponse>(`/forecast?${params.toString()}`, {}, signal);
}

/**
 * GET /port-status?port=…
 */
export async function getPortStatus(
  port: string,
  signal?: AbortSignal,
): Promise<Result<PortStatusResponse>> {
  const params = new URLSearchParams({ port });
  return apiFetch<PortStatusResponse>(`/port-status?${params.toString()}`, {}, signal);
}

/**
 * POST /chat — Claude tool-calling proxy.
 * ANTHROPIC_API_KEY is held server-side; this call never exposes it.
 * Pass an AbortSignal to cancel a pending Claude turn if the user sends a new message.
 * DOC3 §FEATURE: Chatbot — all chat communication goes through this function.
 */
export async function postChat(
  req: ChatRequest,
  signal?: AbortSignal,
): Promise<Result<ChatResponse>> {
  return apiFetch<ChatResponse>(
    '/chat',
    { method: 'POST', body: JSON.stringify(req) },
    signal,
  );
}

/**
 * GET /fleet-schedule — Step 51V multi-contract fleet portfolio optimization.
 */
export async function getFleetSchedule(
  signal?: AbortSignal,
): Promise<Result<import('./types').FleetScheduleResponse>> {
  return apiFetch<import('./types').FleetScheduleResponse>('/fleet-schedule', {}, signal);
}

/**
 * GET /fleet-status — Live fleet visibility MVP.
 */
export async function getFleetStatus(
  signal?: AbortSignal,
): Promise<Result<import('./types').FleetStatusResponse>> {
  return apiFetch<import('./types').FleetStatusResponse>('/fleet-status', {}, signal);
}

/**
 * GET /vessel-positions — Live vessel coordinates from AIS listener.
 */
export async function getVesselPositions(): Promise<Result<Record<string, any>>> {
  return apiFetch<Record<string, any>>('/vessel-positions');
}

/**
 * POST /narrate — On-demand Groq narrative from Prophet decomposition numbers.
 * Called only when the user opens the Rate Driver panel. Zero cost until viewed.
 * API key stays server-side.
 */
export interface NarrateRequest {
  horizon_days: number;
  trend_delta: number;
  trend_direction: 'rising' | 'falling' | 'flat';
  weekly_seasonality_amplitude: number;
  regressor_effects: Record<string, number>;
  available_regressors: string[];
}

export interface NarrateResponse {
  narrative: string;
  source: 'groq' | 'template';
}

export async function postNarrate(
  req: NarrateRequest,
  signal?: AbortSignal,
): Promise<Result<NarrateResponse>> {
  return apiFetch<NarrateResponse>(
    '/narrate',
    { method: 'POST', body: JSON.stringify(req) },
    signal,
  );
}
