/**
 * WhyNotComparator.tsx — DOC3 Dashboard sellable layer / Build Step 12
 *
 * "Clicking a non-winning scenario_comparison[] entry opens a side-by-side cost
 *  breakdown vs. the winner — pure re-render of already-fetched data, no new call."
 *  (DOC3)
 *
 * Renders an expandable row in the scenario table that shows a diff-style cost
 * comparison between the selected strategy and the winner.
 */
import React, { useState } from 'react';
import type { RecommendationResponse, Strategy } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  result: RecommendationResponse;
}

function fmtM(n: number) { return '$' + (n / 1e6).toFixed(2) + 'M'; }
function fmtK(n: number) {
  if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
  if (Math.abs(n) >= 1e3) return '$' + Math.round(n / 1e3) + 'k';
  return '$' + Math.round(n);
}

interface CostDiffRowProps {
  label: string;
  winner: number;
  challenger: number;
}

function CostDiffRow({ label, winner, challenger }: CostDiffRowProps) {
  const diff = challenger - winner;
  const sign = diff > 0 ? '+' : '';
  const color = diff > 0 ? 'var(--warn)' : diff < 0 ? 'var(--emerald-4)' : 'var(--sail-400)';
  return (
    <tr style={{ borderBottom: '1px solid color-mix(in srgb, var(--sail-800) 60%, transparent)' }}>
      <td style={{ padding: '7px 0', fontSize: 12, color: 'var(--sail-400)' }}>{label}</td>
      <td style={{ textAlign: 'right', fontFamily: 'var(--f-mono)', fontSize: 12, color: 'var(--text-accent)' }}>
        {fmtK(winner)}
      </td>
      <td style={{ textAlign: 'right', fontFamily: 'var(--f-mono)', fontSize: 12 }}>
        {fmtK(challenger)}
      </td>
      <td style={{ textAlign: 'right', fontFamily: 'var(--f-mono)', fontSize: 12, color, paddingLeft: 8 }}>
        {diff !== 0 ? `${sign}${fmtK(diff)}` : '—'}
      </td>
    </tr>
  );
}

function StrategyRow({ strategy, isWinner, isSelected, onClick }: {
  strategy: Strategy;
  isWinner: boolean;
  isSelected: boolean;
  onClick: () => void;
}) {
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

  return (
    <tr
      onClick={onClick}
      style={{
        borderBottom: '1px solid color-mix(in srgb, var(--sail-800) 60%, transparent)',
        cursor: isWinner ? 'default' : 'pointer',
        background: isWinner ? 'color-mix(in srgb, var(--accent) 5%, transparent)' : isSelected ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : undefined,
        transition: 'background 0.1s',
      }}
    >
      <td style={{ padding: '9px 12px 9px 0', color: isWinner ? 'var(--text-accent)' : 'var(--sail-200)', fontWeight: isWinner ? 600 : undefined }}>
        {isWinner ? '★ ' : isSelected ? '▶ ' : ''}
        {primaryLabel}
        {isWinner ? ' (selected)' : ''}
      </td>
      <td style={{ padding: '9px 12px', textAlign: 'center', fontFamily: 'var(--f-mono)', fontSize: 12 }}>{strategy.voyage_count}</td>
      <td style={{ padding: '9px 12px', textAlign: 'center', fontFamily: 'var(--f-mono)', fontSize: 12, whiteSpace: 'nowrap' }}>{modeMix}</td>
      <td style={{ padding: '9px 12px', textAlign: 'right', fontFamily: 'var(--f-mono)', fontSize: 12, color: 'var(--sail-100)' }}>
        {fmtM(strategy.total_cost_worst_case)}
      </td>
      <td style={{ padding: '9px 0 9px 12px', fontSize: 11, color: strategy.infeasible_reason ? 'var(--warn)' : 'var(--sail-400)', fontFamily: 'var(--f-sans)' }}>
        {strategy.infeasible_reason
          ? `Infeasible: ${strategy.infeasible_reason}`
          : strategy.voyages.some(v => v.lightening_required) ? 'Lightening req.' : 
             hasTheme ? strategy.voyages.length > 0 ? `${strategy.voyages.length} ${strategy.voyages[0].vessel_class} (${modeMix})` : ''
             : strategy.provenance_note?.slice(0, 36) ?? ''}
      </td>
    </tr>
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
      <div className="panel-hd">
        <span className="panel-title">Ranked Alternatives</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ProvenanceBadge provenance="modeled" note="Pure re-render of scenario_comparison[] from /recommendation — no re-solve." />
          <span className="panel-meta">click row to compare</span>
        </div>
      </div>
      <div className="panel-body" style={{ overflowX: 'auto', display: 'flex', flexDirection: 'column', flex: 1 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ color: 'var(--sail-500)', borderBottom: '1px solid var(--sail-800)' }}>
              <th style={{ padding: '8px 12px 8px 0', fontWeight: 500, textAlign: 'left' }}>Strategy</th>
              <th style={{ padding: '8px 12px', fontWeight: 500, textAlign: 'center' }}>Voyages</th>
              <th style={{ padding: '8px 12px', fontWeight: 500, textAlign: 'center' }}>Mode</th>
              <th style={{ padding: '8px 12px', fontWeight: 500, textAlign: 'right' }}>Worst-case</th>
              <th style={{ padding: '8px 0 8px 12px', fontWeight: 500, textAlign: 'left' }}>Notes</th>
            </tr>
          </thead>
          <tbody className="mono">
            <StrategyRow strategy={winner} isWinner onClick={() => {}} isSelected={false} />
            {others.map((s, i) => (
              <StrategyRow key={i} strategy={s} isWinner={false}
                isSelected={selected === i}
                onClick={() => setSelected(prev => prev === i ? null : i)}
              />
            ))}
          </tbody>
        </table>

        {/* Expanded comparison panel */}
        {challenger && challBD && (
          <div style={{
            marginTop: 12, padding: 12,
            background: 'color-mix(in srgb, var(--accent) 4%, transparent)',
            border: '1px solid color-mix(in srgb, var(--accent) 18%, transparent)',
            borderRadius: 6,
          }}>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--sail-300)', marginBottom: 8 }}>
              Why <em style={{ color: 'var(--text-accent)' }}>{winner.commitment_mode} (winner)</em> beats{' '}
              <em>{challenger.commitment_mode}</em> — same cost engine, not a re-solve
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ color: 'var(--sail-500)', borderBottom: '1px solid var(--sail-800)' }}>
                  <th style={{ textAlign: 'left', padding: '6px 0', fontWeight: 500 }}>Bucket</th>
                  <th style={{ textAlign: 'right', padding: '6px 0', fontWeight: 500, color: 'var(--text-accent)' }}>Winner</th>
                  <th style={{ textAlign: 'right', padding: '6px 0', fontWeight: 500 }}>Challenger</th>
                  <th style={{ textAlign: 'right', padding: '6px 0', fontWeight: 500, paddingLeft: 8 }}>Δ</th>
                </tr>
              </thead>
              <tbody>
                <CostDiffRow label="Ocean freight"     winner={winnerBD.ocean_freight}        challenger={challBD.ocean_freight} />
                <CostDiffRow label="Bunker"            winner={winnerBD.bunker}               challenger={challBD.bunker} />
                <CostDiffRow label="Port & handling"   winner={winnerBD.port_handling}        challenger={challBD.port_handling} />
                <CostDiffRow label="Lightening / extra" winner={winnerBD.lightening_extra ?? 0} challenger={challBD.lightening_extra ?? 0} />
                <CostDiffRow label="Risk buffer"       winner={winnerBD.risk_buffer ?? 0}     challenger={challBD.risk_buffer ?? 0} />
                <CostDiffRow label="TOTAL (worst-case)" winner={winner.total_cost_worst_case} challenger={challenger.total_cost_worst_case} />
              </tbody>
            </table>
            {challenger.infeasible_reason && (
              <div style={{ marginTop: 8, fontSize: 11, color: 'var(--warn)', background: 'color-mix(in srgb, var(--warn) 5%, transparent)', padding: '6px 8px', borderRadius: 4, border: '1px solid color-mix(in srgb, var(--warn) 20%, transparent)' }}>
                ⚠ Infeasible: {challenger.infeasible_reason}
              </div>
            )}
          </div>
        )}

        {!selected && others.length > 0 && (
          <p className="infer" style={{ marginTop: 'auto' }}>Click a non-winning row to see a cost breakdown diff against the winner.</p>
        )}
      </div>
    </section>
  );
};

export default WhyNotComparator;
