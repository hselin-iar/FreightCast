import React, { useState } from 'react';
import type { RecommendationResponse, Strategy } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  result: RecommendationResponse;
}

function fmtM(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return '—';
  return `$${(v / 1_000_000).toFixed(2)}M`;
}

function fmtDelta(d: number): string {
  const sign = d > 0 ? '+' : '';
  const abs = Math.abs(d);
  if (abs >= 1_000_000) return `${sign}$${(d / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(d / 1_000).toFixed(0)}k`;
  return `${sign}$${d.toFixed(0)}`;
}

interface CostDiffCardProps {
  label: string;
  winner: number | null | undefined;
  challenger: number | null | undefined;
  note?: string;
}

function CostDiffCard({ label, winner, challenger, note }: CostDiffCardProps) {
  const w = winner ?? 0;
  const c = challenger ?? 0;
  const delta = c - w; // positive = challenger is more expensive (winner saved money)
  const isZero = Math.abs(delta) < 1;
  const maxVal = Math.max(Math.abs(w), Math.abs(c), 1);
  const wPct = Math.min(100, Math.max(6, Math.round((Math.abs(w) / maxVal) * 100)));
  const cPct = Math.min(100, Math.max(6, Math.round((Math.abs(c) / maxVal) * 100)));

  return (
    <div style={{
      padding: '10px 14px',
      background: 'color-mix(in srgb, var(--sail-900) 70%, transparent)',
      border: '1px solid var(--sail-800)',
      borderRadius: 'var(--r)',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      {/* Top Line: Category Label & Delta Badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--sail-100)' }}>
            {label}
          </span>
          {note && (
            <span style={{ fontSize: 10, color: 'var(--sail-400)' }}>
              ({note})
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontFamily: 'var(--f-mono)',
            fontSize: 12,
            fontWeight: 700,
            color: isZero ? 'var(--sail-400)' : delta > 0 ? 'var(--emerald)' : 'var(--warn)',
          }}>
            {isZero ? 'Equal ($0)' : fmtDelta(delta)}
          </span>
          {!isZero && (
            <span style={{
              fontSize: 10,
              fontWeight: 600,
              padding: '2px 6px',
              borderRadius: 3,
              background: delta > 0 ? 'rgba(16, 185, 129, 0.12)' : 'rgba(217, 119, 6, 0.12)',
              color: delta > 0 ? 'var(--emerald)' : 'var(--warn)',
              fontFamily: 'var(--f-mono)',
            }}>
              {delta > 0 ? 'Winner Cheaper' : 'Challenger Cheaper'}
            </span>
          )}
        </div>
      </div>

      {/* Comparison Metrics Stack */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14 }}>
        {/* Winner Plan */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11 }}>
            <span style={{ fontSize: 10.5, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 500 }}>
              Recommended Plan
            </span>
            <span style={{ fontFamily: 'var(--f-mono)', fontSize: 12.5, fontWeight: 700, color: 'var(--sail-100)' }}>
              {fmtM(w)}
            </span>
          </div>
          <div style={{ height: 4, background: 'var(--sail-800)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${wPct}%`,
              background: 'var(--sail-400)',
              borderRadius: 2,
            }} />
          </div>
        </div>

        {/* Challenger Alternative */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11 }}>
            <span style={{ fontSize: 10.5, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 500 }}>
              Challenger
            </span>
            <span style={{ fontFamily: 'var(--f-mono)', fontSize: 12.5, fontWeight: 600, color: 'var(--sail-200)' }}>
              {fmtM(c)}
            </span>
          </div>
          <div style={{ height: 4, background: 'var(--sail-800)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${cPct}%`,
              background: delta > 0 ? 'var(--warn)' : 'var(--emerald)',
              borderRadius: 2,
            }} />
          </div>
        </div>
      </div>
    </div>
  );
}

function StrategyCard({
  strategy,
  isWinner,
  isSelected,
  onClick,
}: {
  strategy: Strategy;
  isWinner: boolean;
  isSelected: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const spotCount   = strategy.voyages.filter(v => v.mode === 'spot').length;
  const lockedCount = strategy.voyages.filter(v => v.mode === 'locked').length;
  const modeMix = spotCount === strategy.voyages.length ? 'all spot'
    : lockedCount === strategy.voyages.length ? 'all locked'
    : `${spotCount}s / ${lockedCount}L`;

  let primaryLabel = strategy.voyages.length > 0 ? `${strategy.voyages.length} ${strategy.voyages[0].vessel_class} (${modeMix})` : strategy.commitment_mode;
  let hasTheme = false;
  if (strategy.provenance_note?.startsWith("Theme: ")) {
    const themeMatch = strategy.provenance_note.match(/^Theme:\s*([^(]+)/);
    if (themeMatch) {
      primaryLabel = themeMatch[1].trim();
      hasTheme = true;
    }
  }

  const isEco = strategy.cost_breakdown?.steaming_mode === 'eco';
  const isExpress = strategy.cost_breakdown?.steaming_mode === 'express';

  return (
    <div
      onClick={isWinner ? undefined : onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        padding: '12px 14px',
        borderRadius: 'var(--r)',
        border: isWinner
          ? '1px solid var(--sail-700)'
          : isSelected
          ? '1px solid var(--sail-600)'
          : '1px solid var(--sail-800)',
        background: isWinner
          ? 'color-mix(in srgb, var(--emerald) 6%, var(--sail-900))'
          : isSelected
          ? 'color-mix(in srgb, var(--sail-700) 25%, var(--sail-900))'
          : hovered
          ? 'color-mix(in srgb, var(--sail-800) 30%, transparent)'
          : 'var(--sail-900)',
        cursor: isWinner ? 'default' : 'pointer',
        transition: 'all 0.15s ease',
        borderLeft: isWinner
          ? '3px solid var(--emerald)'
          : isSelected
          ? '3px solid var(--sail-500)'
          : '3px solid transparent',
      }}
    >
      {/* Tier 1: Strategy Status, Title & Total Cost */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, flex: 1 }}>
          {isWinner ? (
            <span className="badge badge-emerald" style={{ fontSize: 9, fontWeight: 700, flexShrink: 0 }}>
              RECOMMENDED
            </span>
          ) : isSelected ? (
            <span className="badge" style={{ fontSize: 9, background: 'var(--sail-700)', color: 'var(--sail-100)', flexShrink: 0 }}>
              COMPARING
            </span>
          ) : null}
          <span style={{
            fontSize: 13,
            fontWeight: isWinner ? 700 : 500,
            color: 'var(--sail-100)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {primaryLabel}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <div style={{ textAlign: 'right' }}>
            <span style={{
              fontFamily: 'var(--f-mono)',
              fontSize: 13,
              fontWeight: 700,
              color: 'var(--sail-100)',
            }}>
              {fmtM(strategy.total_cost_worst_case)}
            </span>
            <span style={{ fontSize: 10, color: 'var(--sail-400)', marginLeft: 4 }}>
              worst-case
            </span>
          </div>

          {!isWinner && (
            <span style={{
              fontSize: 10,
              fontWeight: 500,
              padding: '2px 8px',
              borderRadius: 4,
              background: isSelected ? 'var(--sail-700)' : 'var(--sail-800)',
              color: isSelected ? 'var(--sail-100)' : 'var(--sail-300)',
              border: '1px solid var(--sail-700)',
              whiteSpace: 'nowrap',
            }}>
              {isSelected ? 'Viewing Diff ▼' : 'Compare ↗'}
            </span>
          )}
        </div>
      </div>

      {/* Tier 2: Sub-Attributes & Operational Context */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: 'var(--sail-400)', flexWrap: 'wrap', gap: 8, paddingTop: 2 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--sail-300)' }}>
            {strategy.voyage_count} {strategy.voyage_count === 1 ? 'voyage' : 'voyages'}
          </span>
          <span>·</span>
          <span className={`badge ${
            modeMix === 'all locked'
              ? 'badge-emerald'
              : modeMix === 'all spot'
              ? 'badge-primary'
              : 'badge-warn'
          }`} style={{ fontSize: 9, textTransform: 'uppercase' }}>
            {modeMix}
          </span>
          {isEco && (
            <span className="badge" style={{ fontSize: 9, background: 'rgba(16, 185, 129, 0.1)', color: 'var(--emerald)' }}>
              Eco Steaming
            </span>
          )}
          {isExpress && (
            <span className="badge" style={{ fontSize: 9, background: 'rgba(217, 119, 6, 0.1)', color: 'var(--warn)' }}>
              Fast Steaming
            </span>
          )}
        </div>

        <div style={{ fontSize: 11 }}>
          {strategy.infeasible_reason ? (
            <span style={{ color: 'var(--warn)', fontWeight: 600 }}>Infeasible: {strategy.infeasible_reason}</span>
          ) : strategy.voyages.some(v => v.lightening_required) ? (
            <span style={{ color: 'var(--warn)' }}>Lightening required</span>
          ) : hasTheme ? (
            <span style={{ color: 'var(--sail-400)' }}>{strategy.voyages.length > 0 ? `${strategy.voyages.length} ${strategy.voyages[0].vessel_class}` : ''}</span>
          ) : (
            <span style={{ color: 'var(--sail-400)' }}>{strategy.provenance_note?.slice(0, 36) ?? ''}</span>
          )}
        </div>
      </div>
    </div>
  );
}

const WhyNotComparator: React.FC<Props> = ({ result }) => {
  const winner    = result.recommendation;
  const others    = result.scenario_comparison;
  const [selected, setSelected] = useState<number | null>(null);

  const challenger = selected !== null ? others[selected] : null;
  const winnerBD   = winner.cost_breakdown;
  const challBD    = challenger?.cost_breakdown;

  return (
    <section className="panel" style={{ marginTop: 16, flex: 1, display: 'flex', flexDirection: 'column' }}>
      <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <span className="panel-title">Why-Not Comparison</span>
          <span className="panel-meta" style={{ marginLeft: 6 }}>
            {others.length} alternative strategies evaluated
          </span>
        </div>
        <ProvenanceBadge provenance="modeled" note="All scenarios evaluated with the same MILP cost formulation — not a heuristic post-sort." />
      </div>

      <div className="panel-body" style={{ overflowX: 'hidden', display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }}>
        <p className="infer" style={{ margin: 0 }}>
          Select any alternative below to inspect why the optimizer rejected it in favor of the recommended plan.
        </p>

        {/* Vertical Stack of Strategy Cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <StrategyCard
            strategy={winner}
            isWinner={true}
            isSelected={false}
            onClick={() => {}}
          />

          {others.map((s, i) => (
            <React.Fragment key={i}>
              <StrategyCard
                strategy={s}
                isWinner={false}
                isSelected={selected === i}
                onClick={() => setSelected(prev => prev === i ? null : i)}
              />

              {/* Inline Expanded Challenger Diff Drawer when this strategy is selected */}
              {selected === i && challenger && challBD && (
                <div style={{
                  margin: '4px 0 8px 0',
                  padding: 14,
                  background: 'var(--sail-950)',
                  border: '1px solid var(--sail-700)',
                  borderRadius: 'var(--r)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}>
                  {/* Diff Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 8, borderBottom: '1px solid var(--sail-800)', flexWrap: 'wrap', gap: 6 }}>
                    <div>
                      <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--sail-100)' }}>
                        Economic Comparison Breakdown
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--sail-400)', marginTop: 2 }}>
                        Recommended Winner vs <strong style={{ color: 'var(--sail-200)' }}>{challenger.commitment_mode}</strong>
                      </div>
                    </div>

                    <span className="badge badge-emerald" style={{ fontSize: 11, fontWeight: 700, fontFamily: 'var(--f-mono)' }}>
                      Winner Saves: {fmtDelta((challenger.total_cost_worst_case ?? 0) - (winner.total_cost_worst_case ?? 0))}
                    </span>
                  </div>

                  {/* Vertical Stack of Cost Bucket Cards */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <CostDiffCard
                      label="Ocean Freight"
                      winner={winnerBD.ocean_freight}
                      challenger={challBD.ocean_freight}
                    />

                    <CostDiffCard
                      label="Bunker Fuel"
                      winner={winnerBD.bunker}
                      challenger={challBD.bunker}
                    />

                    {((winnerBD.speed_bunker_savings_usd ?? 0) > 0 || (challBD.speed_bunker_savings_usd ?? 0) > 0) && (
                      <CostDiffCard
                        label="Speed Bunker Savings"
                        winner={-(winnerBD.speed_bunker_savings_usd ?? 0)}
                        challenger={-(challBD.speed_bunker_savings_usd ?? 0)}
                        note="Eco steaming fuel reduction"
                      />
                    )}

                    <CostDiffCard
                      label="Port & Handling"
                      winner={winnerBD.port_handling}
                      challenger={challBD.port_handling}
                    />

                    <CostDiffCard
                      label="Lightening / Extra"
                      winner={winnerBD.lightening_extra ?? 0}
                      challenger={challBD.lightening_extra ?? 0}
                    />

                    <CostDiffCard
                      label="Demurrage Risk"
                      winner={winnerBD.demurrage_exposure}
                      challenger={challBD.demurrage_exposure}
                    />

                    <CostDiffCard
                      label="Laycan Opportunity"
                      winner={winnerBD.opportunity_cost}
                      challenger={challBD.opportunity_cost}
                    />
                  </div>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </section>
  );
};

export default WhyNotComparator;
