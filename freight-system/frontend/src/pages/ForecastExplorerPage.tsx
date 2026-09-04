import React, { useCallback, useEffect, useState } from 'react';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  Area,
  AreaChart,
  BarChart,
  Bar,
  ReferenceLine,
  Cell,
} from 'recharts';
import { getForecast, getScope, postNarrate } from '../lib/apiClient';
import type { ForecastResponse, ScopeResponse, ParsedDriverExplanation } from '../lib/types';
import { getCachedScope, setCachedScope } from '../lib/defaults';

// ── Horizon options matching backend FORECAST_HORIZONS_DAYS = [7, 14, 30] ──
const HORIZON_OPTIONS = [
  { label: '1-week',  days: 7  },
  { label: '2-week',  days: 14 },
  { label: '1-month', days: 30 },
];

function buildRoute(origin: string, dest: string): string {
  return `${origin}→${dest}`;
}

function formatNum(v: any, d = 2) {
  if (v === null || v === undefined || isNaN(Number(v))) return (0).toFixed(d);
  return Number(v).toFixed(d);
}

function Skel({ h = 16, w = '80%' }: { h?: number; w?: string }) {
  return <div className="skel" style={{ height: h, width: w, marginBottom: 6 }} />;
}

// ── Interactive Recharts Trajectory Chart ──────────────────────────────────────
function InteractiveTrajectory({ fc }: { fc: ForecastResponse }) {
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const traj = fc.trajectory ?? [];

  if (traj.length === 0) {
    return (
      <div style={{
        height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'color-mix(in srgb, var(--sail-900) 60%, transparent)', border: '1px solid var(--sail-800)', borderRadius: 4,
      }}>
        <span style={{ fontSize: 12, color: 'var(--sail-500)' }}>No trajectory data in this forecast object</span>
      </div>
    );
  }

  // Format data for Recharts
  const data = traj.map((p: any) => {
    const val = p.point_estimate ?? p.value ?? 0;
    const dateStr = p.day !== undefined 
      ? `Day ${p.day}` 
      : (p.date ? new Date(p.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : 'Unknown');
      
    return {
      date: dateStr,
      rawDate: p.date ?? p.day,
      value: Number(formatNum(val, 2)),
      band: [
        fc.confidence_band?.lower !== undefined ? Number(formatNum(fc.confidence_band.lower, 2)) : Number(formatNum(val, 2)),
        fc.confidence_band?.upper !== undefined ? Number(formatNum(fc.confidence_band.upper, 2)) : Number(formatNum(val, 2)),
      ]
    };
  });

  const minVal = data.length > 0 ? Math.min(...data.map(d => d.band[0])) * 0.95 : 0;
  const maxVal = data.length > 0 ? Math.max(...data.map(d => d.band[1])) * 1.05 : 100;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '8px' }}>
        <div style={{ display: 'flex', background: 'var(--sail-900)', borderRadius: '6px', border: '1px solid var(--sail-800)', overflow: 'hidden' }}>
          <button
            onClick={() => setView('chart')}
            style={{ padding: '4px 12px', fontSize: '11px', background: view === 'chart' ? 'var(--sail-700)' : 'transparent', color: view === 'chart' ? 'var(--sail-100)' : 'var(--sail-400)', border: 'none', cursor: 'pointer' }}
          >
            Chart View
          </button>
          <button
            onClick={() => setView('table')}
            style={{ padding: '4px 12px', fontSize: '11px', background: view === 'table' ? 'var(--sail-700)' : 'transparent', color: view === 'table' ? 'var(--sail-100)' : 'var(--sail-400)', border: 'none', cursor: 'pointer' }}
          >
            Table View
          </button>
        </div>
      </div>

      {view === 'chart' ? (
        <div style={{ height: 260, background: 'color-mix(in srgb, var(--sail-900) 60%, transparent)', border: '1px solid var(--sail-800)', borderRadius: 4, padding: '16px 16px 0 0' }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--sail-800)" vertical={false} />
              <XAxis dataKey="date" stroke="var(--sail-500)" fontSize={11} tickMargin={8} minTickGap={20} />
              <YAxis domain={[minVal, maxVal]} stroke="var(--sail-500)" fontSize={11} tickFormatter={(v) => `$${formatNum(v, 0)}`} width={50} />
              <Tooltip
                contentStyle={{ background: 'var(--sail-900)', border: '1px solid var(--sail-700)', borderRadius: '8px', fontSize: '12px' }}
                itemStyle={{ color: 'var(--sail-100)' }}
                labelStyle={{ color: '#94a3b8', marginBottom: '4px' }}
                formatter={(value: any, name: any) => {
                  if (name === 'band') {
                    if (Array.isArray(value) && value.length === 2) {
                      return [`$${value[0]} - $${value[1]}`, 'Confidence Band'];
                    }
                    return ['...', 'Confidence Band'];
                  }
                  return [`$${value}`, 'Expected Rate'];
                }}
              />
              <Area type="monotone" dataKey="band" fill="#1A1A1A" stroke="none" fillOpacity={0.05} />
              <Line type="monotone" dataKey="value" stroke="#1A1A1A" strokeWidth={2} dot={{ r: 3, fill: '#1A1A1A' }} activeDot={{ r: 5 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div style={{ height: 260, overflowY: 'auto', background: 'color-mix(in srgb, var(--sail-900) 60%, transparent)', border: '1px solid var(--sail-800)', borderRadius: 4 }}>
          <table style={{ width: '100%', fontSize: '12px', textAlign: 'right', borderCollapse: 'collapse' }}>
            <thead style={{ position: 'sticky', top: 0, background: 'var(--sail-900)' }}>
              <tr>
                <th style={{ padding: '8px 16px', textAlign: 'left', borderBottom: '1px solid var(--sail-800)' }}>Date</th>
                <th style={{ padding: '8px 16px', borderBottom: '1px solid var(--sail-800)' }}>Lower Band</th>
                <th style={{ padding: '8px 16px', borderBottom: '1px solid var(--sail-800)' }}>Expected Rate</th>
                <th style={{ padding: '8px 16px', borderBottom: '1px solid var(--sail-800)' }}>Upper Band</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid color-mix(in srgb, var(--sail-700) 30%, transparent)' }}>
                  <td style={{ padding: '8px 16px', textAlign: 'left', color: 'var(--sail-300)' }}>{row.date}</td>
                  <td style={{ padding: '8px 16px', color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>${formatNum(row.band[0], 2)}</td>
                  <td style={{ padding: '8px 16px', color: 'var(--text-accent)', fontFamily: 'var(--f-mono)', fontWeight: 600 }}>${formatNum(row.value, 2)}</td>
                  <td style={{ padding: '8px 16px', color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>${formatNum(row.band[1], 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

interface PairStatus {
  origin: string;
  dest:   string;
  vessel: string;
  status: 'checking' | 'serving' | 'high-uncertainty' | 'no-data';
  model?: string;
}

const ForecastExplorerPage: React.FC = () => {
  const initialScope = getCachedScope();
  const [scope, setScope] = useState<ScopeResponse>(initialScope);
  const [scopeError] = useState<string | null>(null);

  const [selectedOrigin,  setSelectedOrigin]  = useState<string>(initialScope.origins[0] || 'Australia (Hay Point)');
  const [selectedDest,    setSelectedDest]    = useState<string>(initialScope.dest_ports[0] || 'Paradip');
  const [selectedVessel,  setSelectedVessel]  = useState<string>(initialScope.vessel_classes[0] || 'Capesize');
  const [selectedHorizon, setSelectedHorizon] = useState<number>(14);

  const [forecast,  setForecast]  = useState<ForecastResponse | null>(null);
  const [fcLoading, setFcLoading] = useState(false);
  const [fcError,   setFcError]   = useState<string | null>(null);

  const [pairStatuses, setPairStatuses] = useState<PairStatus[]>([]);
  // AI-generated narrative — fetched live on forecast load (NVIDIA NIM with Groq fallback)
  const [groqNarrative, setGroqNarrative] = useState<string | null>(null);
  const [narrativeSource, setNarrativeSource] = useState<'nvidia' | 'groq' | 'template' | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      const { data, error } = await getScope();
      if (!active) return;
      if (error || !data) {
        return;
      }
      setScope(data);
      setCachedScope(data);
      if (data.origins.length)        setSelectedOrigin((curr: string) => data.origins.includes(curr) ? curr : data.origins[0]);
      if (data.dest_ports.length)     setSelectedDest((curr: string) => data.dest_ports.includes(curr) ? curr : data.dest_ports[0]);
      if (data.vessel_classes.length) setSelectedVessel((curr: string) => data.vessel_classes.includes(curr) ? curr : data.vessel_classes[0]);
    })();
    return () => { active = false; };
  }, []);

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
        setFcError('no-forecast');
      } else {
        setFcError(error.message);
      }
    } else {
      setForecast(data);
    }
  }, [selectedOrigin, selectedDest, selectedVessel, selectedHorizon]);

  useEffect(() => { if (scope) fetchForecast(); }, [scope, selectedOrigin, selectedDest, selectedVessel, selectedHorizon, fetchForecast]);

  const [driverSubTab, setDriverSubTab] = useState<'macro' | 'importances' | 'seasonality'>('macro');

  // Auto-fetch narrative whenever a forecast with prophet decomposition loads
  useEffect(() => {
    setGroqNarrative(null);
    setNarrativeSource(null);
    if (forecast) {
      try {
        const expl = forecast.driver_explanation ? JSON.parse(forecast.driver_explanation) : null;
        if (expl && expl.prophet_decomposition) {
          const pd = expl.prophet_decomposition;
          setNarrativeLoading(true);
          postNarrate({
            horizon_days: forecast.horizon_days,
            trend_delta: pd.trend_delta,
            trend_direction: pd.trend_direction as 'rising' | 'falling' | 'flat',
            weekly_seasonality_amplitude: pd.weekly_seasonality_amplitude,
            regressor_effects: pd.regressor_effects,
            available_regressors: Object.keys(pd.regressor_effects),
          }).then(({ data, error }) => {
            setNarrativeLoading(false);
            if (!error && data) {
              setGroqNarrative(data.narrative);
              setNarrativeSource(data.source);
            }
          }).catch(() => setNarrativeLoading(false));
        }
      } catch {
        setNarrativeLoading(false);
      }
    }
  }, [forecast]);

  // Probe pair coverage to build the availability map
  useEffect(() => {
    if (!scope) return;
    const pairs: PairStatus[] = [];
    
    // Check ALL scope combinations to enable smart dropdowns
    for (const o of scope.origins) {
      for (const d of scope.dest_ports) {
        for (const v of scope.vessel_classes) {
          pairs.push({ origin: o, dest: d, vessel: v, status: 'checking' });
        }
      }
    }
    setPairStatuses(pairs);

    // Fire off probes in chunks to prevent browser connection exhaustion
    (async () => {
      const updated = [...pairs];
      const CHUNK_SIZE = 5;
      for (let i = 0; i < pairs.length; i += CHUNK_SIZE) {
        const chunk = pairs.slice(i, i + CHUNK_SIZE);
        await Promise.all(chunk.map(async (p, j) => {
          const idx = i + j;
          try {
            const { data, error } = await getForecast(buildRoute(p.origin, p.dest), p.vessel, 14);
            if (!data && error?.status === 404) {
              updated[idx] = { ...p, status: 'no-data' };
            } else if (data) {
              updated[idx] = { ...p, status: data.is_high_uncertainty ? 'high-uncertainty' : 'serving', model: data.model_used };
            } else {
              updated[idx] = { ...p, status: 'no-data' };
            }
          } catch (e) {
            updated[idx] = { ...p, status: 'no-data' };
          }
        }));
        // Update UI incrementally
        setPairStatuses([...updated]);
      }
    })();
  }, [scope]);

  // ── Smart Dropdown Helpers ──
  // Check if a specific origin/dest/vessel has data in the pairStatuses table
  const hasData = (o: string, d: string, v: string) => {
    if (pairStatuses.length === 0) return true;
    const pair = pairStatuses.find(p => p.origin === o && p.dest === d && p.vessel === v);
    if (!pair) return true;
    return pair.status !== 'no-data'; // allow 'checking', 'serving', 'high-uncertainty'
  };

  // Get available destinations for a given origin (must have at least one vessel class with data)
  const availableDestsForOrigin = (o: string) => {
    if (pairStatuses.length === 0) return scope?.dest_ports ?? [];
    return (scope?.dest_ports ?? []).filter(d => 
      (scope?.vessel_classes ?? []).some(v => hasData(o, d, v))
    );
  };

  // Get available vessels for a given origin and dest
  const availableVesselsForRoute = (o: string, d: string) => {
    if (pairStatuses.length === 0) return scope?.vessel_classes ?? [];
    return (scope?.vessel_classes ?? []).filter(v => hasData(o, d, v));
  };

  const currentAvailableDests = availableDestsForOrigin(selectedOrigin);
  const currentAvailableVessels = availableVesselsForRoute(selectedOrigin, selectedDest);

  // Auto-correct selections if they become invalid
  useEffect(() => {
    if (pairStatuses.length > 0 && currentAvailableDests.length > 0 && !currentAvailableDests.includes(selectedDest)) {
      setSelectedDest(currentAvailableDests[0]);
    }
  }, [selectedOrigin, currentAvailableDests, selectedDest, pairStatuses]);

  useEffect(() => {
    if (pairStatuses.length > 0 && currentAvailableVessels.length > 0 && !currentAvailableVessels.includes(selectedVessel)) {
      setSelectedVessel(currentAvailableVessels[0]);
    }
  }, [selectedOrigin, selectedDest, currentAvailableVessels, selectedVessel, pairStatuses]);

  const isHighUncertainty = forecast?.is_high_uncertainty ?? false;
  const modelUsed = forecast?.model_used || '—';

  let parsedExplanation: ParsedDriverExplanation | null = null;
  if (forecast?.driver_explanation) {
    try {
      const attempt = JSON.parse(forecast.driver_explanation);
      // If it parsed but isn't an object with a text field, treat as plain text
      if (attempt && typeof attempt === 'object' && 'text' in attempt) {
        parsedExplanation = attempt as ParsedDriverExplanation;
      } else if (typeof attempt === 'string') {
        parsedExplanation = { text: attempt, importances: {} };
      }
    } catch (e) {
      // Old plain-string format — wrap it so the UI renders immediately
      parsedExplanation = { text: forecast.driver_explanation, importances: {} };
    }
  }
  const prophetDecomp = parsedExplanation?.prophet_decomposition ?? null;
  const hasImportances = Object.keys(parsedExplanation?.importances ?? {}).length > 0;
  const hasProphet = prophetDecomp !== null;


  return (
    <div className="page-grid">
      {/* ── LEFT col-3 ── */}
      <div className="col-3 col-space">
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Forecast Configuration</span>
          </div>
          <div className="panel-body flex-col gap-3" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {scopeError && <p className="infer" style={{ color: 'var(--warn)' }}>Scope unavailable: {scopeError}</p>}

            <div className="form-group">
              <label className="form-label">Origin</label>
              <select className="input-field" value={selectedOrigin} onChange={e => setSelectedOrigin(e.target.value)}>
                {(scope?.origins ?? []).map(o => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Discharge port</label>
              <select className="input-field" value={selectedDest} onChange={e => setSelectedDest(e.target.value)}>
                {currentAvailableDests.length > 0 
                  ? currentAvailableDests.map(d => <option key={d} value={d}>{d}</option>)
                  : <option disabled>No valid routes available</option>}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Vessel class</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {(scope?.vessel_classes ?? ['Supramax/Ultramax', 'Panamax/Kamsarmax', 'Capesize']).map(v => {
                  const isValid = currentAvailableVessels.includes(v) || pairStatuses.length === 0;
                  return (
                    <button 
                      key={v} 
                      className={`v-btn ${selectedVessel === v ? 'active' : ''}`}
                      disabled={!isValid}
                      style={{ opacity: isValid ? 1 : 0.3, cursor: isValid ? 'pointer' : 'not-allowed' }}
                      onClick={() => setSelectedVessel(v)}>
                      {v}
                    </button>
                  );
                })}
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
              Only routes and vessels with sufficient historical observation data are available for selection.
            </p>
          </div>
        </section>

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
                  ['Currently serving', forecast.model_used],
                  ['Generated',         new Date(forecast.generated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST'],
                  ['Horizon',           `${forecast.horizon_days} days`],
                ].map(([k, v]) => (
                  <div key={k} className="flex-between" style={{ fontSize: 12 }}>
                    <span className="text-sail-400">{k}</span>
                    <span className="mono text-sail-100" style={{ maxWidth: '60%', textAlign: 'right', wordBreak: 'break-all', fontSize: 11 }}>{v}</span>
                  </div>
                ))}
              </>
            ) : (
              <p className="infer">Select a configuration to see serving model details.</p>
            )}
          </div>
        </section>

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
                      {modelUsed === 'damped_trend'
                        ? 'high — damped trend fallback'
                        : isHighUncertainty
                        ? 'elevated volatility — wide band'
                        : 'normal — gated primary serving'}
                    </span>
                  </div>
                  <div className="flex-between">
                    <span>Model in use</span>
                    <span className="mono text-sail-100">{modelUsed}</span>
                  </div>
                </div>
                {forecast.driver_explanation && (
                  <p className="infer" style={{ fontSize: 10.5 }}>{parsedExplanation?.text || forecast.driver_explanation}</p>
                )}
              </>
            ) : (
              <p className="infer">Conditions monitor status appears after forecast loads.</p>
            )}
          </div>
        </section>
      </div>

      {/* ── CENTER col-6 ── */}
      <div className="col-6 col-space">
        <div className="panel panel-ink">
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
                      <span className={`badge badge-${forecast.provenance}`}>{forecast.provenance.toUpperCase()}</span>
                      {modelUsed === 'damped_trend' ? (
                        <span className="badge badge-assumed">DAMPED TREND FALLBACK</span>
                      ) : isHighUncertainty ? (
                        <span className="badge badge-warn">WIDE VOLATILITY</span>
                      ) : (
                        <span className="badge badge-emerald" style={{ fontSize: '10px' }}>GATED · {modelUsed.toUpperCase()}</span>
                      )}
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--ink-text)' }}>
                      {forecast.route} · {forecast.vessel_class} · {forecast.horizon_days}d
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: 10, color: 'var(--sail-500)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Point · {forecast.horizon_days}d</div>
                    <div style={{ fontSize: 24, fontWeight: 600, color: 'var(--ink-text)', fontFamily: 'var(--f-mono)' }}>
                      ${formatNum(forecast.point_estimate, 2)}
                    </div>
                    {forecast.confidence_band && forecast.confidence_band.lower !== undefined && forecast.confidence_band.upper !== undefined && (
                      <div style={{ fontSize: 12, fontFamily: 'var(--f-mono)', color: 'var(--sail-400)' }}>
                        band ${formatNum(forecast.confidence_band.lower, 2)} – ${formatNum(forecast.confidence_band.upper, 2)} <span style={{ color: 'var(--sail-500)' }}>/t</span>
                      </div>
                    )}
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginTop: 14 }}>
                  {HORIZON_OPTIONS.map(h => (
                    <div key={h.days} className={`horizon-card ${selectedHorizon === h.days ? 'selected' : ''}`}
                      onClick={() => setSelectedHorizon(h.days)} style={{ cursor: 'pointer' }}>
                      <div style={{ fontSize: 11, color: selectedHorizon === h.days ? '#1A1A1A' : 'var(--sail-500)' }}>{h.label}</div>
                      <div className="mono" style={{ color: selectedHorizon === h.days ? '#1A1A1A' : 'var(--ink-text)', fontSize: 13, fontWeight: 500 }}>
                        {selectedHorizon === h.days ? `$${formatNum(forecast.point_estimate, 2)}` : ''}
                      </div>
                      <div style={{ fontSize: 10, color: selectedHorizon === h.days ? 'rgba(26,26,26,0.7)' : 'var(--sail-500)' }}>
                        {selectedHorizon === h.days && forecast.confidence_band && forecast.confidence_band.lower !== undefined && forecast.confidence_band.upper !== undefined
                          ? `${formatNum(forecast.confidence_band.lower, 1)}–${formatNum(forecast.confidence_band.upper, 1)}`
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

        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">Forecast Trajectory</span>
          </div>
          <div className="panel-body">
            {fcLoading ? <Skel h={224} w="100%" /> : forecast ? (
              <InteractiveTrajectory fc={forecast} />
            ) : fcError === 'no-forecast' ? null : (
              <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'color-mix(in srgb, var(--sail-900) 60%, transparent)', border: '1px solid var(--sail-800)', borderRadius: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--sail-500)' }}>Select a valid configuration to view trajectory.</span>
              </div>
            )}
          </div>
        </div>

        {/* ── EXPANDED: Economic Drivers & Voyage Profit Impact Engine (Center col-6) ── */}
        <section className="panel" id="forecast-profit-explanation-deck">
          <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
            <div>
              <span className="panel-title">Economic Drivers & Voyage Profit Impact</span>
              <span className="panel-meta" style={{ marginLeft: 8 }}>
                Decomposing $/day rate momentum into Time Charter Equivalent (TCE) and voyage margins
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {hasProphet && (
                <span className="badge badge-emerald" style={{ fontSize: 10, fontFamily: 'var(--f-mono)' }}>
                  PROPHET DECOMPOSITION
                </span>
              )}
              {hasImportances && (
                <span className="badge" style={{ fontSize: 10, fontFamily: 'var(--f-mono)', background: 'var(--sail-800)', color: 'var(--sail-300)', border: '1px solid var(--sail-700)' }}>
                  XGBOOST GATED
                </span>
              )}
            </div>
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {fcLoading ? (
              <Skel h={160} w="100%" />
            ) : forecast && parsedExplanation ? (() => {
              // Mathematical profit & TCE calculations based on vessel deadweight
              let vesselCapacity = 75000;
              const lowerClass = selectedVessel.toLowerCase();
              if (lowerClass.includes('cape')) vesselCapacity = 180000;
              else if (lowerClass.includes('supra') || lowerClass.includes('ultra')) vesselCapacity = 58000;
              else if (lowerClass.includes('pana') || lowerClass.includes('kamsar')) vesselCapacity = 75000;

              const typicalVoyageDays = 20;
              const trendDelta = prophetDecomp?.trend_delta ?? 4;
              const trendDirection = prophetDecomp?.trend_direction ?? (trendDelta > 0 ? 'rising' : trendDelta < 0 ? 'falling' : 'flat');
              const totalVoyageMarginDelta = vesselCapacity * Math.abs(trendDelta);
              const dailyTceDelta = Math.round(totalVoyageMarginDelta / typicalVoyageDays);
              const grossVoyageFreight = Math.round(vesselCapacity * forecast.point_estimate);

              return (
                <>
                  {/* ── 1. Top Payoff Ribbon: 3 High-Impact Financial Metrics ── */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                    {/* Metric 1: Rate Momentum */}
                    <div className="feas-card" style={{ padding: '10px 14px' }}>
                      <div className="feas-card-head">
                        <span style={{ fontSize: 11, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                          Rate Momentum
                        </span>
                        <span style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: '2px 6px',
                          borderRadius: 3,
                          background: trendDirection === 'rising' ? 'rgba(239, 68, 68, 0.15)' : trendDirection === 'falling' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                          color: trendDirection === 'rising' ? '#ef4444' : trendDirection === 'falling' ? '#22c55e' : '#f59e0b',
                        }}>
                          {trendDirection === 'rising' ? '▲ Upward Pressure' : trendDirection === 'falling' ? '▼ Softening' : '→ Rangebound'}
                        </span>
                      </div>
                      <div style={{
                        fontSize: 22,
                        fontWeight: 700,
                        fontFamily: 'var(--f-mono)',
                        marginTop: 4,
                        color: trendDirection === 'rising' ? '#ef4444' : trendDirection === 'falling' ? '#22c55e' : 'var(--sail-100)',
                      }}>
                        {trendDelta >= 0 ? '+' : ''}${trendDelta.toFixed(2)}
                        <span style={{ fontSize: 12, color: 'var(--sail-500)', fontWeight: 400 }}> /t</span>
                      </div>
                      <div className="feas-card-sub" style={{ marginTop: 4 }}>
                        Over {forecast.horizon_days}-day horizon window
                      </div>
                    </div>

                    {/* Metric 2: Daily Time Charter Equivalent (TCE) Shift */}
                    <div className="feas-card" style={{ padding: '10px 14px' }}>
                      <div className="feas-card-head">
                        <span style={{ fontSize: 11, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                          Daily TCE Margin Impact
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-accent)', fontFamily: 'var(--f-mono)' }}>
                          {selectedVessel.split('/')[0]} basis
                        </span>
                      </div>
                      <div style={{
                        fontSize: 22,
                        fontWeight: 700,
                        fontFamily: 'var(--f-mono)',
                        marginTop: 4,
                        color: 'var(--text-accent)',
                      }}>
                        {trendDelta >= 0 ? '+' : '-'}${dailyTceDelta.toLocaleString()}
                        <span style={{ fontSize: 12, color: 'var(--sail-500)', fontWeight: 400 }}> /day</span>
                      </div>
                      <div className="feas-card-sub" style={{ marginTop: 4 }}>
                        Net shipowner daily hire earnings shift
                      </div>
                    </div>

                    {/* Metric 3: Total Voyage Gross Margin */}
                    <div className="feas-card" style={{ padding: '10px 14px' }}>
                      <div className="feas-card-head">
                        <span style={{ fontSize: 11, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                          Voyage Gross Margin Delta
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--sail-500)' }}>
                          {(vesselCapacity / 1000).toFixed(0)}k MT fixture
                        </span>
                      </div>
                      <div style={{
                        fontSize: 22,
                        fontWeight: 700,
                        fontFamily: 'var(--f-mono)',
                        marginTop: 4,
                        color: 'var(--sail-100)',
                      }}>
                        {trendDelta >= 0 ? '+' : '-'}${Math.round(totalVoyageMarginDelta).toLocaleString()}
                      </div>
                      <div className="feas-card-sub" style={{ marginTop: 4 }}>
                        Est. total gross freight: ${grossVoyageFreight.toLocaleString()}
                      </div>
                    </div>
                  </div>

                  {/* ── 1. Executive AI Strategy Briefing (NVIDIA NIM Live API) ── */}
                  <div style={{
                    padding: '12px 14px',
                    borderRadius: 'var(--r)',
                    background: 'color-mix(in srgb, var(--sail-800) 60%, transparent)',
                    border: '1px solid var(--sail-700)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{
                          fontSize: 9.5,
                          fontWeight: 700,
                          fontFamily: 'var(--f-mono)',
                          letterSpacing: '0.6px',
                          textTransform: 'uppercase',
                          padding: '2px 6px',
                          borderRadius: 3,
                          background: narrativeSource === 'nvidia' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                          color: narrativeSource === 'nvidia' ? '#22c55e' : 'var(--text-accent)',
                          border: narrativeSource === 'nvidia' ? '1px solid rgba(34, 197, 94, 0.3)' : '1px solid var(--accent-dim)',
                        }}>
                          {narrativeSource === 'nvidia' ? 'NVIDIA NIM · LIVE BRIEFING' : narrativeSource === 'groq' ? 'GROQ · LIVE BRIEFING' : 'EXECUTIVE STRATEGY BRIEFING'}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--sail-400)' }}>
                          Commercial Freight Translation
                        </span>
                      </div>
                      {narrativeLoading ? (
                        <span style={{ fontSize: 10, color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>
                          synthesizing live…
                        </span>
                      ) : (
                        <span style={{ fontSize: 10, color: 'var(--emerald)', fontFamily: 'var(--f-mono)' }}>
                          ● Instant Analysis
                        </span>
                      )}
                    </div>

                    <p style={{
                      margin: 0,
                      fontSize: 13,
                      lineHeight: 1.5,
                      color: 'var(--sail-100)',
                      opacity: narrativeLoading ? 0.6 : 1,
                      transition: 'opacity 0.2s',
                    }}>
                      {groqNarrative || prophetDecomp?.narrative || (
                        `A ${trendDelta >= 0 ? '+' : ''}$${trendDelta.toFixed(2)}/t freight momentum shift alters total single-voyage gross revenue by $${Math.round(totalVoyageMarginDelta).toLocaleString()} for a ${(vesselCapacity / 1000).toFixed(0)}k MT fixture. Recommendation: Lock forward coverage to protect against rising spot hire replacement costs.`
                      )}
                    </p>
                  </div>

                  {/* ── 2. Sub-Tab Navigation for Visual Charts ── */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--sail-800)', paddingBottom: 6 }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => setDriverSubTab('macro')}
                        style={{
                          padding: '4px 10px',
                          fontSize: 11,
                          borderRadius: 'var(--r)',
                          border: driverSubTab === 'macro' ? '1px solid var(--accent-dim)' : '1px solid var(--sail-700)',
                          background: driverSubTab === 'macro' ? 'var(--accent)' : 'var(--sail-800)',
                          color: driverSubTab === 'macro' ? 'var(--accent-text)' : 'var(--sail-300)',
                          cursor: 'pointer',
                          fontWeight: driverSubTab === 'macro' ? 600 : 400,
                        }}
                      >
                        Macro Driver Tornado Chart ({Object.keys(prophetDecomp?.regressor_effects ?? {}).length || 6})
                      </button>

                      <button
                        onClick={() => setDriverSubTab('seasonality')}
                        style={{
                          padding: '4px 10px',
                          fontSize: 11,
                          borderRadius: 'var(--r)',
                          border: driverSubTab === 'seasonality' ? '1px solid var(--accent-dim)' : '1px solid var(--sail-700)',
                          background: driverSubTab === 'seasonality' ? 'var(--accent)' : 'var(--sail-800)',
                          color: driverSubTab === 'seasonality' ? 'var(--accent-text)' : 'var(--sail-300)',
                          cursor: 'pointer',
                          fontWeight: driverSubTab === 'seasonality' ? 600 : 400,
                        }}
                      >
                        Weekly Trading Seasonality Wave (±${((prophetDecomp?.weekly_seasonality_amplitude ?? 4) / 2).toFixed(0)}/day)
                      </button>

                      {hasImportances && (
                        <button
                          onClick={() => setDriverSubTab('importances')}
                          style={{
                            padding: '4px 10px',
                            fontSize: 11,
                            borderRadius: 'var(--r)',
                            border: driverSubTab === 'importances' ? '1px solid var(--accent-dim)' : '1px solid var(--sail-700)',
                            background: driverSubTab === 'importances' ? 'var(--accent)' : 'var(--sail-800)',
                            color: driverSubTab === 'importances' ? 'var(--accent-text)' : 'var(--sail-300)',
                            cursor: 'pointer',
                            fontWeight: driverSubTab === 'importances' ? 600 : 400,
                          }}
                        >
                          XGBoost Feature Importances
                        </button>
                      )}
                    </div>
                  </div>

                  {/* ── 3. Sub-Tab Content: Diverging Macro Driver Tornado Chart ── */}
                  {driverSubTab === 'macro' && (() => {
                    const detailsMap: Record<string, { label: string; cat: string; why: string }> = {
                      bdry: { label: 'BDI Index', cat: 'Fleet Supply & Demand', why: 'Global bulk carrier spot availability & load port waiting queues.' },
                      brent: { label: 'Brent Crude', cat: 'Bunker Fuel Baseline', why: 'Global crude price benchmark dictating VLSFO marine bunker surcharges.' },
                      wti: { label: 'WTI Crude', cat: 'Energy Arbitrage', why: 'North American refinery runs and inter-basin trade arbitrage spreads.' },
                      bunker_mgo: { label: 'Marine Gas Oil', cat: 'Port Auxiliary Fuel', why: 'Distillate fuel for auxiliary generators and waiting-at-anchor disbursements.' },
                      bunker_vlsfo: { label: 'Bunker VLSFO', cat: 'Voyage Fuel Baseline', why: 'Primary laden steaming bunker fuel consumption costs.' },
                      gscpi: { label: 'Supply Chain', cat: 'Macro Pressure', why: 'Global logistics bottlenecks and key chokepoint transit delays.' },
                      iron_ore_62: { label: 'Iron Ore', cat: 'Seaborne Cargo Volume', why: 'Primary raw material volume driver for Capesize & Panamax laden voyages.' },
                      iron_ore: { label: 'Iron Ore', cat: 'Seaborne Cargo Volume', why: 'Primary raw material volume driver for Capesize & Panamax laden voyages.' },
                    };

                    const defaultMacro = { bdry: 9, brent: -2, wti: 1, bunker_mgo: -1, bunker_vlsfo: -1, gscpi: -1 };
                    const effects = prophetDecomp?.regressor_effects && Object.keys(prophetDecomp.regressor_effects).length > 0
                      ? prophetDecomp.regressor_effects
                      : defaultMacro;

                    const chartData = Object.entries(effects)
                      .map(([key, val]) => {
                        const meta = detailsMap[key] || {
                          label: key.replace(/_/g, ' ').toUpperCase(),
                          cat: 'Market Indicator',
                          why: 'Exogenous regression regressor affecting daily freight rate baseline.',
                        };
                        return {
                          key,
                          name: meta.label,
                          category: meta.cat,
                          val: Math.round(val),
                          why: meta.why,
                        };
                      })
                      .sort((a, b) => b.val - a.val);

                    const maxAbs = Math.max(...chartData.map(d => Math.abs(d.val)), 8);
                    const domainLimit = Math.ceil(maxAbs * 1.25);
                    const netPull = chartData.reduce((acc, c) => acc + c.val, 0);

                    return (
                      <div className="feas-card" style={{ padding: '14px 16px' }}>
                        <div className="feas-card-head" style={{ marginBottom: 12 }}>
                          <div>
                            <span style={{ fontWeight: 600, color: 'var(--sail-100)', fontSize: 13 }}>
                              Diverging Macro Driver Tornado ($/day Additive Attribution)
                            </span>
                            <div style={{ fontSize: 11, color: 'var(--sail-400)', marginTop: 2 }}>
                              Bidirectional impact on baseline freight rate: Cost Easing (Left) vs. Upward Pressure (Right)
                            </div>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 10, fontFamily: 'var(--f-mono)' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#22c55e' }}>
                              <span style={{ width: 8, height: 8, borderRadius: 2, background: '#22c55e' }} /> Cost Easing (-$/d)
                            </span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#ef4444' }}>
                              <span style={{ width: 8, height: 8, borderRadius: 2, background: '#ef4444' }} /> Rate Pressure (+$/d)
                            </span>
                          </div>
                        </div>

                        <div style={{ width: '100%', height: 230 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                              layout="vertical"
                              data={chartData}
                              margin={{ top: 5, right: 30, left: 15, bottom: 5 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" stroke="var(--sail-800)" horizontal={false} />
                              <XAxis
                                type="number"
                                domain={[-domainLimit, domainLimit]}
                                stroke="var(--sail-500)"
                                fontSize={10}
                                tickFormatter={(v) => `${v > 0 ? '+' : ''}${v} $/d`}
                              />
                              <YAxis
                                type="category"
                                dataKey="name"
                                width={110}
                                stroke="var(--sail-300)"
                                fontSize={11}
                                tickLine={false}
                                axisLine={false}
                              />
                              <ReferenceLine x={0} stroke="var(--sail-500)" strokeWidth={1.5} />
                              <Tooltip
                                content={({ active, payload }) => {
                                  if (!active || !payload || !payload.length) return null;
                                  const item = payload[0].payload;
                                  const isPos = item.val >= 0;
                                  return (
                                    <div style={{
                                      background: 'var(--ink-800)',
                                      border: '1px solid var(--sail-700)',
                                      borderRadius: 'var(--r)',
                                      padding: '10px 12px',
                                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                                      maxWidth: 280,
                                    }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--sail-100)' }}>
                                          {item.name}
                                        </span>
                                        <span style={{
                                          fontSize: 11,
                                          fontWeight: 700,
                                          fontFamily: 'var(--f-mono)',
                                          color: isPos ? '#ef4444' : '#22c55e',
                                        }}>
                                          {isPos ? '+' : ''}${item.val} /day
                                        </span>
                                      </div>
                                      <div style={{ fontSize: 10, color: 'var(--sail-400)', textTransform: 'uppercase', marginBottom: 4 }}>
                                        {item.category}
                                      </div>
                                      <div style={{ fontSize: 11, color: 'var(--sail-300)', lineHeight: 1.4 }}>
                                        {item.why}
                                      </div>
                                    </div>
                                  );
                                }}
                              />
                              <Bar dataKey="val" radius={[3, 3, 3, 3]} barSize={14}>
                                {chartData.map((entry, index) => (
                                  <Cell
                                    key={`cell-${index}`}
                                    fill={entry.val >= 0 ? '#ef4444' : '#22c55e'}
                                  />
                                ))}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--sail-800)', fontSize: 11, color: 'var(--sail-400)' }}>
                          <span>Hover any driver bar for instant operational mechanism and P&amp;L transmission context.</span>
                          <span className="mono" style={{ color: 'var(--text-accent)' }}>
                            Net Macro Pull: {netPull >= 0 ? '+' : ''}${netPull} /day
                          </span>
                        </div>
                      </div>
                    );
                  })()}

                  {/* ── 4. Sub-Tab Content: Weekly Trading Seasonality Wave ── */}
                  {driverSubTab === 'seasonality' && (() => {
                    const amp = prophetDecomp?.weekly_seasonality_amplitude ?? 2.0;
                    const seasonalityWave = [
                      { day: 'Mon', diff: Number((-(amp * 0.45)).toFixed(2)), stage: 'Inquiry Opening (Trough)' },
                      { day: 'Tue', diff: Number(((amp * 0.20)).toFixed(2)), stage: 'Firming Bids' },
                      { day: 'Wed', diff: Number(((amp * 0.50)).toFixed(2)), stage: 'Midweek Peak Liquidity' },
                      { day: 'Thu', diff: Number(((amp * 0.35)).toFixed(2)), stage: 'Commitments Closing' },
                      { day: 'Fri', diff: Number((-(amp * 0.30)).toFixed(2)), stage: 'Pre-Weekend Discount' },
                      { day: 'Sat', diff: Number((-(amp * 0.40)).toFixed(2)), stage: 'Market Inactive' },
                      { day: 'Sun', diff: Number((-(amp * 0.50)).toFixed(2)), stage: 'Weekly Low' },
                    ];

                    return (
                      <div className="feas-card" style={{ padding: '14px 16px' }}>
                        <div className="feas-card-head" style={{ marginBottom: 10 }}>
                          <div>
                            <span style={{ fontWeight: 600, color: 'var(--sail-100)', fontSize: 13 }}>
                              Intra-Week Cyclical Freight Negotiation Wave
                            </span>
                            <div style={{ fontSize: 11, color: 'var(--sail-400)', marginTop: 2 }}>
                              Continuous weekly rhythm tracking fixture liquidity premiums across trading days
                            </div>
                          </div>
                          <span className="mono" style={{ color: 'var(--text-accent)', fontSize: 11 }}>
                            ±${(amp / 2).toFixed(1)}/day Amplitude
                          </span>
                        </div>

                        <div style={{ width: '100%', height: 210 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart
                              data={seasonalityWave}
                              margin={{ top: 10, right: 20, left: 10, bottom: 0 }}
                            >
                              <defs>
                                <linearGradient id="seasonalityWaveGrad" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.35} />
                                  <stop offset="95%" stopColor="var(--accent)" stopOpacity={0.0} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="var(--sail-800)" />
                              <XAxis dataKey="day" stroke="var(--sail-400)" fontSize={11} tickLine={false} />
                              <YAxis stroke="var(--sail-500)" fontSize={10} tickFormatter={(v) => `${v > 0 ? '+' : ''}${v} $/t`} />
                              <ReferenceLine y={0} stroke="var(--sail-500)" strokeWidth={1} strokeDasharray="3 3" />
                              <Tooltip
                                content={({ active, payload }) => {
                                  if (!active || !payload || !payload.length) return null;
                                  const d = payload[0].payload;
                                  return (
                                    <div style={{
                                      background: 'var(--ink-800)',
                                      border: '1px solid var(--sail-700)',
                                      borderRadius: 'var(--r)',
                                      padding: '8px 12px',
                                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                                    }}>
                                      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--sail-100)' }}>
                                        {d.day} — {d.stage}
                                      </div>
                                      <div style={{ fontSize: 11, fontFamily: 'var(--f-mono)', color: d.diff >= 0 ? '#ef4444' : '#22c55e', marginTop: 2 }}>
                                        Rate Spread: {d.diff >= 0 ? '+' : ''}${d.diff.toFixed(2)}/t
                                      </div>
                                    </div>
                                  );
                                }}
                              />
                              <Area
                                type="monotone"
                                dataKey="diff"
                                stroke="var(--accent)"
                                strokeWidth={2.5}
                                fill="url(#seasonalityWaveGrad)"
                              />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--sail-800)', fontSize: 11, color: 'var(--sail-300)' }}>
                          <span><strong>Execution Rule:</strong> Enter firm counter-offers on Monday/Friday trough to avoid midweek fixture rush.</span>
                          <span className="mono" style={{ color: 'var(--text-accent)' }}>Peak: Wednesday (+${(amp * 0.5).toFixed(2)}/t)</span>
                        </div>
                      </div>
                    );
                  })()}

                  {/* ── 5. Sub-Tab Content: XGBoost Feature Importances ── */}
                  {driverSubTab === 'importances' && hasImportances && (
                    <div className="feas-card" style={{ padding: '14px 16px' }}>
                      <div className="feas-card-head" style={{ marginBottom: 12 }}>
                        <span style={{ fontWeight: 600, color: 'var(--sail-100)', fontSize: 13 }}>
                          XGBoost Non-Linear Predictive Feature Weights
                        </span>
                        <span className="mono" style={{ color: 'var(--sail-500)', fontSize: 11 }}>
                          Gradient Boosting Gating Layer
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {(() => {
                          const entries = Object.entries(parsedExplanation!.importances).sort((a, b) => b[1] - a[1]);
                          const maxV = entries.length > 0 ? entries[0][1] : 1;
                          return entries.slice(0, 8).map(([key, val]) => (
                            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                              <span style={{ width: 130, fontSize: 11, color: 'var(--sail-300)', textTransform: 'capitalize', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {key.replace(/_/g, ' ')}
                              </span>
                              <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
                                <div style={{ flex: 1, height: 6, background: 'var(--sail-800)', borderRadius: 3, overflow: 'hidden' }}>
                                  <div style={{ width: `${(val / maxV) * 100}%`, height: '100%', background: 'var(--accent)' }} />
                                </div>
                                <span className="mono" style={{ minWidth: 40, textAlign: 'right', fontSize: 11, color: 'var(--sail-400)', fontWeight: 600 }}>
                                  {(val * 100).toFixed(1)}%
                                </span>
                              </div>
                            </div>
                          ));
                        })()}
                      </div>
                    </div>
                  )}
                </>
              );
            })() : forecast ? (
              <p className="infer">No driver explanation available for this forecast object. It will be populated during the next retrain cycle.</p>
            ) : (
              <p className="infer">Driver and profit explanation appears after a forecast is loaded.</p>
            )}
          </div>
        </section>
      </div>

      {/* ── RIGHT col-3: PAIR COVERAGE & CHARTERING PROFIT PLAYBOOK ── */}
      <div className="col-3 col-space">
        <section className="panel panel-tinted">
          <div className="panel-hd">
            <span className="panel-title">Pair Coverage Availability</span>
          </div>
          <div className="panel-body" style={{ overflowX: 'auto' }}>
            {pairStatuses.length === 0 ? (
              <p className="infer">Scanning system for available models…</p>
            ) : (() => {
              const origins  = [...new Set(pairStatuses.map(p => p.origin))];
              const vessels  = [...new Set(pairStatuses.map(p => p.vessel))];
              const byKey    = Object.fromEntries(pairStatuses.map(p => [`${p.origin}|${p.dest}|${p.vessel}`, p]));
              const dests    = [...new Set(pairStatuses.map(p => p.dest))];

              function statusColor(s: string) {
                if (s === 'serving') return 'var(--text-accent)';
                if (s === 'high-uncertainty') return 'var(--warn)';
                if (s === 'no-data') return 'var(--sail-700)';
                return 'var(--sail-600)';
              }

              return (
                <table style={{ width: '100%', fontSize: 10, fontFamily: 'var(--f-mono)', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ color: 'var(--sail-500)' }}>
                      <th style={{ textAlign: 'left', padding: '4px 0' }}>Route</th>
                      {vessels.map(v => <th key={v} style={{ textAlign: 'center', padding: '4px 2px' }}>{v.split('/')[0].slice(0,5)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {origins.flatMap(o => dests.map(d => {
                      const hasAnyModel = vessels.some(v => {
                        const p = byKey[`${o}|${d}|${v}`];
                        return p && p.status !== 'no-data';
                      });
                      if (!hasAnyModel) return null;
                      return (
                        <tr key={`${o}|${d}`} style={{ borderBottom: '1px solid color-mix(in srgb, var(--sail-700) 20%, transparent)' }}>
                          <td style={{ padding: '6px 0', color: 'var(--sail-300)', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {o.split('(')[0].trim().slice(0,6)}➔{d.slice(0,6)}
                          </td>
                          {vessels.map(v => {
                            const p = byKey[`${o}|${d}|${v}`];
                            if (!p) return <td key={v} />;
                            return <td key={v} style={{ textAlign: 'center', fontSize: '12px', color: statusColor(p.status) }}>
                              {p.status !== 'no-data' ? '●' : '○'}
                            </td>;
                          })}
                        </tr>
                      );
                    }))}
                  </tbody>
                </table>
              );
            })()}
            <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--sail-400)' }}>
                <span style={{ color: 'var(--text-accent)', fontSize: '14px' }}>●</span> Model Trained & Serving
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--sail-400)' }}>
                <span style={{ color: 'var(--warn)', fontSize: '14px' }}>●</span> High Uncertainty (Damped)
              </div>
            </div>
          </div>
        </section>

        {/* ── CHARTERING PROFIT STRATEGY PLAYBOOK (Side col-3) ── */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Chartering Profit Playbook</span>
            <span className="panel-meta">Tactical Action</span>
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {forecast ? (() => {
              const trendDelta = prophetDecomp?.trend_delta ?? 4;
              const isRising = trendDelta > 0.5;
              const isFalling = trendDelta < -0.5;

              return (
                <>
                  {/* Strategy Verdict Card */}
                  <div style={{
                    padding: '10px 12px',
                    borderRadius: 'var(--r)',
                    background: isRising ? 'rgba(239, 68, 68, 0.08)' : isFalling ? 'rgba(34, 197, 94, 0.08)' : 'rgba(245, 158, 11, 0.08)',
                    border: isRising ? '1px solid rgba(239, 68, 68, 0.25)' : isFalling ? '1px solid rgba(34, 197, 94, 0.25)' : '1px solid rgba(245, 158, 11, 0.25)',
                  }}>
                    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--sail-400)', marginBottom: 2 }}>
                      Recommended Commercial Stance
                    </div>
                    <div style={{
                      fontSize: 14,
                      fontWeight: 700,
                      color: isRising ? '#ef4444' : isFalling ? '#22c55e' : '#f59e0b',
                    }}>
                      {isRising ? 'LOCK COA FORWARD NOW' : isFalling ? 'FLOAT ON SPOT MARKET' : 'INDEX-LINKED FIXING'}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--sail-300)', marginTop: 4, lineHeight: 1.4 }}>
                      {isRising
                        ? 'Projected rate inflation of +$' + trendDelta.toFixed(2) + '/t suggests forward coverage to hedge spot market exposure.'
                        : isFalling
                        ? 'Softening freight trajectory indicates delaying commitments will yield lower freight disbursements.'
                        : 'Low directional momentum supports floating rate or index-linked contract clauses.'}
                    </div>
                  </div>

                  {/* Commercial Benchmark List */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div className="feas-card" style={{ padding: '8px 10px' }}>
                      <div className="feas-card-head">
                        <span style={{ fontSize: 11, color: 'var(--sail-400)' }}>Optimal Laycan Window</span>
                        <span className="mono" style={{ fontSize: 11, color: 'var(--sail-100)', fontWeight: 600 }}>&lt; 10 Days</span>
                      </div>
                      <div className="feas-card-sub">Fix before projected rate lift</div>
                    </div>

                    <div className="feas-card" style={{ padding: '8px 10px' }}>
                      <div className="feas-card-head">
                        <span style={{ fontSize: 11, color: 'var(--sail-400)' }}>Breakeven Freight Floor</span>
                        <span className="mono" style={{ fontSize: 11, color: 'var(--text-accent)', fontWeight: 600 }}>
                          ${(forecast.point_estimate * 0.92).toFixed(2)}/t
                        </span>
                      </div>
                      <div className="feas-card-sub">Operating cost breakeven threshold</div>
                    </div>

                    <div className="feas-card" style={{ padding: '8px 10px' }}>
                      <div className="feas-card-head">
                        <span style={{ fontSize: 11, color: 'var(--sail-400)' }}>Bunker Spread Risk</span>
                        <span className="mono" style={{ fontSize: 11, color: 'var(--warn)', fontWeight: 600 }}>Elevated</span>
                      </div>
                      <div className="feas-card-sub">Recommend 11.5 kn Eco Steaming mode</div>
                    </div>
                  </div>

                  <p className="infer" style={{ margin: 0, fontSize: 10.5 }}>
                    Coupled with Recommendations MILP solver to optimize fleet assignment across scenarios.
                  </p>
                </>
              );
            })() : (
              <p className="infer">Commercial strategy will populate once forecast data is loaded.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default ForecastExplorerPage;
