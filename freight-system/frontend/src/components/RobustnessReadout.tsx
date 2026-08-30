/**
 * RobustnessReadout.tsx — DOC3 Dashboard sellable layer / Build Step 12
 *
 * Computes and renders the robustness score and a visual gauge.
 * Formula: 1 − (worst_case − best_case) / best_case, clamped [0,1].
 * "Pure re-render of already-fetched data — no new solve." (DOC4 Step 12)
 */
import React from 'react';
import type { RecommendationResponse } from '../lib/types';

interface Props {
  result: RecommendationResponse;
}

function computeRobustness(result: RecommendationResponse): number {
  const all = [result.recommendation, ...result.scenario_comparison]
    .filter(s => !s.infeasible_reason);
  if (all.length < 2) return 1;
  const costs = all.map(s => s.total_cost_worst_case);
  const worst = Math.max(...costs);
  const best  = Math.min(...costs);
  if (best <= 0) return 1;
  return Math.max(0, Math.min(1, 1 - (worst - best) / best));
}

function robustnessLabel(r: number): { label: string; color: string } {
  if (r >= 0.90) return { label: 'Strong',   color: 'var(--emerald-4)' };
  if (r >= 0.75) return { label: 'Moderate', color: 'var(--text-accent)' };
  if (r >= 0.60) return { label: 'Weak',     color: 'var(--warn)' };
  return              { label: 'Poor',      color: '#ef4444' };
}

/** Arc gauge — SVG semicircle filled proportionally */
function RobustnessGauge({ score }: { score: number }) {
  const r = 38, cx = 50, cy = 54;
  const startAngle = -180; // left
  const sweepAngle = 180 * score;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const x1 = cx + r * Math.cos(toRad(startAngle));
  const y1 = cy + r * Math.sin(toRad(startAngle));
  const x2 = cx + r * Math.cos(toRad(startAngle + sweepAngle));
  const y2 = cy + r * Math.sin(toRad(startAngle + sweepAngle));
  const largeArc = sweepAngle > 180 ? 1 : 0;

  const { color } = robustnessLabel(score);

  return (
    <svg width={100} height={58} viewBox="0 0 100 58">
      {/* Track */}
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="var(--sail-800)" strokeWidth={6} strokeLinecap="round" />
      {/* Fill */}
      {score > 0.01 && (
        <path d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
          fill="none" stroke={color} strokeWidth={6} strokeLinecap="round" />
      )}
      {/* Score label */}
      <text x={cx} y={cy - 2} textAnchor="middle"
        fontSize={14} fontWeight={700} fill={color} fontFamily="var(--f-mono)">
        {score.toFixed(2)}
      </text>
    </svg>
  );
}

const RobustnessReadout: React.FC<Props> = ({ result }) => {
  const score = computeRobustness(result);
  const { label, color } = robustnessLabel(score);
  const rec = result.recommendation;

  const allCosts = [rec, ...result.scenario_comparison]
    .filter(s => !s.infeasible_reason)
    .map(s => s.total_cost_worst_case);
  const best  = allCosts.length ? Math.min(...allCosts) : 0;
  const worst = allCosts.length ? Math.max(...allCosts) : 0;

  return (
    <section className="panel" id="robustness-readout">
      <div className="panel-hd">
        <span className="panel-title">Robustness</span>
        <span style={{ fontSize: 11, fontFamily: 'var(--f-mono)', fontWeight: 600, color }}>
          {label}
        </span>
      </div>
      <div className="panel-body">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ flexShrink: 0 }}>
            <RobustnessGauge score={score} />
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5 }}>
              <span style={{ color: 'var(--sail-400)' }}>Best case</span>
              <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--emerald-4)' }}>
                ${(best / 1e6).toFixed(2)}M
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5 }}>
              <span style={{ color: 'var(--sail-400)' }}>Worst case</span>
              <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--warn)' }}>
                ${(worst / 1e6).toFixed(2)}M
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5 }}>
              <span style={{ color: 'var(--sail-400)' }}>Max regret</span>
              <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--sail-300)' }}>
                ${((worst - best) / 1e3).toFixed(0)}k
              </span>
            </div>
            {rec.solved_via && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5 }}>
                <span style={{ color: 'var(--sail-400)' }}>Solver</span>
                <span style={{ fontFamily: 'var(--f-mono)', color: 'var(--sail-300)' }}>
                  {rec.solved_via === 'hybrid_fallback' ? 'hybrid' : rec.solved_via}
                </span>
              </div>
            )}
          </div>
        </div>
        <p className="infer">
          Score = 1 − (worst − best) / best across all feasible strategies.
          0.91+ means the plan does not collapse under the pessimistic path.
        </p>
      </div>
    </section>
  );
};

export default RobustnessReadout;
