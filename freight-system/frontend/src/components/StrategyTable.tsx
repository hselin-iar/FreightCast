/**
 * StrategyTable.tsx
 * DOC3: StrategyTable — renders ranked Strategy[] with 5-bucket cost breakdown,
 *       provenance badges, voyage detail, and mode chips.
 *       "pure re-render of already-fetched data — no cost math in this component."
 */
import React, { useState } from 'react';
import type { Strategy } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  strategies: Strategy[];
}

function fmtUSD(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}


function CostBar({ bd }: { bd: Strategy['cost_breakdown'] }) {
  const total = bd.total || 1;
  return (
    <div className="cost-bar" title="Freight / Bunker / Port / Other">
      <div className="cost-bar-seg freight" style={{ width: `${(bd.ocean_freight / total) * 100}%` }} />
      <div className="cost-bar-seg bunker"  style={{ width: `${(bd.bunker / total) * 100}%` }} />
      <div className="cost-bar-seg port"    style={{ width: `${(bd.port_handling / total) * 100}%` }} />
      <div className="cost-bar-seg light"   style={{ width: `${((bd.lightening_extra ?? 0) / total) * 100}%` }} />
    </div>
  );
}

function ModeChip({ mode }: { mode: string }) {
  return <span className={`mode-chip ${mode}`}>{mode}</span>;
}

function VoyageExpandedRow({ strat }: { strat: Strategy }) {
  return (
    <tr>
      <td colSpan={7} style={{ padding: '0 14px 14px', background: 'var(--bg-void)' }}>
        <div style={{ borderTop: '1px solid var(--border-dim)', paddingTop: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.6px', textTransform: 'uppercase', color: 'var(--text-faint)', marginBottom: 8 }}>
            Voyage breakdown
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {strat.voyages.map((v, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 12,
                background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)',
                padding: '8px 12px', fontSize: 12
              }}>
                <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--text-faint)', minWidth: 16 }}>
                  V{i + 1}
                </span>
                <span style={{ color: 'var(--text-hi)', minWidth: 100 }}>{v.port}</span>
                <span style={{ color: 'var(--text-dim)', minWidth: 90 }}>{v.vessel_class}</span>
                <ModeChip mode={v.mode} />
                <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--text-dim)', fontSize: 11 }}>
                  τ={v.fix_day}d
                </span>
                <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--text-amber)' }}>
                  {fmtUSD(v.cost_by_scenario.base)}
                  <span style={{ color: 'var(--text-faint)', fontSize: 10 }}> base</span>
                </span>
                {v.lightening_required && (
                  <span style={{
                    fontSize: 10, padding: '1px 6px', borderRadius: 3,
                    background: 'var(--red-bg)', border: '1px solid color-mix(in srgb, var(--error, #ef4444) 20%, transparent)', color: 'var(--red)'
                  }}>
                    lightening → {v.lightening_port ?? '?'}
                  </span>
                )}
                {v.tidal_window_note && (
                  <span style={{ fontSize: 10, color: 'var(--text-dim)', fontStyle: 'italic' }}>
                    {v.tidal_window_note}
                  </span>
                )}
              </div>
            ))}
          </div>
          {/* Scenario costs */}
          <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
            {(['optimistic', 'base', 'pessimistic'] as const).map(sc => {
              const val = strat.voyages.reduce((sum, v) => sum + (v.cost_by_scenario[sc] ?? 0), 0);
              return (
                <div key={sc} style={{
                  flex: 1, background: 'var(--bg-elevated)', borderRadius: 'var(--r-sm)',
                  padding: '8px 12px', textAlign: 'center'
                }}>
                  <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-faint)', marginBottom: 3 }}>
                    {sc}
                  </div>
                  <div style={{ fontFamily: 'var(--f-mono)', fontSize: 14, fontWeight: 600, color: sc === 'pessimistic' ? 'var(--red)' : sc === 'optimistic' ? 'var(--green)' : 'var(--text-hi)' }}>
                    {fmtUSD(val)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </td>
    </tr>
  );
}

const StrategyTable: React.FC<Props> = ({ strategies }) => {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!strategies.length) return null;

  const toggle = (i: number) => setExpanded(prev => prev === i ? null : i);

  return (
    <div className="strat-table-wrap">
      <table className="strat-table">
        <thead>
          <tr>
            <th style={{ width: 32 }}>#</th>
            <th>Strategy</th>
            <th>Worst-case cost</th>
            <th>Breakdown</th>
            <th>Solver</th>
            <th>Provenance</th>
            <th style={{ width: 32 }} />
          </tr>
        </thead>
        <tbody>
          {strategies.map((s, i) => {
            const isBest      = i === 0;
            const isInfeasible = !!s.infeasible_reason;
            const isExpanded  = expanded === i;

            return (
              <React.Fragment key={i}>
                <tr
                  className={isBest ? 'winner-row' : ''}
                  style={{ opacity: isInfeasible ? 0.4 : 1, cursor: 'pointer' }}
                  onClick={() => !isInfeasible && toggle(i)}
                >
                  {/* Rank */}
                  <td>
                    <span className={`rank-cell ${isBest ? 'best' : ''}`}>
                      {isBest ? '★' : i + 1}
                    </span>
                  </td>

                  {/* Strategy label */}
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <ModeChip mode={s.commitment_mode} />
                      <span style={{ fontSize: 12, color: 'var(--text-body)' }}>
                        {s.voyage_count}v
                        {s.contains_high_uncertainty_voyage && (
                          <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--amber)' }} title="Contains high-uncertainty voyage">⚠</span>
                        )}
                      </span>
                    </div>
                    {isInfeasible && (
                      <div style={{ fontSize: 10, color: 'var(--red)', marginTop: 3 }}>
                        {s.infeasible_reason}
                      </div>
                    )}
                  </td>

                  {/* Cost */}
                  <td>
                    <div className="cost-num">
                      <span className="cost-usd">$</span>
                      {(s.total_cost_worst_case / 1_000_000).toFixed(3)}M
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 1 }}>
                      {fmtUSD(s.cost_breakdown.bunker)} bunker · {fmtUSD(s.cost_breakdown.ocean_freight)} freight
                    </div>
                  </td>

                  {/* Stacked bar */}
                  <td>
                    <CostBar bd={s.cost_breakdown} />
                    <div style={{ display: 'flex', gap: 8, marginTop: 5, fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--f-mono)' }}>
                      <span style={{ color: 'var(--indigo-hi)' }}>■</span> freight
                      <span style={{ color: 'var(--amber)' }}>■</span> bunker
                      <span style={{ color: '#a78bfa' }}>■</span> port
                    </div>
                  </td>

                  {/* Solved via */}
                  <td>
                    <span style={{
                      fontSize: 9, fontFamily: 'var(--f-mono)', fontWeight: 600,
                      padding: '2px 6px', borderRadius: 3,
                      background: s.solved_via === 'milp' ? 'var(--green-bg)' : 'var(--amber-bg)',
                      border: `1px solid ${s.solved_via === 'milp' ? 'rgba(16,185,129,0.2)' : 'var(--amber-glow)'}`,
                      color: s.solved_via === 'milp' ? 'var(--green)' : 'var(--amber)',
                      textTransform: 'uppercase'
                    }}>
                      {s.solved_via === 'milp' ? 'MILP' : 'Fallback'}
                    </span>
                  </td>

                  {/* Provenance */}
                  <td>
                    <ProvenanceBadge provenance={s.provenance} note={s.provenance_note} />
                  </td>

                  {/* Expand toggle */}
                  <td style={{ textAlign: 'center', color: 'var(--text-faint)', fontSize: 12 }}>
                    {!isInfeasible && (isExpanded ? '▲' : '▼')}
                  </td>
                </tr>

                {isExpanded && !isInfeasible && (
                  <VoyageExpandedRow strat={s} />
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default StrategyTable;
