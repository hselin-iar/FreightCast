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
} from 'recharts';
import { getForecast, getScope } from '../lib/apiClient';
import type { ForecastResponse, ScopeResponse } from '../lib/types';

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
        background: 'rgba(15,23,42,0.6)', border: '1px solid var(--sail-800)', borderRadius: 4,
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
            style={{ padding: '4px 12px', fontSize: '11px', background: view === 'chart' ? 'var(--sail-700)' : 'transparent', color: view === 'chart' ? '#fff' : 'var(--sail-400)', border: 'none', cursor: 'pointer' }}
          >
            Chart View
          </button>
          <button
            onClick={() => setView('table')}
            style={{ padding: '4px 12px', fontSize: '11px', background: view === 'table' ? 'var(--sail-700)' : 'transparent', color: view === 'table' ? '#fff' : 'var(--sail-400)', border: 'none', cursor: 'pointer' }}
          >
            Table View
          </button>
        </div>
      </div>

      {view === 'chart' ? (
        <div style={{ height: 260, background: 'rgba(15,23,42,0.6)', border: '1px solid var(--sail-800)', borderRadius: 4, padding: '16px 16px 0 0' }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickMargin={8} minTickGap={20} />
              <YAxis domain={[minVal, maxVal]} stroke="#64748b" fontSize={11} tickFormatter={(v) => `$${formatNum(v, 0)}`} width={50} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px' }}
                itemStyle={{ color: '#fff' }}
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
              <Area type="monotone" dataKey="band" fill="#0d9488" stroke="none" fillOpacity={0.15} />
              <Line type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3, fill: 'var(--accent)' }} activeDot={{ r: 5 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div style={{ height: 260, overflowY: 'auto', background: 'rgba(15,23,42,0.6)', border: '1px solid var(--sail-800)', borderRadius: 4 }}>
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
                <tr key={i} style={{ borderBottom: '1px solid rgba(51,65,85,0.3)' }}>
                  <td style={{ padding: '8px 16px', textAlign: 'left', color: 'var(--sail-300)' }}>{row.date}</td>
                  <td style={{ padding: '8px 16px', color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>${formatNum(row.band[0], 2)}</td>
                  <td style={{ padding: '8px 16px', color: 'var(--accent-hi)', fontFamily: 'var(--f-mono)', fontWeight: 600 }}>${formatNum(row.value, 2)}</td>
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
  const [scope, setScope] = useState<ScopeResponse | null>(null);
  const [scopeError, setScopeError] = useState<string | null>(null);

  const [selectedOrigin,  setSelectedOrigin]  = useState('');
  const [selectedDest,    setSelectedDest]    = useState('');
  const [selectedVessel,  setSelectedVessel]  = useState('');
  const [selectedHorizon, setSelectedHorizon] = useState(14);

  const [forecast,  setForecast]  = useState<ForecastResponse | null>(null);
  const [fcLoading, setFcLoading] = useState(false);
  const [fcError,   setFcError]   = useState<string | null>(null);

  const [pairStatuses, setPairStatuses] = useState<PairStatus[]>([]);

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
  const modelUsed         = forecast?.model_used ?? '—';

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
              </>
            ) : (
              <p className="infer">Conditions monitor status appears after forecast loads.</p>
            )}
          </div>
        </section>
      </div>

      {/* ── CENTER col-6 ── */}
      <div className="col-6 col-space">
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
                      <span className={`badge badge-${forecast.provenance}`}>{forecast.provenance.toUpperCase()}</span>
                      {forecast.is_high_uncertainty && <span className="badge badge-assumed">HIGH UNCERTAINTY</span>}
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--sail-100)' }}>
                      {forecast.route} · {forecast.vessel_class} · {forecast.horizon_days}d
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontSize: 10, color: 'var(--sail-500)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Point · {forecast.horizon_days}d</div>
                    <div style={{ fontSize: 24, fontWeight: 600, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)' }}>
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
                      <div style={{ fontSize: 11, color: selectedHorizon === h.days ? 'var(--accent-hi)' : 'var(--sail-500)' }}>{h.label}</div>
                      <div className="mono" style={{ color: 'var(--sail-100)', fontSize: 13, fontWeight: 500 }}>
                        {selectedHorizon === h.days ? `$${formatNum(forecast.point_estimate, 2)}` : '—'}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--sail-500)' }}>
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
              <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(15,23,42,0.6)', border: '1px solid var(--sail-800)', borderRadius: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--sail-500)' }}>Select a valid configuration to view trajectory.</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── RIGHT col-3 ── */}
      <div className="col-3 col-space">
        <section className="panel">
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
                if (s === 'serving') return 'var(--accent-hi)';
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
                      if (!hasAnyModel) return null; // Hide routes with completely zero models
                      return (
                        <tr key={`${o}|${d}`} style={{ borderBottom: '1px solid rgba(51,65,85,0.2)' }}>
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
                <span style={{ color: 'var(--accent-hi)', fontSize: '14px' }}>●</span> Model Trained & Serving
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--sail-400)' }}>
                <span style={{ color: 'var(--warn)', fontSize: '14px' }}>●</span> High Uncertainty (Damped)
              </div>
            </div>
          </div>
        </section>
        
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Rate driver explanation</span>
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
      </div>
    </div>
  );
};

export default ForecastExplorerPage;
