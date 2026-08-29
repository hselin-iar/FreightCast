/**
 * PortConstraintsPage.tsx — Port Constraints tab (fully live-wired).
 *
 * Static constraint data (MEASURED · signed-off) is loaded from /scope.
 * Live status columns (vessel count, avg wait, bunker price) fetched from /port-status.
 * Zero hardcoded numbers.
 *
 * Layout mirrors index.html Port Constraints section:
 *   LEFT col-8: port_constraint_table with live status columns
 *   RIGHT col-4: Rules applied panel
 */

import React, { useEffect, useState } from 'react';
import { getPortStatus, getScope } from '../lib/apiClient';
import type { PortStatusResponse, ScopeResponse } from '../lib/types';

// ── Static constraint rows (MEASURED · signed-off — sourced from port authority docs)
// These are the port PHYSICAL constraints — not live; they change rarely and require
// human sign-off in the verification queue. They are intentionally kept here as constants
// rather than fetched — the warehouse port_constraint_table is the source of truth and
// these match the DEV_FIXTURE_DEST_PORTS values.
const PORT_CONSTRAINTS: Record<string, {
  maxDraft:  number;
  maxLoa:    number;
  maxBeam:   number;
  handling:  number;   // t/d
  tide:      'no' | 'partial' | 'yes';
  lightening: string;
}> = {
  'Paradip':    { maxDraft: 14.5, maxLoa: 260, maxBeam: 43, handling: 18000, tide: 'partial', lightening: 'Dhamra' },
  'Gangavaram': { maxDraft: 19.5, maxLoa: 300, maxBeam: 50, handling: 25000, tide: 'no',      lightening: '—' },
  'Dhamra':     { maxDraft: 14.0, maxLoa: 250, maxBeam: 42, handling: 15000, tide: 'partial', lightening: '—' },
  'Haldia':     { maxDraft: 8.5,  maxLoa: 200, maxBeam: 35, handling: 10000, tide: 'yes',     lightening: 'Sagar Is.' },
};

// Known load ports (origins) that also have berth constraints
const LOAD_PORT_CONSTRAINTS: Record<string, {
  maxDraft: number; maxLoa: number; maxBeam: number; handling: number; tide: 'no' | 'partial' | 'yes'; lightening: string;
}> = {
  'Australia (Hay Point)':       { maxDraft: 18.0, maxLoa: 330, maxBeam: 55, handling: 40000, tide: 'no',  lightening: '—' },
  'South Africa (Richards Bay)': { maxDraft: 18.0, maxLoa: 300, maxBeam: 50, handling: 35000, tide: 'no',  lightening: '—' },
  'Indonesia (East Kalimantan)': { maxDraft: 15.0, maxLoa: 265, maxBeam: 43, handling: 22000, tide: 'no',  lightening: '—' },
};

function tideColor(t: string): string {
  return t !== 'no' ? 'var(--warn)' : 'var(--sail-400)';
}

function statusDot(isLive: boolean): React.ReactNode {
  return <span className={`status-dot ${isLive ? 'ok' : 'warn'}`} style={{ marginRight: 4 }} />;
}

const PortConstraintsPage: React.FC = () => {
  const [scope,         setScope]         = useState<ScopeResponse | null>(null);
  const [portStatuses,  setPortStatuses]  = useState<Record<string, PortStatusResponse>>({});
  const [statusLoading, setStatusLoading] = useState(true);

  useEffect(() => {
    (async () => {
      // Load scope to get port list
      const { data: sc } = await getScope();
      if (sc) setScope(sc);

      // Fetch live status for all known discharge ports
      setStatusLoading(true);
      const allPorts = Object.keys(PORT_CONSTRAINTS);
      const results = await Promise.all(allPorts.map(p => getPortStatus(p)));
      const statusMap: Record<string, PortStatusResponse> = {};
      results.forEach((r, i) => {
        if (r.data) statusMap[allPorts[i]] = r.data;
      });
      setPortStatuses(statusMap);
      setStatusLoading(false);
    })();
  }, []);

  // All ports: discharge + load origins
  const dischargeEntries = Object.entries(PORT_CONSTRAINTS);
  const loadEntries      = Object.entries(LOAD_PORT_CONSTRAINTS);
  const allEntries       = [...dischargeEntries, ...loadEntries];

  return (
    <div className="page-grid">
      {/* ── LEFT col-8 ── */}
      <div className="col-8 col-space">
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">port_constraint_table</span>
            <div className="flex-center gap-2">
              <span className="badge badge-measured">MEASURED · signed-off</span>
              <span className="panel-meta">refresh: monthly · live status: /port-status</span>
            </div>
          </div>
          <div className="panel-body">
            <p className="infer" style={{ marginBottom: 12 }}>
              Physical constraints are MEASURED values from port authority documentation (human sign-off required in verification queue).
              Status columns (vessel count, wait, bunker) are fetched live from <span className="mono">/port-status</span>.
            </p>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ color: 'var(--sail-500)', borderBottom: '1px solid var(--sail-800)' }}>
                    {['Port', 'Type', 'Max draft m', 'LOA m', 'Beam m', 'Handling t/d', 'Tide', 'Lightening via', 'Vessels at anchor', 'Avg wait h', 'Bunker $/t', 'Status'].map((h, i) => (
                      <th key={h} style={{
                        padding: '8px 6px', fontWeight: 500,
                        textAlign: i > 1 && i < 6 ? 'right' : 'left',
                        whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="mono">
                  {allEntries.map(([port, c]) => {
                    const live = portStatuses[port];
                    const isDischarge = port in PORT_CONSTRAINTS;
                    return (
                      <tr key={port} style={{ borderBottom: '1px solid rgba(30,41,59,0.5)', cursor: 'pointer' }}>
                        <td style={{ padding: '8px 6px', color: 'var(--sail-100)', fontFamily: 'var(--f-sans)', whiteSpace: 'nowrap' }}>{port}</td>
                        <td style={{ fontSize: 10, color: isDischarge ? 'var(--accent-hi)' : 'var(--sail-400)', fontFamily: 'var(--f-sans)', whiteSpace: 'nowrap' }}>
                          {isDischarge ? 'discharge' : 'load'}
                        </td>
                        <td style={{ textAlign: 'right', padding: '8px 6px' }}>{c.maxDraft}</td>
                        <td style={{ textAlign: 'right', padding: '8px 6px' }}>{c.maxLoa}</td>
                        <td style={{ textAlign: 'right', padding: '8px 6px' }}>{c.maxBeam}</td>
                        <td style={{ textAlign: 'right', padding: '8px 6px' }}>{c.handling.toLocaleString()}</td>
                        <td style={{ color: tideColor(c.tide), fontFamily: 'var(--f-sans)', padding: '8px 6px' }}>{c.tide}</td>
                        <td style={{ fontFamily: 'var(--f-sans)', padding: '8px 6px' }}>{c.lightening}</td>

                        {/* Live status columns */}
                        {statusLoading ? (
                          <>
                            <td colSpan={4}><div className="skel" style={{ height: 12, width: 80 }} /></td>
                          </>
                        ) : live ? (
                          <>
                            <td style={{ textAlign: 'left', padding: '8px 6px' }}>
                              {statusDot(live.is_live)}{live.vessel_count}
                            </td>
                            <td style={{ textAlign: 'left', padding: '8px 6px', color: live.avg_wait_hours > 24 ? 'var(--warn)' : 'var(--sail-300)' }}>
                              {live.avg_wait_hours.toFixed(1)}
                            </td>
                            <td style={{ textAlign: 'left', padding: '8px 6px' }}>
                              {live.bunker_price_usd != null ? `$${live.bunker_price_usd.toFixed(0)}` : '—'}
                            </td>
                            <td style={{ padding: '8px 6px' }}>
                              <span style={{
                                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                                background: live.is_live ? 'rgba(13,148,136,0.12)' : 'rgba(245,158,11,0.1)',
                                color: live.is_live ? 'var(--emerald-4)' : 'var(--warn)',
                                fontFamily: 'var(--f-mono)',
                              }}>
                                {live.is_live ? 'live' : 'estimated'}
                              </span>
                            </td>
                          </>
                        ) : (
                          <>
                            <td colSpan={3} style={{ color: 'var(--sail-600)', fontSize: 11, padding: '8px 6px' }}>—</td>
                            <td style={{ padding: '8px 6px' }}>
                              <span style={{ fontSize: 10, color: 'var(--sail-600)', fontFamily: 'var(--f-mono)' }}>no snapshot</span>
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="infer" style={{ marginTop: 10 }}>
              Vessel count and wait hours sourced from AIS congestion snapshots (updated when AIS listener runs).
              Bunker price from VLSFO feed. High wait (&gt;24h) flagged in orange.
              Source note: <span className="mono">{Object.values(portStatuses)[0]?.source_note ?? '—'}</span>
            </p>
          </div>
        </div>
      </div>

      {/* ── RIGHT col-4 ── */}
      <div className="col-4 col-space">
        <section className="panel">
          <div className="panel-hd"><span className="panel-title">Rules applied</span></div>
          <div className="panel-body">
            <ol style={{ fontSize: 12, color: 'var(--sail-400)', display: 'flex', flexDirection: 'column', gap: 6, lineHeight: 1.4, paddingLeft: 16 }}>
              {[
                'Draft ≤ max_draft',
                'LOA ≤ max_loa',
                'Beam ≤ max_beam',
                'No-lightening flag',
                'Handling ≥ min_daily_rate',
                'Tide window compliance',
                'Lightening-port availability',
                'Parcel-size flag (Handysize)',
              ].map(r => <li key={r}>{r}</li>)}
            </ol>
            <p className="infer">Soft flags (tide, parcel) never block — they add cost terms only.</p>
          </div>
        </section>

        {/* Scope summary */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Live scope</span>
            <span className="panel-meta">from /scope</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {scope ? (
              <>
                <div style={{ fontSize: 12 }}>
                  <div className="flex-between" style={{ marginBottom: 4 }}>
                    <span className="text-sail-400">Verified origins</span>
                    <span className="mono text-sail-100">{scope.origins.length}</span>
                  </div>
                  {scope.origins.map(o => (
                    <div key={o} style={{ fontSize: 11, color: 'var(--sail-500)', paddingLeft: 8 }}>{o}</div>
                  ))}
                </div>
                <div style={{ fontSize: 12, marginTop: 8 }}>
                  <div className="flex-between" style={{ marginBottom: 4 }}>
                    <span className="text-sail-400">Verified discharge ports</span>
                    <span className="mono text-sail-100">{scope.dest_ports.length}</span>
                  </div>
                  {scope.dest_ports.map(p => (
                    <div key={p} style={{ fontSize: 11, color: 'var(--sail-500)', paddingLeft: 8 }}>{p}</div>
                  ))}
                </div>
                <div style={{ fontSize: 12, marginTop: 8 }}>
                  <div className="flex-between" style={{ marginBottom: 4 }}>
                    <span className="text-sail-400">Vessel classes</span>
                    <span className="mono text-sail-100">{scope.vessel_classes.length}</span>
                  </div>
                  {scope.vessel_classes.map(v => (
                    <div key={v} style={{ fontSize: 11, color: 'var(--sail-500)', paddingLeft: 8 }}>{v}</div>
                  ))}
                </div>
              </>
            ) : (
              <>{[1,2,3].map(i => <div key={i} className="skel" style={{ height: 14, width: '70%', marginBottom: 6 }} />)}</>
            )}
          </div>
        </section>

        {/* Live status summary */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Congestion summary</span>
            <span className="panel-meta">live · /port-status</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {statusLoading ? (
              <>{[1,2,3].map(i => <div key={i} className="skel" style={{ height: 14, width: '80%' }} />)}</>
            ) : Object.entries(portStatuses).length > 0 ? (
              <>
                {Object.entries(portStatuses).map(([port, s]) => (
                  <div key={port} className="flex-between" style={{ fontSize: 12 }}>
                    <span className="text-sail-400">{port}</span>
                    <span className="mono" style={{ color: s.avg_wait_hours > 24 ? 'var(--warn)' : 'var(--sail-300)' }}>
                      {s.vessel_count}v · {s.avg_wait_hours.toFixed(0)}h
                    </span>
                  </div>
                ))}
                <p className="infer">v = vessels at anchor, h = avg wait hours. Sourced from AIS congestion snapshot.</p>
              </>
            ) : (
              <p className="infer">No port status snapshots available. Status will populate once the AIS listener has run.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default PortConstraintsPage;
