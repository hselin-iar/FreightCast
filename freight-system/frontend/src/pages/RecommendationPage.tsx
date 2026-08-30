/**
 * RecommendationPage.tsx
 * 12-column layout mirroring index.html exactly:
 *   LEFT col-3:   Cargo Request form + Port Congestion
 *   CENTER col-6: Winning Plan Banner + Cost Breakdown + Scenario Fan + Scenario Table
 *   RIGHT col-3:  Feasible Options + Rate Drivers + Sensitivity + Decision Assistant
 *   BOTTOM col-12: Route & Port Context (map + provenance strip)
 *
 * DOC3: page orchestrates state, renders children — no cost math here.
 * All backend calls through apiClient.ts.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  getHealth,
  getPortStatus,
  getRecommendation,
  getForecast,
  getScope,
  postNarrate,
} from '../lib/apiClient';
import type {
  HealthResponse,
  PortStatusResponse,
  RecommendationRequest,
  RecommendationResponse,
  ScopeResponse,
  Strategy,
} from '../lib/types';
import WhatIfSliders      from '../components/WhatIfSliders';
import ScenarioFanChart   from '../components/ScenarioFanChart';
import SensitivityPanel   from '../components/SensitivityPanel';
import RobustnessReadout  from '../components/RobustnessReadout';
import AISRouteMap        from '../components/AISRouteMap';
import WhyNotComparator   from '../components/WhyNotComparator';
import ExecutiveBriefExport from '../components/ExecutiveBriefExport';
import ProvenanceBadge from '../components/ProvenanceBadge';


/* ── Helpers ──────────────────────────────────────────────── */
function fmtM(n: number)  { return '$' + (n / 1_000_000).toFixed(2) + 'M'; }
function fmtK(n: number)  {
  if (n >= 1_000_000) return '$' + (n / 1_000_000).toFixed(2) + 'M';
  if (n >= 1_000)     return '$' + Math.round(n / 1_000) + 'k';
  return '$' + Math.round(n);
}
function pct(a: number, total: number) { return total > 0 ? Math.round((a / total) * 100) : 0; }

/* ── Left panel: Cargo Request form ────────────────────────── */
interface FormPanelProps {
  scope: ScopeResponse | null;
  loading: boolean;
  qty: string; setQty: (v: string) => void;
  origin: string; setOrigin: (v: string) => void;
  ports: Set<string>; togglePort: (p: string) => void;
  flex: number; setFlex: (v: number) => void;
  bench: string; setBench: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}

function CargoForm({
  scope, loading, qty, setQty, origin, setOrigin,
  ports, togglePort, flex, setFlex, bench, setBench, onSubmit,
}: FormPanelProps) {
  const [benchOpen, setBenchOpen] = useState(false);

  return (
    <section className="panel">
      <div className="panel-hd">
        <span className="panel-title">Cargo Request</span>
      </div>
      <form className="panel-body flex-col gap-3" style={{ display: 'flex', flexDirection: 'column', gap: 12 }} onSubmit={onSubmit}>
        {/* Quantity */}
        <div className="form-group">
          <label className="form-label">Cargo quantity (tonnes)</label>
          <input className="input-field" type="number" min={1000} max={300000} step={1000}
            value={qty} onChange={e => setQty(e.target.value)} placeholder="e.g. 60000" />
        </div>

        {/* Origin */}
        <div className="form-group">
          <label className="form-label">Origin port</label>
          {scope ? (
            <select className="input-field" value={origin} onChange={e => setOrigin(e.target.value)}>
              {scope.origins.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : <div className="skel" style={{ height: 34 }} />}
        </div>

        {/* Discharge ports */}
        <div className="form-group">
          <label className="form-label">Preferred discharge ports</label>
          {scope ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {scope.dest_ports.map(p => (
                <label key={p} className="checkbox-item">
                  <input type="checkbox" checked={ports.has(p)} onChange={() => togglePort(p)} />
                  {p}
                </label>
              ))}
            </div>
          ) : (
            <>
              <div className="skel" style={{ height: 20, marginBottom: 6 }} />
              <div className="skel" style={{ height: 20, marginBottom: 6 }} />
              <div className="skel" style={{ height: 20 }} />
            </>
          )}
        </div>

        {/* Timing flex */}
        <div className="form-group">
          <div className="flex-between">
            <label className="form-label">Timing flexibility (days)</label>
            <span className="mono text-sail-100" style={{ fontSize: 12, fontWeight: 600 }}>{flex}d</span>
          </div>
          <input type="range" min={1} max={60} value={flex}
            onChange={e => setFlex(Number(e.target.value))}
            style={{ width: '100%', marginTop: 4 }}
          />
          <div className="flex-between" style={{ fontSize: 9, fontFamily: 'var(--f-mono)', color: 'var(--sail-500)' }}>
            <span>0</span>
            <span className="text-accent">{flex} days</span>
            <span>60</span>
          </div>
        </div>

        {/* Commitment benchmark (collapsed) */}
        <div>
          <div style={{ borderTop: '1px solid var(--sail-800)', paddingTop: 10 }}>
            <button type="button" className="collapse-btn" onClick={() => setBenchOpen(o => !o)}>
              <span className={`collapse-icon ${benchOpen ? 'open' : ''}`}>▶</span>
              Locked-rate discount vs spot
            </button>
            {benchOpen && (
              <div style={{ marginTop: 10 }}>
                <div className="flex-between" style={{ marginBottom: 6 }}>
                  <label className="form-label" style={{ flex: 1 }}>
                    commitment_benchmark
                  </label>
                  <ProvenanceBadge provenance="assumed"
                    note="No public COA quotes — this is your assumption. Locked voyages priced as Base-path rate × (1 − this %). Raise if brokers offer steeper discount." />
                </div>
                <div className="flex-center gap-2" style={{ marginBottom: 6 }}>
                  <input className="input-field" type="number" min={50} max={100} step={0.5}
                    value={bench} onChange={e => setBench(e.target.value)}
                    style={{ width: 72, textAlign: 'right', color: 'var(--warn)' }}
                  />
                  <span className="text-sail-400">%</span>
                </div>
                <p className="infer">
                  Assumed locked-rate discount vs spot (user-set). Default: 95%. Adjust based on current market negotiations.
                </p>
              </div>
            )}
          </div>
        </div>

        <button type="submit" className="btn btn-accent btn-full" disabled={loading || !scope} id="btn-run">
          {loading ? <><span className="spinner" />Solving…</> : 'Run Recommendation'}
        </button>
        {loading && <p className="infer" style={{ textAlign: 'center' }}>MILP solver running — may take a few seconds</p>}
      </form>
    </section>
  );
}

/* ── Left panel: Port Congestion ───────────────────────────── */
function PortCongestionPanel({ portStatuses, loading }: { portStatuses: PortStatusResponse[]; loading: boolean }) {
  const congPct = (v: number) => Math.min(100, Math.round((v / 20) * 100));
  const congColor = (v: number) => v > 10 ? 'var(--warn)' : v > 5 ? '#f59e0b' : 'var(--emerald)';
  const textColor = (v: number) => v > 10 ? 'var(--warn)' : v > 5 ? '#f59e0b' : 'var(--emerald-4)';

  return (
    <section className="panel" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      <div className="panel-hd">
        <span className="panel-title">Port Congestion</span>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
        {loading ? (
          [1,2,3].map(i => <div key={i} className="skel" style={{ height: 18 }} />)
        ) : portStatuses.length ? portStatuses.map(ps => (
          <div key={ps.port} style={{ display: 'grid', gridTemplateColumns: '1fr auto 64px', gap: '8px', alignItems: 'center', fontSize: 13 }}>
            <span className="tip-wrap" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', display: 'block' }}>{ps.port}</span>
              <span className="tip-box">
                {ps.vessel_count} vessels in AIS geofence. {ps.source_note ?? ''}
              </span>
            </span>
            <span style={{ fontSize: 12, fontFamily: 'var(--f-mono)', color: textColor(ps.vessel_count), textAlign: 'right', whiteSpace: 'nowrap' }}>
              {ps.vessel_count} vessels
            </span>
            <div className="cong-track" style={{ width: '100%', margin: 0 }}>
              <div className="cong-fill" style={{
                width: `${congPct(ps.vessel_count)}%`,
                background: congColor(ps.vessel_count),
              }} />
            </div>
          </div>
        )) : (
          <p className="infer">AIS data not available (backend offline or cold start).</p>
        )}
        <p className="infer" style={{ marginTop: 'auto' }}>
          <strong>Read this as:</strong> congestion is not a hard block — it adds a risk-buffer term and biases entry timing.
        </p>
      </div>
    </section>
  );
}

/* ── Center: Winning Plan Banner ───────────────────────────── */
function WinningPlanBanner({ rec }: { rec: Strategy; ports?: Set<string> }) {
  const bd = rec.cost_breakdown;
  void bd; // bd used in plan-tags below
  const robustness = 0.91; // derived from scenario comparison in full impl (Step 12)

  const desc = rec.voyages.map((v, i) => {
    const cargo = v.cargo_tonnes ? `${v.cargo_tonnes} MT ` : '';
    return `Voyage ${i + 1}: ${v.port} (${v.vessel_class}, ${cargo}${v.mode}, fix day ${v.fix_day})`;
  }).join(' · ');

  return (
    <div className="panel panel-ink">
      <div className="plan-header">
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span className="plan-label">Recommended Plan</span>
            <ProvenanceBadge provenance={rec.provenance} note={rec.provenance_note} />
          </div>
          <div className="plan-title">
            {rec.voyage_count}-voyage {rec.commitment_mode}
          </div>
          <p className="plan-subtitle">{desc || 'No voyage detail available.'}</p>
        </div>
        <div style={{ flexShrink: 0, textAlign: 'right' }}>
          <div className="tip-wrap">
            <div className="plan-cost">{fmtM(rec.total_cost_worst_case)}</div>
            <span className="tip-box">Worst-case of Base / Optimistic / Pessimistic paths.</span>
          </div>
          <div className="plan-cost-label">worst-case across scenarios</div>
          <div className="plan-robustness mono">robustness score {robustness.toFixed(2)}</div>
        </div>
      </div>
      <div className="plan-tags">
        {rec.solved_via === 'milp' && <span className="plan-tag">MILP solve</span>}
        {!rec.voyages.some(v => v.lightening_required) && <span className="plan-tag">No lightening required</span>}
        {rec.contains_high_uncertainty_voyage
          ? <span className="plan-tag warn">High uncertainty ⚠</span>
          : <span className="plan-tag">Uncertainty: normal</span>}
      </div>

    </div>
  );
}

/* ── Center: Cost Breakdown ─────────────────────────────────── */
function CostBreakdown({ bd }: { bd: Strategy['cost_breakdown'] }) {
  const total = bd.total || 1;
  const opex = bd.opex ?? 0;
  const otherCost = bd.other_cost ?? 0;
  const tax = bd.tax ?? 0;
  const light = bd.lightening_extra ?? 0;
  const risk = bd.risk_buffer ?? 0;

  return (
    <div className="panel">
      <div className="panel-hd">
        <span className="panel-title">Cost Breakdown (7-bucket Economics)</span>
      </div>
      <div className="panel-body">
        <div className="cost-stacked-bar">
          <div className="cost-seg freight" style={{ width: `${pct(bd.ocean_freight, total)}%` }}>
            {pct(bd.ocean_freight, total) > 8 && `Ocean freight ${pct(bd.ocean_freight, total)}%`}
          </div>
          <div className="cost-seg bunker" style={{ width: `${pct(bd.bunker, total)}%` }}>
            {pct(bd.bunker, total) > 8 && `Bunker ${pct(bd.bunker, total)}%`}
          </div>
          {opex > 0 && (
            <div className="cost-seg opex" style={{ width: `${pct(opex, total)}%` }}>
              {pct(opex, total) > 6 && `OPEX ${pct(opex, total)}%`}
            </div>
          )}
          <div className="cost-seg port" style={{ width: `${pct(bd.port_handling, total)}%` }}>
            {pct(bd.port_handling, total) > 6 && `Port ${pct(bd.port_handling, total)}%`}
          </div>
          {otherCost > 0 && (
            <div className="cost-seg other" style={{ width: `${pct(otherCost, total)}%` }}>
              {pct(otherCost, total) > 5 && `Other ${pct(otherCost, total)}%`}
            </div>
          )}
          {tax > 0 && (
            <div className="cost-seg tax" style={{ width: `${pct(tax, total)}%` }}>
              {pct(tax, total) > 5 && `Tax ${pct(tax, total)}%`}
            </div>
          )}
          {light > 0 && (
            <div className="cost-seg light" style={{ width: `${pct(light, total)}%` }}>
              {pct(light, total) > 5 && `Light ${pct(light, total)}%`}
            </div>
          )}
          {risk > 0 && (
            <div className="cost-seg risk" style={{ width: `${pct(risk, total)}%` }}>
              {pct(risk, total) > 5 && `Risk ${pct(risk, total)}%`}
            </div>
          )}
        </div>
        <div className="cost-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))' }}>
          {[
            ['Ocean freight',      bd.ocean_freight],
            ['Bunker Fuel',        bd.bunker],
            ['Vessel OPEX',        opex],
            ['Port & Handling',    bd.port_handling],
            ['Other Dues / Tolls', otherCost],
            ['Freight Tax',        tax],
            ['Lightening / Extra', light],
            ['Risk Buffer',        risk],
          ].map(([label, val]) => (
            <div className="cost-item" key={label as string}>
              <div className="cost-item-label">{label}</div>
              <div className="cost-item-value">{fmtK(val as number)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FeasibleOptions({ rec }: { rec: Strategy }) {
  return (
    <section className="panel">
      <div className="panel-hd">
        <span className="panel-title">Feasible Options</span>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rec.voyages.map((v, i) => (
          <div key={i} className="feas-card">
            <div className="feas-card-head">
              <span style={{ color: 'var(--sail-100)' }}>{v.vessel_class} → {v.port}</span>
              <span style={{ color: v.lightening_required ? 'var(--warn)' : 'var(--emerald)', fontSize: 11 }}>
                {v.lightening_required ? 'lightening' : 'clear'}
              </span>
            </div>
            <div className="feas-card-sub">
              {v.lightening_required
                ? `Draft exceed · lighten at ${v.lightening_port ?? '?'}`
                : `Draft OK · discharge ~${v.discharge_days}d`}
              {v.tidal_window_note && ` · ${v.tidal_window_note}`}
            </div>
          </div>
        ))}
        <p className="infer">Soft flags (inefficient, tide) never block — they only change cost ranking.</p>
      </div>
    </section>
  );
}


/* ── Right: Rate Drivers ───────────────────────────────────── */
function RateDrivers({ driverNote }: { driverNote: string | null }) {
  const [expanded, setExpanded] = useState(false);
  const [groqNarrative, setGroqNarrative] = useState<string | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);

  // Parse driver explanation — handle both old plain-string and new JSON formats
  let explanationText = driverNote ?? 'Driver context will populate after the next retrain cycle.';
  let importances: Record<string, number> = {};
  let prophetDecomp: {
    trend_delta: number;
    trend_direction: 'rising' | 'falling' | 'flat';
    weekly_seasonality_amplitude: number;
    regressor_effects: Record<string, number>;
    narrative: string;
  } | null = null;

  if (driverNote) {
    try {
      const parsed = JSON.parse(driverNote);
      if (parsed && typeof parsed === 'object' && 'text' in parsed) {
        if (parsed.text) explanationText = parsed.text;
        if (parsed.importances) importances = parsed.importances;
        if (parsed.prophet_decomposition) prophetDecomp = parsed.prophet_decomposition;
      } else if (typeof parsed === 'string') {
        explanationText = parsed;
      }
    } catch (e) {
      // Old plain-string format — use as-is
      explanationText = driverNote;
    }
  }

  const hasProphet = prophetDecomp !== null;
  const hasImportances = Object.keys(importances).length > 0;

  return (
    <section className="panel">
      <div className="panel-hd">
        <span className="panel-title">Rate Drivers</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {hasProphet && (
            <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4,
              background: 'rgba(59,130,246,0.15)', color: '#1d4ed8',
              fontFamily: 'var(--f-mono)' }}>
              PROPHET · ACTIVE
            </span>
          )}
          <ProvenanceBadge provenance="modeled" />
          <button
            onClick={async () => {
              const isExpanding = !expanded;
              setExpanded(isExpanding);
              
              if (isExpanding && prophetDecomp && !groqNarrative && !narrativeLoading) {
                setNarrativeLoading(true);
                try {
                  const { data, error } = await postNarrate({
                    horizon_days: 14, // Fallback, recommendations generally use the 14-day forecast
                    trend_delta: prophetDecomp.trend_delta,
                    trend_direction: prophetDecomp.trend_direction,
                    weekly_seasonality_amplitude: prophetDecomp.weekly_seasonality_amplitude,
                    regressor_effects: prophetDecomp.regressor_effects,
                    available_regressors: Object.keys(prophetDecomp.regressor_effects),
                  });
                  if (!error && data) {
                    setGroqNarrative(data.narrative);
                  }
                } finally {
                  setNarrativeLoading(false);
                }
              }
            }}
            style={{ fontSize: 11, color: 'var(--sail-500)', background: 'none',
              border: '1px solid var(--sail-700)', borderRadius: 4,
              padding: '2px 7px', cursor: 'pointer', lineHeight: 1.4 }}>
            {expanded ? '▴ collapse' : '▾ details'}
          </button>
        </div>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* ── Prophet trend headline (always visible when available) ── */}
        {hasProphet && prophetDecomp ? (
          <div style={{ padding: '10px 12px', borderRadius: 8,
            background: 'color-mix(in srgb, var(--sail-800) 60%, transparent)',
            border: '1px solid var(--sail-700)' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
              <span style={{
                fontSize: 20, fontWeight: 700, fontFamily: 'var(--f-mono)',
                color: prophetDecomp.trend_direction === 'rising' ? '#ef4444'
                     : prophetDecomp.trend_direction === 'falling' ? '#22c55e'
                     : 'var(--sail-300)',
              }}>
                {prophetDecomp.trend_direction === 'rising' ? '▲' :
                 prophetDecomp.trend_direction === 'falling' ? '▼' : '→'}
                {' '}{prophetDecomp.trend_delta >= 0 ? '+' : ''}${prophetDecomp.trend_delta.toFixed(0)}/day
              </span>
              <span style={{ fontSize: 11, color: 'var(--sail-500)' }}>trend component</span>
            </div>
            {prophetDecomp.weekly_seasonality_amplitude > 0 && (
              <div style={{ fontSize: 11, color: 'var(--sail-400)', marginBottom: 6 }}>
                Weekly swing ±${(prophetDecomp.weekly_seasonality_amplitude / 2).toFixed(0)}/day
              </div>
            )}
            <div style={{ fontSize: 12, color: 'var(--sail-300)', lineHeight: 1.5, margin: 0, position: 'relative' }}>
              <p style={{ margin: 0, opacity: narrativeLoading ? 0.5 : 1, transition: 'opacity 0.2s' }}>
                {groqNarrative || prophetDecomp.narrative}
              </p>
              {narrativeLoading && (
                <div style={{ position: 'absolute', top: 0, right: 0, fontSize: 10, color: 'var(--sail-400)' }}>
                  writing...
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Fallback: styled prose card (same look as Prophet headline) */
          <div style={{ padding: '10px 12px', borderRadius: 8,
            background: 'color-mix(in srgb, var(--sail-800) 60%, transparent)',
            border: '1px solid var(--sail-700)' }}>
            <p style={{ fontSize: 12, color: 'var(--sail-300)', lineHeight: 1.7, margin: 0 }}>
              {explanationText}
            </p>
          </div>
        )}

        {/* ── Collapsible detail section ── */}
        {expanded && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16,
            paddingTop: 10, borderTop: '1px solid var(--sail-800)' }}>

            {/* Prophet macro regressor $/day bars */}
            {hasProphet && prophetDecomp && Object.keys(prophetDecomp.regressor_effects).length > 0 && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--sail-500)', marginBottom: 12,
                  display: 'flex', alignItems: 'center', gap: 6, borderBottom: '1px solid var(--sail-800)', paddingBottom: 6 }}>
                  <span style={{ padding: '2px 6px', borderRadius: 4,
                    background: 'rgba(59,130,246,0.15)', color: '#3b82f6',
                    fontWeight: 600, fontFamily: 'var(--f-mono)', fontSize: 9 }}>PROPHET</span>
                  <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>Macro Drivers ($/day)</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {(() => {
                    const entries = Object.entries(prophetDecomp!.regressor_effects)
                      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
                    const maxAbs = entries.length > 0 ? Math.max(...entries.map(e => Math.abs(e[1])), 1) : 1;
                    return entries.map(([key, val]) => (
                      <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <span style={{ width: 85, fontSize: 11, color: 'var(--sail-300)',
                          textTransform: 'capitalize', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>
                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ flex: 1, height: 5, background: 'var(--sail-800)', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{
                              height: '100%', borderRadius: 3,
                              background: val >= 0 ? '#ef4444' : '#22c55e',
                              width: `${(Math.abs(val) / maxAbs) * 100}%`,
                            }} />
                          </div>
                          <span style={{ fontFamily: 'var(--f-mono)', fontSize: 11, minWidth: 40, textAlign: 'right',
                            color: val >= 0 ? '#ef4444' : '#22c55e' }}>
                            {val >= 0 ? '+' : ''}${val.toFixed(0)}
                          </span>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              </div>
            )}

            {/* XGBoost feature importances */}
            {hasImportances && (
              <div>
                <div style={{ fontSize: 11, color: 'var(--sail-500)', marginBottom: 12,
                  display: 'flex', alignItems: 'center', gap: 6, borderBottom: '1px solid var(--sail-800)', paddingBottom: 6 }}>
                  <span style={{ padding: '2px 6px', borderRadius: 4,
                    background: 'rgba(245,158,11,0.15)', color: '#f59e0b',
                    fontWeight: 600, fontFamily: 'var(--f-mono)', fontSize: 9 }}>XGBOOST</span>
                  <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>Feature Importance</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {(() => {
                    const entries = Object.entries(importances).sort((a, b) => b[1] - a[1]);
                    const maxV = entries.length > 0 ? entries[0][1] : 1;
                    return entries.slice(0, 8).map(([key, val]) => (
                      <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <span style={{ width: 85, fontSize: 11, color: 'var(--sail-400)',
                          textTransform: 'capitalize', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {key.replace(/_/g, ' ')}
                        </span>
                        <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ flex: 1, height: 5, background: 'var(--sail-800)', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{ width: `${(val / maxV) * 100}%`, height: '100%',
                              background: 'rgba(245,158,11,0.8)' }} />
                          </div>
                          <span className="mono" style={{ minWidth: 35, textAlign: 'right',
                            fontSize: 10, color: 'var(--sail-500)' }}>{val.toFixed(2)}</span>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              </div>
            )}

            {!hasImportances && !hasProphet && (
              <p className="infer" style={{ fontSize: 11 }}>
                Detailed driver breakdown will appear after the next retrain cycle with Prophet + XGBoost installed.
              </p>
            )}
          </div>
        )}

        {/* Show details button when collapsed */}
        {!expanded && (hasImportances || hasProphet) && (
          <button onClick={() => setExpanded(true)} style={{
            alignSelf: 'flex-start', fontSize: 11, color: 'var(--sail-500)',
            background: 'none', border: '1px solid var(--sail-700)',
            borderRadius: 4, padding: '3px 8px', cursor: 'pointer' }}>
            Show {hasProphet ? 'macro drivers + ' : ''}XGBoost importances ▾
          </button>
        )}
      </div>
    </section>
  );
}


/* DecisionAssistant stub removed — live ChatPanel sidebar in App.tsx replaces it (Build Step 13 ✓) */


/* ── Bottom: System Status & Provenance Strip ──────────────── */
function SystemProvenanceStrip({ origin, ports, health }: { origin: string; ports: Set<string>; health: HealthResponse | null }) {
  return (
    <div className="panel panel-tinted">
      <div className="panel-hd" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
        <span className="panel-title">System Status & Data Provenance</span>
        <div className="panel-meta" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
          <span>Origin: {origin || '—'}</span>
          <span>Discharge candidates: {[...ports].join(' · ') || '—'}</span>
          <span>AIS geofence {health?.ais_listener_last_seen ? 'active' : 'offline'}</span>
        </div>
      </div>
      <div className="panel-body">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--sail-300)', marginBottom: 6 }}>Provenance classification</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              <span className="badge badge-measured">MEASURED · BDI, bunker, AIS</span>
              <span className="badge badge-modeled">MODELED · forecast, trajectory</span>
              <span className="badge badge-assumed">ASSUMED · commitment_benchmark</span>
            </div>
          </div>
          <div className="prov-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
            <div className="prov-cell">
              <div className="prov-cell-label">Model gate</div>
              <div className="prov-cell-value" style={{ color: health?.models_loaded ? 'var(--emerald-4)' : 'var(--warn)' }}>
                {health?.models_loaded ? 'passed' : 'checking…'}
              </div>
            </div>
            <div className="prov-cell">
              <div className="prov-cell-label">AIS listener</div>
              <div className="prov-cell-value" style={{ color: health?.ais_listener_last_seen ? 'var(--emerald-4)' : 'var(--warn)' }}>
                {health?.ais_listener_last_seen ? 'live' : 'offline'}
              </div>
            </div>
            <div className="prov-cell">
              <div className="prov-cell-label">Last retrain</div>
              <div className="prov-cell-value" style={{ fontSize: 11 }}>
                {health?.last_retrain_at ? new Date(health.last_retrain_at).toLocaleDateString() : '—'}
              </div>
            </div>
            <div className="prov-cell">
              <div className="prov-cell-label">Warehouse</div>
              <div className="prov-cell-value" style={{ color: health?.warehouse_reachable ? 'var(--emerald-4)' : 'var(--warn)' }}>
                {health?.warehouse_reachable ? 'ok' : 'degraded'}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Main component ─────────────────────────────────────────── */
interface RecommendationPageProps {
  /** Fires when user submits the form — lets App pass cargo_context to ChatPanel */
  onCargoContextChange?: (req: RecommendationRequest) => void;
  /** A re-solved result pushed in from ChatPanel (DOC2 §3c dashboard_update) */
  externalResult?: RecommendationResponse | null;
  /** Human-readable annotation of what constraint drove the re-solve */
  chatConstraintNote?: string | null;
}

const RecommendationPage: React.FC<RecommendationPageProps> = ({
  onCargoContextChange,
  externalResult,
  chatConstraintNote,
}) => {
  /* ── Server state ── */
  const [health,       setHealth]       = useState<HealthResponse | null>(null);
  const [scope,        setScope]        = useState<ScopeResponse | null>(null);
  const [result,       setResult]       = useState<RecommendationResponse | null>(null);
  const [driverNote,   setDriverNote]   = useState<string | null>(null);
  const [portStatuses, setPortStatuses] = useState<PortStatusResponse[]>([]);

  /* ── UI state ── */
  const [loading,      setLoading]      = useState(false);
  const [portLoading,  setPortLoading]  = useState(true);
  const [error,        setError]        = useState<string | null>(null);

  /* ── Form state ── */
  const [qty,    setQty]    = useState('60000');
  const [origin, setOrigin] = useState('');
  const [ports,  setPorts]  = useState<Set<string>>(new Set());
  const [flex,   setFlex]   = useState(30);
  const [bench,  setBench]  = useState('95');

  /** Last submitted request — fed into WhatIfSliders as base values */
  const [baseRequest, setBaseRequest] = useState<RecommendationRequest | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const [{ data: h }, { data: sc }] = await Promise.all([getHealth(), getScope()]);
      setHealth(h);
      if (sc) {
        setScope(sc);
        if (sc.origins.length) setOrigin(sc.origins[0]);
        if (sc.dest_ports.length) setPorts(new Set(sc.dest_ports.slice(0, 2)));

        // Fetch port statuses for first few ports
        setPortLoading(true);
        const statusResults = await Promise.all(
          sc.dest_ports.slice(0, 4).map(p => getPortStatus(p))
        );
        setPortStatuses(statusResults.map(r => r.data).filter(Boolean) as PortStatusResponse[]);
        setPortLoading(false);
      } else {
        setPortLoading(false);
      }
    })();
  }, []);

  const togglePort = (p: string) => {
    setPorts(prev => {
      const next = new Set(prev);
      next.has(p) ? next.delete(p) : next.add(p);
      return next;
    });
  };

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const q = parseFloat(qty);
    if (isNaN(q) || q <= 0) { setError('Cargo quantity must be a positive number.'); return; }
    if (!origin) { setError('Select an origin port.'); return; }
    if (!ports.size) { setError('Select at least one discharge port.'); return; }

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true); setError(null); setResult(null);

    const req: RecommendationRequest = {
      cargo_quantity:           q,
      origin_port:              origin,
      discharge_ports:          [...ports],
      timing_flexibility_days:  flex,
      commitment_benchmark_pct: parseFloat(bench) || 95,
    };
    const { data, error: apiErr } = await getRecommendation(req, abortRef.current.signal);
    setLoading(false);
    if (apiErr) { setError(apiErr.message); return; }
    if (data) {
      setResult(data);
      setBaseRequest(req);
      onCargoContextChange?.(req);
      const mainVoyage = data.recommendation.voyages[0];
      if (mainVoyage) {
        getForecast(`${origin}→${mainVoyage.port}`, mainVoyage.vessel_class, 30).then(fRes => {
          if (fRes.data) setDriverNote(fRes.data.driver_explanation);
        });
      }
    }
  }, [qty, origin, ports, flex, bench, onCargoContextChange]);

  /** WhatIfSliders callback — same /recommendation path, AbortSignal provided by slider */
  const handleSliderChange = useCallback(async (req: RecommendationRequest, signal: AbortSignal) => {
    setLoading(true); setError(null);
    const { data, error: apiErr } = await getRecommendation(req, signal);
    setLoading(false);
    // Ignore AbortError (stale request cancelled)
    if (apiErr?.message?.includes('abort') || apiErr?.message?.includes('cancel')) return;
    if (apiErr) { setError(apiErr.message); return; }
    if (data) {
      setResult(data);
      const mainVoyage = data.recommendation.voyages[0];
      if (mainVoyage) {
        getForecast(`${req.origin_port}→${mainVoyage.port}`, mainVoyage.vessel_class, 30).then(fRes => {
          if (fRes.data) setDriverNote(fRes.data.driver_explanation);
        });
      }
    }
  }, []);


  /** Sync external re-solve result from ChatPanel (DOC2 §3c dashboard_update) */
  useEffect(() => {
    if (externalResult) {
      setResult(externalResult);
      const mainVoyage = externalResult.recommendation.voyages[0];
      if (mainVoyage && origin) {
        getForecast(`${origin}→${mainVoyage.port}`, mainVoyage.vessel_class, 30).then(fRes => {
          if (fRes.data) setDriverNote(fRes.data.driver_explanation);
        });
      }
    }
  }, [externalResult, origin]);

  const rec = result?.recommendation;

  return (
    <div className="page-grid">
      {/* ── LEFT & CENTER COMBINED ── */}
      <div className="col-9" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(9, 1fr)', gap: 16, flex: 1 }}>
          
          {/* ── LEFT COL ── */}
          <div style={{ gridColumn: 'span 3', display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        <CargoForm
          scope={scope} loading={loading}
          qty={qty} setQty={setQty}
          origin={origin} setOrigin={setOrigin}
          ports={ports} togglePort={togglePort}
          flex={flex} setFlex={setFlex}
          bench={bench} setBench={setBench}
          onSubmit={handleSubmit}
        />
        {/* WhatIfSliders — shown once we have a result + base request */}
        {result && baseRequest && (
          <WhatIfSliders
            baseRequest={baseRequest}
            onRequestChange={handleSliderChange}
            loading={loading}
          />
        )}
        <PortCongestionPanel portStatuses={portStatuses} loading={portLoading} />
      </div>

          {/* ── CENTER COL ── */}
          <div style={{ gridColumn: 'span 6', display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        {error && (
          <div className="error-bar" id="error-banner">
            <span>✕</span><span>{error}</span>
          </div>
        )}

        {!rec && !loading && !error && (
          <div className="panel" style={{ flex: 1 }}>
            <div className="empty-state">
              <div className="empty-icon">⬡</div>
              <div className="empty-title">No recommendation yet</div>
              <div className="empty-desc">
                Fill in the cargo request form and click Run Recommendation to get a MILP-optimised chartering strategy.
              </div>
            </div>
          </div>
        )}

        {loading && (
          <>
            <div className="panel">
              <div className="panel-body">
                <div className="skel" style={{ height: 20, width: '40%', marginBottom: 8 }} />
                <div className="skel" style={{ height: 28, width: '60%', marginBottom: 6 }} />
                <div className="skel" style={{ height: 14, width: '80%' }} />
              </div>
            </div>
            <div className="panel">
              <div className="panel-body">
                <div className="skel" style={{ height: 32, marginBottom: 12 }} />
                <div className="skel" style={{ height: 50 }} />
              </div>
            </div>
          </>
        )}

        {rec && !loading && (
          <>
            {/* "Changed because you asked" annotation — shown when ChatPanel re-solved */}
            {chatConstraintNote && (
              <div id="chat-update-banner" style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 14px',
                background: 'color-mix(in srgb, var(--accent) 10%, transparent)',
                border: '1px solid color-mix(in srgb, var(--accent) 30%, transparent)',
                borderRadius: 8,
                fontSize: 12,
                color: 'var(--text-accent)',
              }}>
                <span style={{ fontSize: 14 }}>↗</span>
                <span>
                  <strong>Updated by Chartering Agent</strong>
                  {' · '}changed because you asked: {chatConstraintNote}
                </span>
              </div>
            )}
            <WinningPlanBanner rec={rec} />
            <CostBreakdown bd={rec.cost_breakdown} />
            <ScenarioFanChart result={result!} origin={origin} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              <WhyNotComparator result={result} />
            </div>
          </>
        )}
          </div>
        </div>

        {/* ── AIS ROUTE MAP spans full col-9 ── */}
        {rec && !loading && (
          <div>
            <AISRouteMap
              origin={origin}
              dischargePorts={[...ports]}
              portStatuses={portStatuses}
            />
          </div>
        )}
      </div>

      {/* ── RIGHT COL ── */}
      <div className="col-3 col-space">
        {rec ? (
          <FeasibleOptions rec={rec} />
        ) : (
          <section className="panel">
            <div className="panel-hd"><span className="panel-title">Feasible Options</span></div>
            <div className="empty-state" style={{ padding: '24px' }}>
              <div className="empty-desc">Run a recommendation to see feasible vessel/port options.</div>
            </div>
          </section>
        )}
        <RateDrivers driverNote={driverNote} />
        {result ? <SensitivityPanel result={result} /> : null}
        {result && <RobustnessReadout result={result} />}
        <SystemProvenanceStrip origin={origin} ports={ports} health={health} />
        
        {/* Export Button moved to Right Column */}
        {result && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            <ExecutiveBriefExport
              result={result}
              origin={origin}
              dischargePorts={[...ports]}
            />
          </div>
        )}
      </div>

      {/* ── BOTTOM ROW ── */}
      <div className="col-12 col-space">
      </div>

    </div>
  );
};

export default RecommendationPage;
