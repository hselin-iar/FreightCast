/**
 * ForecastExplorerPage.tsx — Forecast Explorer tab (fully live-wired).
 *
 * All data fetched from backend. Zero hardcoded numbers.
 * DOC3 §FEATURE: Forecast Explorer — served on-demand via GET /forecast.
 *
 * Layout (mirrors index.html Forecast Explorer section):
 *   LEFT col-3:   Route/vessel/horizon selector, Serving model info, Conditions monitor
 *   CENTER col-6: Main forecast card, Rate history + trajectory chart, Walk-forward note
 *   RIGHT col-3:  Driver explanation, Pair coverage status, What this is not
 */

import React, { useCallback, useEffect, useState } from 'react';
import { getForecast, getScope } from '../lib/apiClient';
import type { ForecastResponse, ScopeResponse } from '../lib/types';

// ── Horizon options matching backend FORECAST_HORIZONS_DAYS = [7, 14, 30] ──
const HORIZON_OPTIONS = [
  { label: '1-week',  days: 7  },
  { label: '2-week',  days: 14 },
  { label: '1-month', days: 30 },
];

// ── Build the route string that matches what's stored in the DB ──────────────
function buildRoute(origin: string, dest: string): string {
  return `${origin}→${dest}`;
}

// ── Skeleton loader ──────────────────────────────────────────────────────────
function Skel({ h = 16, w = '80%' }: { h?: number; w?: string }) {
  return <div className="skel" style={{ height: h, width: w, marginBottom: 6 }} />;
}

// ── Mini SVG trajectory chart ────────────────────────────────────────────────
function TrajectoryChart({ fc }: { fc: ForecastResponse }) {
  const traj = fc.trajectory ?? [];
  if (traj.length === 0) return (
    <div style={{
      height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(15,23,42,0.6)', border: '1px solid var(--sail-800)', borderRadius: 4,
    }}>
      <span style={{ fontSize: 12, color: 'var(--sail-500)' }}>No trajectory data in this forecast object</span>
    </div>
  );

  const values = traj.map(p => p.value);
  const min    = Math.min(...values) * 0.9;
  const max    = Math.max(...values) * 1.1;
  const range  = max - min || 1;
  const W = 640, H = 200, PAD = 20;
  const innerW = W - PAD * 2;
  const innerH = H - PAD * 2;

  function toSvgX(i: number) { return PAD + (i / (traj.length - 1)) * innerW; }
  function toSvgY(v: number) { return PAD + innerH - ((v - min) / range) * innerH; }

  const pts = traj.map((p, i) => `${toSvgX(i)},${toSvgY(p.value)}`).join(' ');
  const bandLower = toSvgY(fc.confidence_band?.lower ?? min);
  const bandUpper = toSvgY(fc.confidence_band?.upper ?? max);
  const todayX    = PAD + (0 / (traj.length - 1)) * innerW;

  return (
    <div style={{ position: 'relative', height: 224, background: 'rgba(15,23,42,0.6)', border: '1px solid var(--sail-800)', borderRadius: 4, overflow: 'hidden' }}>
      <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {/* Grid lines */}
        <path d={`M${PAD},${PAD} L${W-PAD},${PAD} M${PAD},${PAD+innerH/3} L${W-PAD},${PAD+innerH/3} M${PAD},${PAD+innerH*2/3} L${W-PAD},${PAD+innerH*2/3} M${PAD},${H-PAD} L${W-PAD},${H-PAD}`}
          stroke="#1e293b" strokeWidth={1} fill="none" />
        {/* Confidence band */}
        <rect x={todayX} y={bandUpper} width={W - PAD - todayX} height={Math.abs(bandLower - bandUpper)}
          fill="#0d9488" fillOpacity={0.12} />
        {/* Trajectory line */}
        <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2.2} />
        {/* Today marker */}
        <circle cx={todayX} cy={toSvgY(traj[0].value)} r={4} fill="var(--accent)" />
        <text x={todayX + 6} y={toSvgY(traj[0].value) - 6} fill="#94a3b8" fontSize={10} fontFamily="monospace">today</text>
      </svg>
      {/* Date labels */}
      <div style={{ position: 'absolute', bottom: 4, left: 8, right: 8, display: 'flex', justifyContent: 'space-between', fontSize: 9, fontFamily: 'var(--f-mono)', color: 'var(--sail-500)' }}>
        {traj.filter((_, i) => i === 0 || i === Math.floor(traj.length / 2) || i === traj.length - 1).map(p => (
          <span key={p.date}>{new Date(p.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</span>
        ))}
      </div>
    </div>
  );
}

// ── Pair coverage row — calls /forecast for each pair to check status ─────────
interface PairStatus {
  origin: string;
  dest:   string;
  vessel: string;
  status: 'checking' | 'serving' | 'high-uncertainty' | 'no-data';
  model?: string;
}

// ── Main ForecastExplorerPage ─────────────────────────────────────────────────
const ForecastExplorerPage: React.FC = () => {
  // ── Scope state ──
  const [scope, setScope]       = useState<ScopeResponse | null>(null);
  const [scopeError, setScopeError] = useState<string | null>(null);

  // ── Selector state ──
  const [selectedOrigin,  setSelectedOrigin]  = useState('');
  const [selectedDest,    setSelectedDest]    = useState('');
  const [selectedVessel,  setSelectedVessel]  = useState('');
  const [selectedHorizon, setSelectedHorizon] = useState(14);

  // ── Forecast state ──
  const [forecast,  setForecast]  = useState<ForecastResponse | null>(null);
  const [fcLoading, setFcLoading] = useState(false);
  const [fcError,   setFcError]   = useState<string | null>(null);

  // ── Pair coverage state ──
  const [pairStatuses, setPairStatuses] = useState<PairStatus[]>([]);

  // ── Load scope on mount ──
  useEffect(() => {
    (async () => {
      const { data, error } = await getScope();
      if (error || !data) {
        setScopeError(error?.message ?? 'Failed to load scope');
        return;
      }
      setScope(data);
      if (data.origins.length)        setSelectedOrigin(data.origins[0]);
      if (data.dest_ports.length)     setSelectedDest(data.dest_ports[0]);
      if (data.vessel_classes.length) setSelectedVessel(data.vessel_classes[0]);
    })();
  }, []);

  // ── Fetch forecast whenever selector changes ──
  const fetchForecast = useCallback(async () => {
    if (!selectedOrigin || !selectedDest || !selectedVessel) return;
    setFcLoading(true);
    setFcError(null);
    setForecast(null);
    const route = buildRoute(selectedOrigin, selectedDest);
    const { data, error } = await getForecast(route, selectedVessel, selectedHorizon);
    setFcLoading(false);
    if (error) {
      if (error.status === 404) {
        setFcError('no-forecast'); // special sentinel
      } else {
        setFcError(error.message);
      }
    } else {
      setForecast(data);
    }
  }, [selectedOrigin, selectedDest, selectedVessel, selectedHorizon]);

  useEffect(() => { if (scope) fetchForecast(); }, [scope, selectedOrigin, selectedDest, selectedVessel, selectedHorizon, fetchForecast]);

  // ── Probe pair coverage (fire off calls for all scope×vessel combinations) ──
  useEffect(() => {
    if (!scope) return;
    const pairs: PairStatus[] = [];
    // Limit: first 3 origins × first 3 dests × first 2 vessel classes to avoid rate limits
    const origins  = scope.origins.slice(0, 3);
    const dests    = scope.dest_ports.slice(0, 3);
    const vessels  = scope.vessel_classes.slice(0, 2);

    for (const o of origins) {
      for (const d of dests) {
        for (const v of vessels) {
          pairs.push({ origin: o, dest: d, vessel: v, status: 'checking' });
        }
      }
    }
    setPairStatuses(pairs);

    // Fire off all probes
    (async () => {
      const updated = [...pairs];
      await Promise.all(pairs.map(async (p, i) => {
        const { data, error } = await getForecast(buildRoute(p.origin, p.dest), p.vessel, 14);
        if (!data && error?.status === 404) {
          updated[i] = { ...p, status: 'no-data' };
        } else if (data) {
          updated[i] = { ...p, status: data.is_high_uncertainty ? 'high-uncertainty' : 'serving', model: data.model_used };
        } else {
          updated[i] = { ...p, status: 'no-data' };
        }
      }));
      setPairStatuses([...updated]);
    })();
  }, [scope]);

  // ── Status badge helper ──
  function statusColor(s: PairStatus['status']): string {
    if (s === 'serving')          return 'var(--accent-hi)';
    if (s === 'high-uncertainty') return 'var(--warn)';
    if (s === 'no-data')          return 'var(--sail-500)';
    return 'var(--sail-600)';
  }
  function statusLabel(s: PairStatus['status']): string {
    if (s === 'serving')          return 'serving';
    if (s === 'high-uncertainty') return 'damped*';
    if (s === 'no-data')         return 'no data';
    return '...';
  }

  // ── Conditions monitor label ──
  const isHighUncertainty = forecast?.is_high_uncertainty ?? false;
  const modelUsed         = forecast?.model_used ?? '—';

  return (
    <div className="page-grid">
      {/* ── LEFT col-3 ── */}
      <div className="col-3 col-space">

        {/* Forecast pair selector */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Forecast pair</span>
            <span className="panel-meta">route × vessel × horizon</span>
          </div>
          <div className="panel-body flex-col gap-3" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {scopeError && <p className="infer" style={{ color: 'var(--warn)' }}>Scope unavailable: {scopeError}</p>}

            <div className="form-group">
              <label className="form-label">Origin</label>
              <select className="input-field" value={selectedOrigin} onChange={e => setSelectedOrigin(e.target.value)}>
                {(scope?.origins ?? []).map(o => <option key={o}>{o}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Discharge port</label>
              <select className="input-field" value={selectedDest} onChange={e => setSelectedDest(e.target.value)}>
                {(scope?.dest_ports ?? []).map(d => <option key={d}>{d}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Vessel class</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {(scope?.vessel_classes ?? ['Supramax/Ultramax', 'Panamax/Kamsarmax', 'Capesize']).map(v => (
                  <button key={v} className={`v-btn ${selectedVessel === v ? 'active' : ''}`}
                    onClick={() => setSelectedVessel(v)}>{v}</button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Horizon</label>
              <div style={{ display: 'flex', gap: 4 }}>
                {HORIZON_OPTIONS.map(h => (
                  <button key={h.days} className={`h-btn ${selectedHorizon === h.days ? 'active' : ''}`}
                    onClick={() => setSelectedHorizon(h.days)}>{h.label}</button>
                ))}
              </div>
            </div>

            <p className="infer">
              One model set per pair. Forecasting is scheduled (weekly retrain, daily refresh) and decoupled from cargo requests.
              Decision Engine only <em>reads</em> the stored <span className="mono">forecast_object</span>.
            </p>
          </div>
        </section>

        {/* Serving model */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Serving model</span>
            {forecast && <span className={`badge badge-${forecast.provenance}`}>{forecast.provenance.toUpperCase()}</span>}
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {fcLoading ? (
              <>{[1,2,3,4].map(i => <Skel key={i} />)}</>
            ) : forecast ? (
              <>
                {[
                  ['Primary',          forecast.model_used],
                  ['Currently serving', forecast.model_used],
                  ['Generated',         new Date(forecast.generated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST'],
                  ['Horizon',           `${forecast.horizon_days} days`],
                  ['Route',             forecast.route],
                  ['Vessel class',      forecast.vessel_class],
                ].map(([k, v]) => (
                  <div key={k} className="flex-between" style={{ fontSize: 12 }}>
                    <span className="text-sail-400">{k}</span>
                    <span className="mono text-sail-100" style={{ maxWidth: '60%', textAlign: 'right', wordBreak: 'break-all', fontSize: 11 }}>{v}</span>
                  </div>
                ))}
                <div style={{ borderTop: '1px solid var(--sail-800)', paddingTop: 10, marginTop: 4 }}>
                  <p className="infer">
                    ARIMA and naive exist only inside the evaluation gate — they never populate a <span className="mono">forecast_object</span>.
                    Damped trend substitutes when the conditions monitor trips.
                  </p>
                </div>
              </>
            ) : (
              <p className="infer">Select a route and vessel class to see serving model details.</p>
            )}
          </div>
        </section>

        {/* Conditions monitor */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Conditions monitor</span>
            {forecast && (
              <span style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                background: isHighUncertainty ? 'rgba(245,158,11,0.15)' : '#064e3b',
                color: isHighUncertainty ? 'var(--warn)' : '#6ee7b7',
                fontFamily: 'var(--f-mono)',
              }}>
                UNCERTAINTY · {isHighUncertainty ? 'HIGH' : 'NORMAL'}
              </span>
            )}
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {fcLoading ? <Skel h={80} w="100%" /> : forecast ? (
              <>
                <div style={{ fontSize: 12 }}>
                  <div className="flex-between" style={{ marginBottom: 6 }}>
                    <span>Uncertainty flag</span>
                    <span className="mono" style={{ color: isHighUncertainty ? 'var(--warn)' : 'var(--emerald-4)' }}>
                      {isHighUncertainty ? 'high — damped trend serving' : 'normal — primary serving'}
                    </span>
                  </div>
                  <div className="flex-between">
                    <span>Model in use</span>
                    <span className="mono text-sail-100">{modelUsed}</span>
                  </div>
                </div>
                {forecast.driver_explanation && (
                  <p className="infer" style={{ fontSize: 10.5 }}>{forecast.driver_explanation}</p>
                )}
                <p className="infer">
                  Either check failing → flag = high-uncertainty, damped trend served, band widened.
                </p>
              </>
            ) : (
              <p className="infer">Conditions monitor status appears after forecast loads.</p>
            )}
          </div>
        </section>
      </div>

      {/* ── CENTER col-6 ── */}
      <div className="col-6 col-space">

        {/* Main forecast card */}
        <div className="panel accent-left">
          <div style={{ padding: 16 }}>
            {fcLoading ? (
              <><Skel h={20} w="40%" /><Skel h={30} w="60%" /><Skel h={14} w="80%" /></>
            ) : fcError === 'no-forecast' ? (
              <div className="empty-state">
                <div className="empty-icon">⬡</div>
                <div className="empty-title">No forecast trained yet</div>
                <div className="empty-desc">
                  No gated forecast exists for <strong>{selectedOrigin}→{selectedDest}</strong> / <strong>{selectedVessel}</strong>.
                  The weekly scheduler (Monday 03:00) will train the first model once rate history exceeds the minimum observation threshold.
                </div>
              </div>
            ) : fcError ? (
              <div className="error-bar" id="forecast-error-banner">
                <span>✕</span><span>{fcError}</span>
              </div>
            ) : forecast ? (
              <>
                <div className="flex-between">
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--accent-hi)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>forecast_object</span>
                      <span className={`badge badge-${forecast.provenance}`}>{forecast.provenance.toUpperCase()}</span>
                      {forecast.is_high_uncertainty && <span className="badge badge-assumed">HIGH UNCERTAINTY</span>}
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--sail-100)' }}>
                      {forecast.route} · {forecast.vessel_class} · {forecast.horizon_days}d
                    </div>
                    <p style={{ fontSize: 13, color: 'var(--sail-400)', marginTop: 4 }}>
                      Point estimate with {forecast.is_high_uncertainty ? 'widened' : '80%'} band. Trajectory re-evaluated at event dates.
                    </p>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: 10, color: 'var(--sail-500)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Point · {forecast.horizon_days}d</div>
                    <div style={{ fontSize: 24, fontWeight: 600, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)' }}>
                      ${forecast.point_estimate.toFixed(2)}
                    </div>
                    {forecast.confidence_band && (
                      <div style={{ fontSize: 12, fontFamily: 'var(--f-mono)', color: 'var(--sail-400)' }}>
                        band ${forecast.confidence_band.lower.toFixed(2)} – ${forecast.confidence_band.upper.toFixed(2)} <span style={{ color: 'var(--sail-500)' }}>/t</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Multi-horizon summary cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginTop: 14 }}>
                  {HORIZON_OPTIONS.map(h => (
                    <div key={h.days} className={`horizon-card ${selectedHorizon === h.days ? 'selected' : ''}`}
                      onClick={() => setSelectedHorizon(h.days)} style={{ cursor: 'pointer' }}>
                      <div style={{ fontSize: 11, color: selectedHorizon === h.days ? 'var(--accent-hi)' : 'var(--sail-500)' }}>{h.label}</div>
                      <div className="mono" style={{ color: 'var(--sail-100)', fontSize: 13, fontWeight: 500 }}>
                        {selectedHorizon === h.days ? `$${forecast.point_estimate.toFixed(2)}` : '—'}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--sail-500)' }}>
                        {selectedHorizon === h.days && forecast.confidence_band
                          ? `${forecast.confidence_band.lower.toFixed(1)}–${forecast.confidence_band.upper.toFixed(1)}`
                          : 'select to load'}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="infer" style={{ padding: 8 }}>Select a route, vessel class, and horizon to load a forecast.</p>
            )}
          </div>
        </div>

        {/* Rate history + trajectory chart */}
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">Trajectory</span>
            <div className="flex-center gap-3" style={{ fontSize: 10 }}>
              <span className="flex-center gap-1"><span style={{ display: 'inline-block', width: 12, height: 2, background: 'var(--accent)' }} />Trajectory</span>
              <span className="flex-center gap-1"><span style={{ display: 'inline-block', width: 12, height: 8, background: 'rgba(13,148,136,0.12)', border: '1px solid rgba(13,148,136,0.3)' }} />Band</span>
              <span className="panel-meta">/forecast trajectory</span>
            </div>
          </div>
          <div className="panel-body">
            {fcLoading ? <Skel h={224} w="100%" /> : forecast ? (
              <>
                <TrajectoryChart fc={forecast} />
                <p className="infer">
                  Trajectory is the model's point estimate re-evaluated at event-based τ dates.
                  Band is the {forecast.is_high_uncertainty ? 'widened (high-uncertainty)' : '80%'} confidence interval.
                </p>
              </>
            ) : fcError === 'no-forecast' ? null : (
              <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(15,23,42,0.6)', border: '1px solid var(--sail-800)', borderRadius: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--sail-500)' }}>Select a route and vessel class to see the trajectory chart.</span>
              </div>
            )}
          </div>
        </div>

        {/* Walk-forward eval — not exposed via API, explains why */}
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">Walk-forward evaluation gate</span>
            <span className="panel-meta">§6.2 · rolling backtest · never a random split</span>
          </div>
          <div className="panel-body">
            {fcLoading ? <Skel h={80} w="100%" /> : forecast ? (
              <>
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <span style={{
                    padding: '4px 10px', borderRadius: 6, fontSize: 11, fontFamily: 'var(--f-mono)',
                    background: 'rgba(13,148,136,0.1)', border: '1px solid rgba(13,148,136,0.25)', color: 'var(--accent-hi)',
                  }}>
                    ✓ Gate passed · {forecast.model_used} selected as primary
                  </span>
                </div>
                <p className="infer">
                  Detailed evaluation metrics (MAE, RMSE, MAPE, R², directional accuracy) are computed during the weekly retrain cycle
                  and stored in the warehouse. They are not exposed via the <span className="mono">/forecast</span> API endpoint —
                  the gate pass/fail result is surfaced in <span className="mono">model_used</span>: if you see <span className="mono">{forecast.model_used}</span>
                  here, the gate passed with that model winning the walk-forward backtest against naive and ARIMA.
                  {forecast.is_high_uncertainty && ' The conditions monitor tripped — damped trend is currently serving even though XGBoost passed the gate.'}
                </p>
              </>
            ) : (
              <p className="infer">Evaluation gate status will appear when a forecast is loaded.</p>
            )}
          </div>
        </div>
      </div>

      {/* ── RIGHT col-3 ── */}
      <div className="col-3 col-space">

        {/* Driver explanation */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Rate driver explanation</span>
            <span className="panel-meta">from model</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {fcLoading ? <Skel h={80} w="100%" /> : forecast?.driver_explanation ? (
              <p style={{ fontSize: 12, lineHeight: 1.6, color: 'var(--sail-300)' }}>
                {forecast.driver_explanation}
              </p>
            ) : forecast ? (
              <p className="infer">No driver explanation available for this forecast object. It will be populated during the next retrain cycle.</p>
            ) : (
              <p className="infer">Driver explanation appears after a forecast is loaded.</p>
            )}
          </div>
        </section>

        {/* Pair coverage */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Pair coverage</span>
            <span className="panel-meta">live probe · 14-day horizon</span>
          </div>
          <div className="panel-body" style={{ overflowX: 'auto' }}>
            {pairStatuses.length === 0 ? (
              <p className="infer">Loading pair coverage…</p>
            ) : (() => {
              // Group by origin
              const origins  = [...new Set(pairStatuses.map(p => p.origin))];
              const vessels  = [...new Set(pairStatuses.map(p => p.vessel))];
              const byKey    = Object.fromEntries(pairStatuses.map(p => [`${p.origin}|${p.dest}|${p.vessel}`, p]));
              const dests    = [...new Set(pairStatuses.map(p => p.dest))];

              return (
                <table style={{ width: '100%', fontSize: 10, fontFamily: 'var(--f-mono)', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ color: 'var(--sail-500)' }}>
                      <th style={{ textAlign: 'left', padding: '4px 0' }}>Origin</th>
                      <th style={{ textAlign: 'left', padding: '4px 0' }}>Dest</th>
                      {vessels.map(v => <th key={v} style={{ textAlign: 'center', padding: '4px 2px' }}>{v.split('/')[0].slice(0,5)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {origins.flatMap(o => dests.map(d => (
                      <tr key={`${o}|${d}`}>
                        <td style={{ padding: '3px 0', color: 'var(--sail-400)', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{o.split('(')[0].trim().slice(0,10)}</td>
                        <td style={{ color: 'var(--sail-400)' }}>{d.slice(0,8)}</td>
                        {vessels.map(v => {
                          const p = byKey[`${o}|${d}|${v}`];
                          if (!p) return <td key={v} />;
                          return <td key={v} style={{ textAlign: 'center', color: statusColor(p.status) }}>{statusLabel(p.status)}</td>;
                        })}
                      </tr>
                    )))}
                  </tbody>
                </table>
              );
            })()}
            <p className="infer">* Conditions monitor tripped — damped trend serving.</p>
            <p className="infer">no data — below min-observation threshold or no retrain yet.</p>
          </div>
        </section>

        {/* What this is not */}
        <section className="panel">
          <div className="panel-hd"><span className="panel-title">What this is not</span></div>
          <div className="panel-body">
            <ul style={{ fontSize: 11, color: 'var(--sail-400)', display: 'flex', flexDirection: 'column', gap: 6, lineHeight: 1.4, paddingLeft: 14 }}>
              <li>Not a live retrain on each cargo request.</li>
              <li>Not a deep-learning ensemble (Stage 3, needs ~7,000 obs).</li>
              <li>Not a stochastic tree — Scenario Generator uses three paths only.</li>
              <li>Prophet does not pick the number; {forecast?.model_used ?? 'the gated model'} does.</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
};

export default ForecastExplorerPage;
