/**
 * ExecutiveBriefExport.tsx — DOC3 Dashboard sellable layer / Build Step 12
 *
 * "Renders the current recommendation_response into a single exportable page
 *  (print-to-PDF or a formatted view) — pure formatting, DOC 2 §5.10 item 5."
 *
 * Renders a print-ready modal/overlay. Triggers browser's print dialog when
 * the user clicks "Export PDF". Uses a separate @print CSS class so the rest of
 * the UI is hidden during printing.
 */
import React, { useCallback, useRef, useState } from 'react';
import type { RecommendationResponse } from '../lib/types';

interface Props {
  result: RecommendationResponse;
  origin: string;
  dischargePorts: string[];
}

function fmtM(n: number): string { return '$' + (n / 1e6).toFixed(2) + 'M'; }
function fmtK(n: number): string {
  if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return '$' + Math.round(n / 1e3) + 'k';
  return '$' + Math.round(n);
}
function today(): string {
  return new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

const ExecutiveBriefExport: React.FC<Props> = ({ result, origin, dischargePorts }) => {
  const [open, setOpen] = useState(false);
  const printRef = useRef<HTMLDivElement>(null);

  const rec = result.recommendation;
  const bd  = rec.cost_breakdown;

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  const BriefContent = (
    <div ref={printRef} id="exec-brief-content" style={{
      fontFamily: 'var(--f-sans)',
      background: '#fff',
      color: '#111',
      padding: 32,
      maxWidth: 720,
      margin: '0 auto',
      fontSize: 13,
      lineHeight: 1.6,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '2px solid #0d9488', paddingBottom: 12, marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>SAIL Freight Intelligence</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>Executive Chartering Brief — {today()}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 11, color: '#64748b' }}>Worst-case total</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#0f172a', fontFamily: 'monospace' }}>
            {fmtM(rec.total_cost_worst_case)}
          </div>
        </div>
      </div>

      {/* Recommended Plan */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#0d9488', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6 }}>
          Recommended Plan
        </div>
        <div style={{ fontSize: 16, fontWeight: 600, color: '#0f172a' }}>
          {rec.voyage_count}-voyage {rec.commitment_mode} strategy
        </div>
        <div style={{ fontSize: 13, color: '#475569', marginTop: 4 }}>
          {rec.voyages.map((v, i) =>
            `Voyage ${i + 1}: ${v.vessel_class} → ${v.port} (${v.mode}, fix day ${v.fix_day})`
          ).join(' · ')}
        </div>
        <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[
            `Route: ${origin} → ${dischargePorts.join(' / ')}`,
            rec.solved_via === 'milp' ? 'MILP optimised' : 'Heuristic fallback',
            !rec.voyages.some(v => v.lightening_required) ? 'No lightening required' : 'Lightening required',
          ].map(t => (
            <span key={t} style={{ padding: '2px 8px', borderRadius: 4, background: '#f1f5f9', color: '#334155', fontSize: 11 }}>{t}</span>
          ))}
        </div>
      </div>

      {/* Cost Breakdown */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#0d9488', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 10 }}>
          Cost Breakdown (5-bucket)
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
              {['Bucket', 'Amount', '% of Total'].map(h => (
                <th key={h} style={{ textAlign: h === 'Bucket' ? 'left' : 'right', padding: '6px 0', fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody style={{ fontFamily: 'monospace' }}>
            {[
              ['Ocean freight',       bd.ocean_freight],
              ['Bunker',              bd.bunker],
              ['Port & handling',     bd.port_handling],
              ['Lightening / extra',  bd.lightening_extra ?? 0],
              ['Risk buffer',         bd.risk_buffer ?? 0],
            ].map(([label, val]) => (
              <tr key={label as string} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '6px 0', fontFamily: 'sans-serif', color: '#334155' }}>{label}</td>
                <td style={{ textAlign: 'right' }}>{fmtK(val as number)}</td>
                <td style={{ textAlign: 'right', color: '#64748b' }}>
                  {bd.total > 0 ? Math.round(((val as number) / bd.total) * 100) + '%' : '—'}
                </td>
              </tr>
            ))}
            <tr style={{ borderTop: '2px solid #e2e8f0', fontWeight: 700 }}>
              <td style={{ padding: '8px 0', fontFamily: 'sans-serif' }}>Total (worst-case)</td>
              <td style={{ textAlign: 'right' }}>{fmtM(rec.total_cost_worst_case)}</td>
              <td style={{ textAlign: 'right' }}>100%</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Scenario comparison */}
      {result.scenario_comparison.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#0d9488', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 10 }}>
            Scenario Comparison
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b' }}>
                {['Strategy','Voyages','Worst-case','Status'].map(h => (
                  <th key={h} style={{ textAlign: h === 'Strategy' ? 'left' : 'right', padding: '5px 0', fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody style={{ fontFamily: 'monospace' }}>
              {[rec, ...result.scenario_comparison].map((s, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', fontWeight: i === 0 ? 600 : undefined }}>
                  <td style={{ padding: '5px 0', fontFamily: 'sans-serif' }}>
                    {i === 0 ? '★ ' : ''}{s.commitment_mode}
                  </td>
                  <td style={{ textAlign: 'right' }}>{s.voyage_count}</td>
                  <td style={{ textAlign: 'right' }}>{fmtM(s.total_cost_worst_case)}</td>
                  <td style={{ textAlign: 'right', fontFamily: 'sans-serif', color: s.infeasible_reason ? '#ef4444' : '#10b981', fontSize: 10 }}>
                    {s.infeasible_reason ? 'Infeasible' : i === 0 ? 'Selected' : 'Considered'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer */}
      <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: 12, fontSize: 10, color: '#94a3b8', display: 'flex', justifyContent: 'space-between' }}>
        <span>Generated by SAIL Freight Intelligence — {today()}</span>
        <span>MILP-optimised · Provenance: {rec.provenance}</span>
      </div>
    </div>
  );

  return (
    <>
      {/* Trigger button — sits in the nav bar via prop or inline */}
      <button
        className="btn btn-sm"
        id="btn-export-brief"
        onClick={() => setOpen(true)}
        style={{ border: '1px solid var(--sail-700)', background: 'transparent', color: 'var(--sail-300)' }}
      >
        ↓ Export Brief
      </button>

      {/* Modal overlay */}
      {open && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(2,6,23,0.85)',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center',
          overflowY: 'auto',
          padding: '32px 16px',
        }}>
          {/* Modal controls */}
          <div style={{
            width: '100%', maxWidth: 720,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: 12,
          }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--sail-200)' }}>
              Executive Brief Preview
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-accent btn-sm" onClick={handlePrint} id="btn-print-brief">
                🖨 Print / Save PDF
              </button>
              <button
                className="btn btn-sm"
                onClick={() => setOpen(false)}
                style={{ border: '1px solid var(--sail-700)', background: 'transparent', color: 'var(--sail-300)' }}
              >
                ✕ Close
              </button>
            </div>
          </div>

          {/* Brief content */}
          <div style={{ width: '100%', maxWidth: 720, borderRadius: 8, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,0.6)' }}>
            {BriefContent}
          </div>
        </div>
      )}
    </>
  );
};

export default ExecutiveBriefExport;
