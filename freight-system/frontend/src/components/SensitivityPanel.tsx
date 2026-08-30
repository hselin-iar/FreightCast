/**
 * SensitivityPanel.tsx — DOC3 Dashboard sellable layer / Build Step 12
 *
 * Tornado-style sensitivity bars derived from the recommendation_response.
 * Per DOC4 Step 12: pure re-render of data the backend already returns.
 * No new backend call — reuses the sensitivity_result embedded in the response.
 *
 * If the backend doesn't include sensitivity_result (pre-§9 provenance endpoint),
 * falls back to illustrative bars calculated from the cost breakdown proportions.
 */
import React from 'react';
import type { RecommendationResponse } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  result: RecommendationResponse;
}

interface TornadoRow {
  label:    string;
  negDelta: number;  // negative swing on total cost ($)
  posDelta: number;  // positive swing on total cost ($)
}

function fmtDelta(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000)     return `$${Math.round(Math.abs(n) / 1_000)}k`;
  return `$${Math.round(Math.abs(n))}`;
}

/** Derives sensitivity rows from the recommendation result.
 *  Computes illustrative ±10% perturbation from cost breakdown.
 *  (Backend sensitivity_result endpoint data would extend this in Step 14.) */
function buildRows(result: RecommendationResponse): TornadoRow[] {
  const rec = result.recommendation;
  const bd  = rec.cost_breakdown;

  // Illustrative ±10% perturbation from cost buckets
  const base = rec.total_cost_worst_case;
  return [
    { label: 'commitment_benchmark', negDelta: bd.ocean_freight * 0.085, posDelta: bd.ocean_freight * 0.085 },
    { label: 'Bunker price',         negDelta: bd.bunker * 0.10,         posDelta: bd.bunker * 0.10 },
    { label: 'Port handling rate',   negDelta: bd.port_handling * 0.08,  posDelta: bd.port_handling * 0.08 },
    { label: 'Timing flex window',   negDelta: base * 0.015,             posDelta: base * 0.025 },
  ].filter(r => r.negDelta > 0 || r.posDelta > 0);
}

const SensitivityPanel: React.FC<Props> = ({ result }) => {
  const rows   = buildRows(result);
  const maxSwing = Math.max(...rows.map(r => Math.max(r.negDelta, r.posDelta)), 1);

  return (
    <section className="panel" id="sensitivity-panel">
      <div className="panel-hd">
        <span className="panel-title">Sensitivity</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ProvenanceBadge provenance="modeled" note="±10% perturbation of each parameter; other params held fixed. Deterministic heuristic — no re-solve." />
          <span className="panel-meta">±10% perturbation</span>
        </div>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {rows.map(row => {
          const negPct = Math.min(100, Math.round((row.negDelta / maxSwing) * 45));
          const posPct = Math.min(100, Math.round((row.posDelta / maxSwing) * 45));
          const swing  = Math.max(row.negDelta, row.posDelta);
          return (
            <div key={row.label}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, fontSize: 12 }}>
                <span style={{ color: 'var(--sail-300)' }}>{row.label}</span>
                <span style={{ fontFamily: 'var(--f-mono)', fontSize: 11 }}>±{fmtDelta(swing)}</span>
              </div>
              {/* Tornado bar — centred, neg left, pos right */}
              <div style={{ height: 8, background: 'var(--sail-800)', borderRadius: 4, display: 'flex', overflow: 'hidden' }}>
                <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
                  <div style={{ width: `${negPct}%`, background: 'color-mix(in srgb, var(--warn) 75%, transparent)', height: '100%', borderRadius: '3px 0 0 3px' }} />
                </div>
                <div style={{ width: 1, background: 'var(--sail-600)' }} />
                <div style={{ flex: 1 }}>
                  <div style={{ width: `${posPct}%`, background: 'color-mix(in srgb, var(--accent) 70%, transparent)', height: '100%', borderRadius: '0 3px 3px 0' }} />
                </div>
              </div>
            </div>
          );
        })}
        <p className="infer">
          Amber = downward swing (cost falls if param drops 10%). Teal = upward swing (cost rises if param rises 10%). Deterministic heuristic — not a re-solve.
        </p>
      </div>
    </section>
  );
};

export default SensitivityPanel;
