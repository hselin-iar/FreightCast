/**
 * FleetSchedulePage.tsx — Fleet Portfolio & AIS Scheduling (Step 51V).
 *
 * Visualizes the research pipeline's global multi-contract portfolio optimization,
 * physical AIS ship assignments, temporal conflict graphs, and SAIL/KILL economics.
 */
import React, { useEffect, useState } from 'react';
import { getFleetSchedule } from '../lib/apiClient';
import type { FleetScheduleResponse } from '../lib/types';

const FleetSchedulePage: React.FC = () => {
  const [data, setData] = useState<FleetScheduleResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<'sail' | 'schedule' | 'all'>('sail');

  useEffect(() => {
    const fetchSchedule = async () => {
      setLoading(true);
      setError(null);
      const res = await getFleetSchedule();
      if (res.data) {
        setData(res.data);
      } else if (res.error) {
        setError(res.error.message);
      }
      setLoading(false);
    };

    fetchSchedule();
  }, []);

  if (loading) {
    return (
      <div className="panel" style={{ padding: '3rem', textAlign: 'center' }}>
        <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>⏳ Loading Step 51V Fleet Portfolio…</div>
        <div style={{ color: 'var(--text-muted)' }}>Reading live solver outputs & vessel assignments</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="panel" style={{ padding: '2rem', borderColor: 'var(--danger)' }}>
        <div style={{ fontSize: '1.25rem', color: 'var(--danger)', fontWeight: 600, marginBottom: '0.5rem' }}>
          ⚠️ Unable to load Step 51V Fleet Schedule
        </div>
        <div style={{ color: 'var(--text-muted)' }}>{error ?? 'Unknown error loading optimization files.'}</div>
      </div>
    );
  }

  const { summary, assignments, vessel_schedule, all_decisions } = data;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* ── Header & Context Banner ── */}
      <div className="panel" style={{ background: 'linear-gradient(135deg, rgba(14,165,233,0.1) 0%, rgba(99,102,241,0.05) 100%)', border: '1px solid rgba(14,165,233,0.3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <span style={{ background: '#0284c7', color: '#fff', padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 700 }}>
                RESEARCH ENGINE: STEP 51V
              </span>
              <span style={{ fontSize: '1.25rem', fontWeight: 700 }}>Global Fleet Portfolio & AIS Scheduling</span>
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', maxWidth: '750px' }}>
              Multi-contract combinatorial MILP from <code>freight_optimization/</code>. Matches tracked AIS vessels to 16 contracts, enforces physical non-overlapping voyage intervals, and optimizes portfolio downside protection against Bear/Base/Bull scenarios.
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>SOLVER ENGINE</div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>
              {summary.solver_status}
            </div>
          </div>
        </div>
      </div>

      {/* ── KPI Summary Cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        <div className="panel" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Worst-Case Incremental
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#10b981', marginTop: '0.25rem' }}>
            +${(summary.worst_incremental_usd / 1_000_000).toFixed(2)}M
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Base: +${(summary.base_incremental_usd / 1_000_000).toFixed(2)}M | Bull: +${(summary.bull_incremental_usd / 1_000_000).toFixed(2)}M
          </div>
        </div>

        <div className="panel" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Contract Portfolio Decisions
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#38bdf8', marginTop: '0.25rem' }}>
            {summary.sail_contracts} SAIL <span style={{ fontSize: '1rem', color: 'var(--text-muted)', fontWeight: 400 }}>/ {summary.kill_contracts} KILL</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            {summary.total_contracts} total evaluated contracts
          </div>
        </div>

        <div className="panel" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Total Portfolio Voyage Cost
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#f59e0b', marginTop: '0.25rem' }}>
            ${(summary.total_voyage_cost_usd / 1_000_000).toFixed(2)}M
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Bunker: ${(summary.bunker_cost_usd / 1_000_000).toFixed(2)}M | OPEX: ${(summary.opex_cost_usd / 1_000_000).toFixed(2)}M
          </div>
        </div>

        <div className="panel" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            AIS Live Fleet & Bunker
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#818cf8', marginTop: '0.25rem' }}>
            {summary.sail_vessels} Vessels
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            VLSFO Reference: ${summary.bunker_price_vlsfo_usd}/MT
          </div>
        </div>
      </div>

      {/* ── Sub-Navigation ── */}
      <div style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem' }}>
        <button
          className={`btn ${activeSubTab === 'sail' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveSubTab('sail')}
          style={{ fontSize: '0.85rem' }}
        >
          🚢 Active SAIL Assignments ({assignments.length})
        </button>
        <button
          className={`btn ${activeSubTab === 'schedule' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveSubTab('schedule')}
          style={{ fontSize: '0.85rem' }}
        >
          📅 AIS Vessel Schedule ({vessel_schedule.length})
        </button>
        <button
          className={`btn ${activeSubTab === 'all' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveSubTab('all')}
          style={{ fontSize: '0.85rem' }}
        >
          📋 Complete 16-Contract Portfolio ({all_decisions.length})
        </button>
      </div>

      {/* ── SUB-TAB 1: Active SAIL Assignments ── */}
      {activeSubTab === 'sail' && (
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">Active SAIL Contract Assignments</span>
            <span className="panel-meta">Step 51V Optimal Fleet Allocation</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ width: '100%', fontSize: '0.85rem' }}>
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>Route</th>
                  <th>Cargo</th>
                  <th>Assigned Vessel</th>
                  <th>Class / DWT</th>
                  <th>Departure</th>
                  <th>Est. ETA</th>
                  <th>Voyage Cost</th>
                  <th>Worst Incr.</th>
                  <th>Base Incr.</th>
                  <th>Decision</th>
                </tr>
              </thead>
              <tbody>
                {assignments.map((a) => (
                  <tr key={a.contract_id}>
                    <td>
                      <span style={{ fontWeight: 700, color: '#38bdf8' }}>{a.contract_id}</span>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{a.cargo_type}</div>
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{a.origin}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>→ {a.destination}</div>
                    </td>
                    <td>{Math.round(a.contract_volume_mt).toLocaleString()} MT</td>
                    <td>
                      <div style={{ fontWeight: 700, color: '#10b981' }}>{a.vessel_name ?? '—'}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>IMO {a.imo ?? '—'}</div>
                    </td>
                    <td>
                      <div>{a.vessel_class}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {a.vessel_dwt ? `${Math.round(a.vessel_dwt).toLocaleString()} DWT` : ''}
                      </div>
                    </td>
                    <td>
                      {a.departure_date ? new Date(a.departure_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                    </td>
                    <td>
                      {a.estimated_eta ? new Date(a.estimated_eta).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                    </td>
                    <td>${Math.round(a.total_voyage_cost_usd).toLocaleString()}</td>
                    <td style={{ color: '#10b981', fontWeight: 700 }}>
                      +${Math.round(a.worst_incremental).toLocaleString()}
                    </td>
                    <td style={{ color: '#38bdf8' }}>
                      +${Math.round(a.base_incremental).toLocaleString()}
                    </td>
                    <td>
                      <span style={{ background: '#065f46', color: '#34d399', padding: '0.2rem 0.5rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.75rem' }}>
                        {a.decision}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── SUB-TAB 2: AIS Vessel Schedule ── */}
      {activeSubTab === 'schedule' && (
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">Physical AIS Vessel Scheduling Timeline</span>
            <span className="panel-meta">Non-overlapping voyage windows</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
            {vessel_schedule.map((v) => (
              <div
                key={`${v.imo}-${v.contract_id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1.5rem',
                  padding: '1rem',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ minWidth: '180px' }}>
                  <div style={{ fontSize: '1rem', fontWeight: 700, color: '#10b981' }}>{v.vessel_name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>IMO: {v.imo}</div>
                </div>

                <div style={{ flex: 1, minWidth: '250px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', fontWeight: 600 }}>
                    <span>{v.origin}</span>
                    <span style={{ color: 'var(--text-muted)' }}>➔</span>
                    <span>{v.destination}</span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    Contract: <strong style={{ color: '#38bdf8' }}>{v.contract_id}</strong> ({Math.round(v.contract_volume_mt).toLocaleString()} MT)
                  </div>
                </div>

                <div style={{ minWidth: '220px', fontSize: '0.85rem' }}>
                  <div>🛫 Departure: <strong>{new Date(v.departure_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}</strong></div>
                  <div>🛬 ETA: <strong>{new Date(v.estimated_eta).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}</strong></div>
                </div>

                <div style={{ textAlign: 'right', minWidth: '140px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Worst Incremental</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#10b981' }}>
                    +${Math.round(v.worst_incremental).toLocaleString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── SUB-TAB 3: Complete Contract Portfolio ── */}
      {activeSubTab === 'all' && (
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">Complete 16-Contract Portfolio Decisions</span>
            <span className="panel-meta">Full SAIL vs KILL Tradeoff Audit</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ width: '100%', fontSize: '0.85rem' }}>
              <thead>
                <tr>
                  <th>Contract ID</th>
                  <th>Route</th>
                  <th>Volume (MT)</th>
                  <th>Assigned IMO / Vessel</th>
                  <th>Decision</th>
                  <th>Status Rationale</th>
                </tr>
              </thead>
              <tbody>
                {all_decisions.map((d: any, idx: number) => {
                  const isSail = d.decision === 'SAIL' || d.selected === 1 || d.selected === '1';
                  return (
                    <tr key={idx} style={{ opacity: isSail ? 1 : 0.7 }}>
                      <td style={{ fontWeight: 700, color: isSail ? '#38bdf8' : 'var(--text-muted)' }}>
                        {d.contract_id || `CONTRACT_${String(idx).padStart(3, '0')}`}
                      </td>
                      <td>{d.origin ? `${d.origin} → ${d.destination}` : d.route_id || '—'}</td>
                      <td>{d.contract_volume_mt ? `${Math.round(Number(d.contract_volume_mt)).toLocaleString()} MT` : '—'}</td>
                      <td>{d.vessel_name ? `${d.vessel_name} (${d.imo})` : 'None (Killed)'}</td>
                      <td>
                        <span
                          style={{
                            background: isSail ? '#065f46' : '#7f1d1d',
                            color: isSail ? '#34d399' : '#f87171',
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            fontWeight: 700,
                            fontSize: '0.75rem',
                          }}
                        >
                          {isSail ? 'SAIL' : 'KILL'}
                        </span>
                      </td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {isSail
                          ? 'Optimal incremental profit; cleared ship temporal constraints.'
                          : 'Negative or suboptimal incremental return vs alternative fixture.'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default FleetSchedulePage;
