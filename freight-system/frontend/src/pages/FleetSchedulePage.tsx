import React, { useEffect, useState, useMemo } from 'react';
import { getFleetStatus, getFleetSchedule, solveFleetSchedule } from '../lib/apiClient';
import type {
  FleetStatusResponse,
  FleetScheduleResponse,
  VesselClassEntry,
  LiveVesselStatus,
  VesselScheduleItem,
} from '../lib/types';
import ProvenanceBadge from '../components/ProvenanceBadge';

/* ── Vector SVG Icons (Strictly Zero Emojis) ───────────────── */
const IconShip: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'inline-block', verticalAlign: 'middle' }}>
    <path d="M2 21c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1 .6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
    <path d="M19.38 20A11.6 11.6 0 0 0 21 14l-9-4-9 4c0 2.9.94 5.34 2.81 7.15" />
    <path d="M12 10V4" />
    <path d="M12 4l5 3" />
  </svg>
);

const IconGantt: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'inline-block', verticalAlign: 'middle' }}>
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
    <path d="M8 14h4" />
    <path d="M12 18h6" />
  </svg>
);

const IconSearch: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'inline-block', verticalAlign: 'middle' }}>
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const IconSliders: React.FC<{ size?: number; color?: string }> = ({ size = 14, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'inline-block', verticalAlign: 'middle' }}>
    <line x1="4" y1="21" x2="4" y2="14" />
    <line x1="4" y1="10" x2="4" y2="3" />
    <line x1="12" y1="21" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12" y2="3" />
    <line x1="20" y1="21" x2="20" y2="16" />
    <line x1="20" y1="12" x2="20" y2="3" />
    <line x1="1" y1="14" x2="7" y2="14" />
    <line x1="9" y1="8" x2="15" y2="8" />
    <line x1="17" y1="16" x2="23" y2="16" />
  </svg>
);

function fmtDate(d?: string) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return d;
  }
}

function fmtMoney(val?: number) {
  if (val === undefined || val === null) return '—';
  return '$' + Math.round(val).toLocaleString();
}

/* ── Canonical Vessel Class Catalog Card (matches feas-card pattern) ── */
function VesselClassCard({ vc }: { vc: VesselClassEntry }) {
  return (
    <div className="feas-card">
      <div className="feas-card-head">
        <span style={{ fontWeight: 600, color: 'var(--sail-100)' }}>{vc.class_name}</span>
        <span style={{ fontFamily: 'var(--f-mono)', fontSize: 11, color: 'var(--text-accent)', fontWeight: 600 }}>
          {Math.round(vc.typical_capacity_tonnes).toLocaleString()} MT
        </span>
      </div>
      <div className="feas-card-sub" style={{ display: 'flex', gap: 14, fontFamily: 'var(--f-mono)', fontSize: 11, marginTop: 4 }}>
        <span><span style={{ color: 'var(--sail-500)' }}>Draft:</span> {vc.draft_m}m</span>
        <span><span style={{ color: 'var(--sail-500)' }}>LOA:</span> {vc.loa_m}m</span>
        <span><span style={{ color: 'var(--sail-500)' }}>Beam:</span> {vc.beam_m}m</span>
      </div>
    </div>
  );
}

/* ── Live Tracked AIS Vessel Row ────────────────────────────── */
function LiveVesselRow({ v }: { v: LiveVesselStatus }) {
  return (
    <tr
      style={{
        borderBottom: '1px solid var(--sail-800)',
        transition: 'background 0.08s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-bg)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
    >
      <td style={{ padding: '9px 12px' }}>
        <div style={{ fontWeight: 600, color: 'var(--sail-100)' }}>{v.vessel_name || 'UNKNOWN'}</div>
        <div style={{ fontSize: 11, color: 'var(--sail-500)', fontFamily: 'var(--f-mono)' }}>
          IMO: {v.imo}
        </div>
      </td>
      <td style={{ padding: '9px 12px' }}>
        <div style={{ fontWeight: 500, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)', fontSize: 12 }}>
          {v.vessel_class || 'Unknown'}
        </div>
        <div style={{ fontSize: 11, color: 'var(--sail-400)' }}>
          {v.dwt ? `${Math.round(v.dwt).toLocaleString()} DWT` : '—'}
        </div>
      </td>
      <td style={{ padding: '9px 12px', fontFamily: 'var(--f-mono)', fontSize: 12, color: 'var(--sail-300)' }}>
        {v.current_lat?.toFixed(4) || '—'}, {v.current_lon?.toFixed(4) || '—'}
      </td>
      <td style={{ padding: '9px 12px', textAlign: 'right', fontFamily: 'var(--f-mono)' }}>
        <span style={{ fontWeight: 600, color: v.speed_knots > 0.5 ? 'var(--emerald)' : 'var(--warn)' }}>
          {v.speed_knots ? v.speed_knots.toFixed(1) : '0.0'}
        </span>{' '}
        <span style={{ fontSize: 10, color: 'var(--sail-500)' }}>kn</span>
      </td>
      <td style={{ padding: '9px 12px', textAlign: 'right', fontSize: 11, fontFamily: 'var(--f-mono)', color: 'var(--sail-400)' }}>
        {fmtDate(v.recorded_at)}
      </td>
      <td style={{ padding: '9px 12px', textAlign: 'center' }}>
        <span className="badge badge-emerald" style={{ fontSize: 10 }}>
          AIS Active
        </span>
      </td>
    </tr>
  );
}

/* ── Gantt Timeline Component (using design tokens, zero blue) ─ */
function ScheduleGantt({ schedule }: { schedule: VesselScheduleItem[] }) {
  const { minTime, totalDuration, vesselGroups } = useMemo(() => {
    if (!schedule || schedule.length === 0) {
      return { minTime: 0, totalDuration: 1, vesselGroups: {} };
    }
    const times = schedule.flatMap(s => [
      new Date(s.departure_date).getTime(),
      new Date(s.estimated_eta).getTime(),
    ]);
    const min = Math.min(...times);
    const max = Math.max(...times);
    const span = Math.max(max - min, 86400000); // at least 1 day

    const groups: Record<string, VesselScheduleItem[]> = {};
    schedule.forEach(item => {
      groups[item.vessel_name] = groups[item.vessel_name] || [];
      groups[item.vessel_name].push(item);
    });

    return { minTime: min, totalDuration: span, vesselGroups: groups };
  }, [schedule]);

  if (!schedule || schedule.length === 0) {
    return (
      <div style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--sail-500)', fontSize: 13 }}>
        No scheduled voyages available. Run optimization to generate vessel deployment timelines.
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '4px 0' }}>
      {/* Time header markers */}
      <div style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: 180, paddingRight: 16, fontSize: 10.5, fontFamily: 'var(--f-mono)', color: 'var(--sail-500)' }}>
        <span>{fmtDate(new Date(minTime).toISOString())}</span>
        <span>Mid-Period</span>
        <span>{fmtDate(new Date(minTime + totalDuration).toISOString())}</span>
      </div>

      {/* Rows per vessel */}
      {Object.entries(vesselGroups).map(([vesselName, items]) => (
        <div
          key={vesselName}
          style={{
            display: 'flex',
            alignItems: 'center',
            background: 'var(--sail-900)',
            borderRadius: 'var(--r)',
            padding: '8px 12px',
            border: '1px solid var(--sail-800)',
          }}
        >
          {/* Vessel Label */}
          <div style={{ width: 170, flexShrink: 0 }}>
            <div style={{ fontWeight: 600, color: 'var(--sail-100)', fontSize: 13 }}>
              {vesselName}
            </div>
            <div style={{ fontSize: 10.5, color: 'var(--sail-500)', fontFamily: 'var(--f-mono)' }}>
              IMO: {items[0]?.imo}
            </div>
          </div>

          {/* Timeline Bar Track (Grey card track) */}
          <div style={{ flex: 1, position: 'relative', height: 32, background: 'color-mix(in srgb, var(--sail-800) 60%, transparent)', borderRadius: 'var(--r)', overflow: 'hidden' }}>
            {/* Grid markers */}
            <div style={{ position: 'absolute', left: '25%', top: 0, bottom: 0, width: 1, background: 'var(--sail-800)' }} />
            <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--sail-800)' }} />
            <div style={{ position: 'absolute', left: '75%', top: 0, bottom: 0, width: 1, background: 'var(--sail-800)' }} />

            {/* Voyage Segments (Dark ink bar with yellow accent, zero blue) */}
            {items.map(item => {
              const start = new Date(item.departure_date).getTime();
              const end = new Date(item.estimated_eta).getTime();
              const leftPct = Math.max(0, Math.min(100, ((start - minTime) / totalDuration) * 100));
              const widthPct = Math.max(5, Math.min(100 - leftPct, ((end - start) / totalDuration) * 100));

              return (
                <div
                  key={item.contract_id}
                  title={`${item.contract_id}: ${item.origin} → ${item.destination} (${fmtDate(item.departure_date)} to ${fmtDate(item.estimated_eta)})`}
                  style={{
                    position: 'absolute',
                    left: `${leftPct}%`,
                    width: `${widthPct}%`,
                    top: 2,
                    bottom: 2,
                    background: 'var(--ink-700)',
                    border: '1px solid var(--ink-600)',
                    borderRadius: 3,
                    padding: '2px 8px',
                    color: '#FAFAFA',
                    fontSize: 11,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  <span style={{ fontSize: 10, fontFamily: 'var(--f-mono)', color: 'var(--accent)', fontWeight: 600 }}>
                    {item.contract_id}
                  </span>
                  <span style={{ fontSize: 10, color: '#e4e4e7', opacity: 0.9 }}>
                    {Math.round(item.contract_volume_mt / 1000)}k MT
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Main Fleet Schedule Page Component ─────────────────────── */
const FleetSchedulePage: React.FC = () => {
  const [fleetStatus, setFleetStatus] = useState<FleetStatusResponse | null>(null);
  const [fleetSchedule, setFleetSchedule] = useState<FleetScheduleResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [solving, setSolving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [decisionFilter, setDecisionFilter] = useState<'ALL' | 'SAIL' | 'KILL'>('ALL');
  const [rightViewMode, setRightViewMode] = useState<'matrix' | 'ais'>('matrix');

  // Solver Parameters
  const [maxSail, setMaxSail] = useState<number>(12);
  const [riskRatio, setRiskRatio] = useState<number>(0.60);

  const fetchAllData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, schedRes] = await Promise.all([
        getFleetStatus(),
        getFleetSchedule(),
      ]);
      if (statusRes.data) setFleetStatus(statusRes.data);
      if (schedRes.data) setFleetSchedule(schedRes.data);
      if (schedRes.error) setError(schedRes.error.message);
    } catch (err: any) {
      setError(err?.message || 'Failed to load fleet data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();
  }, []);

  const handleSolve = async () => {
    setSolving(true);
    setError(null);
    try {
      const res = await solveFleetSchedule({
        max_sail: maxSail,
        risk_ratio: riskRatio,
        time_limit: 20,
      });
      if (res.data) {
        setFleetSchedule(res.data);
      } else if (res.error) {
        setError(res.error.message);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to execute fleet optimization');
    } finally {
      setSolving(false);
    }
  };

  const filteredVessels = useMemo(() => {
    if (!fleetStatus?.vessels) return [];
    if (!searchQuery.trim()) return fleetStatus.vessels;
    const q = searchQuery.toLowerCase();
    return fleetStatus.vessels.filter(v =>
      (v.vessel_name || '').toLowerCase().includes(q) ||
      (v.vessel_class || '').toLowerCase().includes(q) ||
      String(v.imo).includes(q)
    );
  }, [fleetStatus, searchQuery]);

  const filteredDecisions = useMemo(() => {
    if (!fleetSchedule?.all_decisions) return [];
    return fleetSchedule.all_decisions.filter(d => {
      if (decisionFilter !== 'ALL' && d.decision !== decisionFilter) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        String(d.contract_id || '').toLowerCase().includes(q) ||
        String(d.vessel_name || '').toLowerCase().includes(q) ||
        String(d.origin || '').toLowerCase().includes(q) ||
        String(d.destination || '').toLowerCase().includes(q)
      );
    });
  }, [fleetSchedule, decisionFilter, searchQuery]);

  if (loading) {
    return (
      <div className="page-grid">
        <div className="col-12">
          <div className="panel" style={{ padding: '4rem', textAlign: 'center' }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--sail-100)', marginBottom: 8 }}>
              Connecting to Fleet & Portfolio Optimizer…
            </div>
            <div style={{ color: 'var(--sail-500)', fontFamily: 'var(--f-mono)', fontSize: 12 }}>
              Retrieving vessel classes, live AIS telemetry, and multi-contract schedule
            </div>
          </div>
        </div>
      </div>
    );
  }

  const summary = fleetSchedule?.summary;

  return (
    <div className="page-grid">
      {/* ══════════════════════════════════════════════════════════════ */}
      {/* ── TOP EXECUTIVE PORTFOLIO BANNER (col-12 panel-ink) ──────── */}
      {/* ── Matches WinningPlanBanner pattern from RecommendationPage ─ */}
      {/* ══════════════════════════════════════════════════════════════ */}
      {summary && (
        <section className="col-12">
          <div className="panel panel-ink">
            <div className="plan-header">
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span className="plan-label">Portfolio Allocation</span>
                  <ProvenanceBadge provenance="modeled" note="Global fleet conflict-graph MILP formulation." />
                </div>
                <div className="plan-title">
                  {summary.total_contracts}-Contract Global Fleet Slate
                </div>
                <p className="plan-subtitle">
                  {summary.sail_contracts} active bulk carriers assigned · {summary.kill_contracts} spot market exits · Zero-collision temporal schedule
                </p>
              </div>

              {/* Cost & Floor Metric (matching plan-cost pattern) */}
              <div style={{ flexShrink: 0, textAlign: 'right' }}>
                <div className="plan-cost">{fmtMoney(summary.expected_incremental_usd)}</div>
                <div className="plan-cost-label">expected incremental margin</div>
                <div className="plan-robustness mono" style={{ color: 'var(--accent)' }}>
                  worst-case floor {fmtMoney(summary.worst_incremental_usd)}
                </div>
              </div>
            </div>

            {/* Strategic Tags */}
            <div className="plan-tags">
              <span className="plan-tag">MILP Multi-Vessel Optimizer</span>
              <span className="plan-tag">Status: {summary.solver_status}</span>
              <span className="plan-tag">Total Voyage Cost: {fmtMoney(summary.total_voyage_cost_usd)}</span>
              <span className="plan-tag">Bunker Fuel: {fmtMoney(summary.bunker_cost_usd)}</span>
              <span className="plan-tag" style={{ color: 'var(--emerald)' }}>
                {summary.sail_contracts} SAIL Assigned
              </span>
              <span className="plan-tag warn">
                {summary.kill_contracts} KILL Exits
              </span>
            </div>
          </div>
        </section>
      )}

      {error && (
        <div className="col-12">
          <div className="error-bar">
            <span>✕</span>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════ */}
      {/* ── LEFT COLUMN: SOLVER PARAMETERS & VESSEL CATALOG (col-4) ── */}
      {/* ══════════════════════════════════════════════════════════════ */}
      <div className="col-4 col-space">
        {/* Panel 1: Fleet Optimizer Parameters (Zero black, matches WhatIfSliders) */}
        <section className="panel">
          <div className="panel-hd">
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <IconSliders size={15} color="var(--sail-500)" />
              <span className="panel-title">Portfolio Optimizer</span>
            </div>
            <ProvenanceBadge provenance="modeled" compact note="Fleet allocation conflict-graph MILP formulation." />
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Slider 1: Max Sail Contracts */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
                <label style={{ fontSize: 12, color: 'var(--sail-400)' }}>Max Sail Contracts</label>
                <span style={{ fontSize: 14, fontFamily: 'var(--f-mono)', fontWeight: 600, color: 'var(--text-accent)' }}>
                  {maxSail}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={16}
                step={1}
                value={maxSail}
                onChange={e => setMaxSail(parseInt(e.target.value) || 12)}
                style={{ width: '100%' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, fontFamily: 'var(--f-mono)', color: 'var(--sail-600)', marginTop: 1 }}>
                <span>1 Contract</span>
                <span>Max: 16</span>
              </div>
            </div>

            {/* Slider 2: Risk Ratio */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
                <label style={{ fontSize: 12, color: 'var(--sail-400)' }}>Risk Ratio Tolerance</label>
                <span style={{ fontSize: 14, fontFamily: 'var(--f-mono)', fontWeight: 600, color: 'var(--text-accent)' }}>
                  {riskRatio.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min={0.0}
                max={1.0}
                step={0.05}
                value={riskRatio}
                onChange={e => setRiskRatio(parseFloat(e.target.value) || 0.60)}
                style={{ width: '100%' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, fontFamily: 'var(--f-mono)', color: 'var(--sail-600)', marginTop: 1 }}>
                <span>0.00 (Risk Averse)</span>
                <span>1.00 (Aggressive)</span>
              </div>
            </div>

            {/* Re-solve Button (Standard btn-accent) */}
            <button
              className="btn btn-accent"
              onClick={handleSolve}
              disabled={solving}
              style={{ width: '100%', padding: '9px 14px' }}
            >
              {solving ? 'Solving MILP Formulation…' : 'Optimize Fleet Portfolio'}
            </button>

            <p className="infer">
              Solves multi-vessel temporal assignments maximizing expected incremental margin subject to downside risk tolerance.
            </p>
          </div>
        </section>

        {/* Panel 2: Canonical Vessel Class Catalog (Uses feas-card grey pattern) */}
        <section className="panel">
          <div className="panel-hd">
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <IconShip size={15} color="var(--sail-500)" />
              <span className="panel-title">Vessel Class Catalog</span>
            </div>
            <span className="panel-meta">{fleetStatus?.vessel_classes?.length || 0} classes</span>
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 420, overflowY: 'auto' }}>
            <div style={{ fontSize: 11, color: 'var(--sail-500)', marginBottom: 2 }}>
              Canonical vessel dimensions used in physical draft & LOA feasibility constraints.
            </div>
            {fleetStatus?.vessel_classes?.map(vc => (
              <VesselClassCard key={vc.class_name} vc={vc} />
            ))}
          </div>
        </section>
      </div>

      {/* ══════════════════════════════════════════════════════════════ */}
      {/* ── RIGHT COLUMN: TIMELINE, DECISIONS & TELEMETRY (col-8) ──── */}
      {/* ══════════════════════════════════════════════════════════════ */}
      <div className="col-8 col-space">
        {/* Panel 1: Fleet Deployment Timeline (Gantt) */}
        <section className="panel">
          <div className="panel-hd">
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <IconGantt size={15} color="var(--sail-500)" />
              <div>
                <span className="panel-title">Fleet Deployment Timeline (Gantt)</span>
                <span className="panel-meta" style={{ marginLeft: 8 }}>
                  Zero-collision temporal assignments across active bulk carriers
                </span>
              </div>
            </div>
            <ProvenanceBadge provenance="modeled" compact note="Derived from global fleet conflict-graph MILP solve." />
          </div>

          <div className="panel-body">
            <ScheduleGantt schedule={fleetSchedule?.vessel_schedule || []} />
          </div>
        </section>

        {/* Panel 2: Multi-Contract Decisions & Live Telemetry Workspace */}
        <section className="panel" style={{ overflow: 'hidden' }}>
          {/* Header with View Toggle & Search */}
          <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
            {/* View Switcher Tabs (Matches standard nav buttons) */}
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                className={`btn ${rightViewMode === 'matrix' ? 'btn-accent' : ''}`}
                onClick={() => setRightViewMode('matrix')}
                style={{
                  fontSize: 12,
                  padding: '5px 12px',
                  background: rightViewMode === 'matrix' ? 'var(--accent)' : 'var(--sail-800)',
                  color: rightViewMode === 'matrix' ? 'var(--accent-text)' : 'var(--sail-300)',
                  border: '1px solid var(--sail-700)',
                  borderRadius: 'var(--r)',
                }}
              >
                Contract Decision Matrix ({filteredDecisions.length})
              </button>

              <button
                className={`btn ${rightViewMode === 'ais' ? 'btn-accent' : ''}`}
                onClick={() => setRightViewMode('ais')}
                style={{
                  fontSize: 12,
                  padding: '5px 12px',
                  background: rightViewMode === 'ais' ? 'var(--accent)' : 'var(--sail-800)',
                  color: rightViewMode === 'ais' ? 'var(--accent-text)' : 'var(--sail-300)',
                  border: '1px solid var(--sail-700)',
                  borderRadius: 'var(--r)',
                }}
              >
                Live Tracked AIS Fleet ({filteredVessels.length})
              </button>
            </div>

            {/* Filter Buttons & Search Input */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {rightViewMode === 'matrix' && (
                <div style={{ display: 'flex', gap: 4 }}>
                  {(['ALL', 'SAIL', 'KILL'] as const).map(mode => {
                    const active = decisionFilter === mode;
                    return (
                      <button
                        key={mode}
                        onClick={() => setDecisionFilter(mode)}
                        style={{
                          padding: '3px 9px',
                          fontSize: 11,
                          borderRadius: 'var(--r)',
                          border: active ? '1px solid var(--accent-dim)' : '1px solid var(--sail-700)',
                          background: active ? 'var(--accent)' : 'var(--sail-800)',
                          color: active ? 'var(--accent-text)' : 'var(--sail-300)',
                          cursor: 'pointer',
                          fontWeight: active ? 600 : 400,
                          transition: 'all 0.08s ease',
                        }}
                      >
                        {mode}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Instant Search Bar */}
              <div style={{ position: 'relative' }}>
                <div style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--sail-500)' }}>
                  <IconSearch size={12} />
                </div>
                <input
                  type="text"
                  className="input-field"
                  placeholder={rightViewMode === 'matrix' ? 'Filter contracts, ports…' : 'Filter vessels, IMO…'}
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  style={{
                    padding: '4px 10px 4px 26px',
                    fontSize: 11.5,
                    width: 180,
                  }}
                />
              </div>
            </div>
          </div>

          {/* Table Content (Matches sc-table pattern from RecommendationPage) */}
          <div style={{ overflowX: 'auto' }}>
            {rightViewMode === 'matrix' ? (
              <table className="sc-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th style={{ padding: '8px 12px' }}>Contract</th>
                    <th style={{ padding: '8px 12px' }}>Route (Origin → Dest)</th>
                    <th style={{ padding: '8px 12px' }}>Assigned Vessel</th>
                    <th style={{ padding: '8px 12px' }}>Dep → ETA</th>
                    <th style={{ padding: '8px 12px' }}>Worst Gain</th>
                    <th style={{ padding: '8px 12px' }}>Expected Gain</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center' }}>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDecisions.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--sail-500)', fontSize: 13 }}>
                        No contracts match your filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredDecisions.map(d => {
                      const isSail = d.decision === 'SAIL';
                      return (
                        <tr
                          key={d.contract_id}
                          className={isSail ? 'winner' : ''}
                        >
                          <td style={{ padding: '9px 12px', fontWeight: 600, fontFamily: 'var(--f-mono)' }}>
                            {d.contract_id}
                          </td>
                          <td style={{ padding: '9px 12px' }}>
                            <div style={{ color: 'var(--sail-100)', fontWeight: 500 }}>{d.destination}</div>
                            <div style={{ fontSize: 11, color: 'var(--sail-500)' }}>from {d.origin}</div>
                          </td>
                          <td style={{ padding: '9px 12px' }}>
                            {isSail ? (
                              <div>
                                <span style={{ fontWeight: 600, color: 'var(--sail-100)' }}>{d.vessel_name}</span>
                                <span style={{ fontSize: 10.5, color: 'var(--sail-500)', fontFamily: 'var(--f-mono)', marginLeft: 6 }}>
                                  (IMO {d.imo})
                                </span>
                              </div>
                            ) : (
                              <span style={{ color: 'var(--sail-500)', fontStyle: 'italic', fontSize: 11.5 }}>— Walk Away —</span>
                            )}
                          </td>
                          <td style={{ padding: '9px 12px', fontFamily: 'var(--f-mono)', fontSize: 11, color: 'var(--sail-400)' }}>
                            {d.departure_date ? fmtDate(d.departure_date) : '—'} → {d.estimated_eta ? fmtDate(d.estimated_eta) : '—'}
                          </td>
                          <td style={{ padding: '9px 12px', fontFamily: 'var(--f-mono)', fontWeight: 600, color: isSail ? 'var(--emerald)' : 'var(--sail-400)' }}>
                            {fmtMoney(d.worst_incremental)}
                          </td>
                          <td style={{ padding: '9px 12px', fontFamily: 'var(--f-mono)', fontWeight: 600, color: 'var(--sail-100)' }}>
                            {fmtMoney(d.expected_incremental)}
                          </td>
                          <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                            <span
                              className={`badge ${isSail ? 'badge-emerald' : 'badge-warn'}`}
                              style={{ padding: '2px 7px', fontSize: 10, fontWeight: 600 }}
                            >
                              {d.decision}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            ) : (
              <table className="sc-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th style={{ padding: '8px 12px' }}>Vessel</th>
                    <th style={{ padding: '8px 12px' }}>Class / DWT</th>
                    <th style={{ padding: '8px 12px' }}>Location (Lat, Lon)</th>
                    <th style={{ padding: '8px 12px' }}>Speed</th>
                    <th style={{ padding: '8px 12px' }}>Last Ping</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredVessels.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--sail-500)', fontSize: 13 }}>
                        No tracked vessels match your search query.
                      </td>
                    </tr>
                  ) : (
                    filteredVessels.map(v => <LiveVesselRow key={v.imo} v={v} />)
                  )}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default FleetSchedulePage;
