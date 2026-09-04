import React, { useState } from 'react';
import type { SituationalScenario } from '../lib/types';
import CitationTextParser from './CitationTextParser';
import MathFormula from './MathFormula';
import { highlightDataTerms } from '../lib/termHighlighter';

interface Props {
  scenarios: SituationalScenario[];
}

export const SituationalProofLab: React.FC<Props> = ({ scenarios }) => {
  const [selectedId, setSelectedId] = useState<string>(scenarios[0]?.id ?? '');
  const [expandedCitations, setExpandedCitations] = useState<Record<string, boolean>>({});

  const activeScenario = scenarios.find((s) => s.id === selectedId) ?? scenarios[0];

  if (!activeScenario) {
    return (
      <div className="col-12">
        <div className="panel">
          <div className="panel-body">No situational scenarios available.</div>
        </div>
      </div>
    );
  }

  const citationsList = Object.values(activeScenario.citations);
  const allExpanded = citationsList.length > 0 && citationsList.every((c) => expandedCitations[c.id]);

  const toggleCitation = (id: string) => {
    setExpandedCitations((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleExpandAll = () => {
    const nextState = !allExpanded;
    const update: Record<string, boolean> = {};
    citationsList.forEach((c) => {
      update[c.id] = nextState;
    });
    setExpandedCitations(update);
  };

  return (
    <>
      {/* ── LEFT COLUMN (col-4): Scenario Selector & Grounded Citations ── */}
      <div className="col-4 col-space">
        {/* Scenario Selector Panel */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Situational Stress-Tests</span>
            <span className="panel-meta">{scenarios.length} scenarios</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {scenarios.map((sc) => {
              const isSelected = sc.id === activeScenario.id;
              return (
                <button
                  key={sc.id}
                  onClick={() => {
                    setSelectedId(sc.id);
                    setExpandedCitations({});
                  }}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    padding: '10px 12px',
                    borderRadius: 6,
                    border: isSelected ? '1.5px solid var(--accent-dim)' : '1px solid var(--sail-800)',
                    borderLeft: isSelected ? '4px solid var(--accent-dim)' : '4px solid transparent',
                    backgroundColor: isSelected ? '#ffffff' : 'var(--sail-950)',
                    boxShadow: isSelected ? '0 2px 6px rgba(0, 0, 0, 0.06)' : 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <span
                    style={{
                      fontSize: 9.5,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      color: isSelected ? 'var(--text-accent)' : 'var(--sail-500)',
                      fontWeight: 700,
                      marginBottom: 2,
                    }}
                  >
                    {sc.category}
                  </span>
                  <span style={{ fontSize: 12.5, fontWeight: isSelected ? 700 : 600, color: 'var(--sail-100)', lineHeight: 1.3 }}>
                    {sc.title}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {/* Grounding Citations Accordion Panel */}
        <section className="panel">
          <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="panel-title">Grounding Citations</span>
              <span className="panel-meta" style={{ marginLeft: 6 }}>{citationsList.length} verified</span>
            </div>
            <button
              onClick={toggleExpandAll}
              style={{
                fontSize: 10,
                padding: '2px 8px',
                background: 'var(--sail-800)',
                color: 'var(--sail-300)',
                border: '1px solid var(--sail-700)',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              {allExpanded ? 'Collapse All' : 'Expand All'}
            </button>
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <p className="infer" style={{ fontSize: 11, marginBottom: 2 }}>
              Physical constraints and verified authorities governing this scenario. Click any item to inspect the mathematical formula and impact.
            </p>

            {citationsList.map((cit) => {
              const isExpanded = expandedCitations[cit.id] ?? false;
              const badgeClass =
                cit.provenance === 'measured'
                  ? 'badge-emerald'
                  : cit.provenance === 'modeled'
                  ? 'badge-primary'
                  : 'badge-warn';

              return (
                <div
                  key={cit.id}
                  style={{
                    backgroundColor: 'var(--sail-950)',
                    borderRadius: 6,
                    border: isExpanded ? '1.5px solid var(--accent-dim)' : '1px solid var(--sail-800)',
                    overflow: 'hidden',
                    transition: 'border-color 0.15s ease',
                  }}
                >
                  {/* Clickable Header */}
                  <div
                    onClick={() => toggleCitation(cit.id)}
                    style={{
                      padding: '9px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      background: isExpanded ? '#ffffff' : 'transparent',
                      userSelect: 'none',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                      <span style={{ fontSize: 9, color: isExpanded ? 'var(--text-accent)' : 'var(--sail-500)', transition: 'transform 0.15s ease' }}>
                        {isExpanded ? '▼' : '▶'}
                      </span>
                      <span style={{ fontSize: 12, fontWeight: isExpanded ? 700 : 600, color: isExpanded ? 'var(--sail-100)' : 'var(--sail-100)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {cit.title}
                      </span>
                    </div>
                    <span className={`badge ${badgeClass}`} style={{ fontSize: 9, flexShrink: 0, textTransform: 'uppercase' }}>
                      {cit.provenance}
                    </span>
                  </div>

                  {/* Summary preview when collapsed */}
                  {!isExpanded && (
                    <div style={{ padding: '0 12px 8px 25px', fontSize: 10.5, color: 'var(--sail-400)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {cit.source}
                    </div>
                  )}

                  {/* Expanded Inset Details */}
                  {isExpanded && (
                    <div style={{
                      padding: '10px 12px 12px 25px',
                      borderTop: '1px solid var(--sail-800)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                      fontSize: 11,
                      background: 'var(--sail-900)',
                    }}>
                      <div>
                        <span style={{ color: 'var(--sail-400)', fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          Authority / Data Source
                        </span>
                        <div style={{ color: 'var(--sail-100)', fontWeight: 600, marginTop: 2 }}>
                          {cit.source}
                        </div>
                      </div>

                      {cit.equation && (
                        <div>
                          <span style={{ color: 'var(--sail-400)', fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            Mathematical / Physical Grounding
                          </span>
                          <div style={{
                            marginTop: 3,
                            padding: '6px 10px',
                            background: 'var(--ink-800)',
                            borderLeft: '2px solid var(--accent)',
                            borderRadius: '0 4px 4px 0',
                            color: '#ffffff',
                          }}>
                            <MathFormula math={cit.equation} block={true} />
                          </div>
                        </div>
                      )}

                      <div>
                        <span style={{ color: 'var(--sail-400)', fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          Why This Grounding Matters
                        </span>
                        <div style={{ color: 'var(--sail-200)', marginTop: 2, lineHeight: 1.45 }}>
                          {cit.rationale}
                        </div>
                      </div>

                      <div style={{ fontSize: 10, color: 'var(--sail-400)', fontFamily: 'var(--f-mono)', borderTop: '1px solid var(--sail-800)', paddingTop: 6 }}>
                        Calibration: <span style={{ color: 'var(--sail-200)' }}>{cit.confidence}</span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </div>

      {/* ── RIGHT COLUMN (col-8): Baseline Case, Assume & Prove, Delta Proof Matrix ── */}
      <div className="col-8 col-space">
        {/* 1. Baseline Case Reality */}
        <section className="panel" style={{ background: 'var(--ink-800)', borderColor: 'var(--ink-700)', color: '#FAFAFA' }}>
          <div className="panel-hd" style={{ borderBottomColor: 'var(--ink-700)' }}>
            <span className="panel-title" style={{ color: '#FAFAFA' }}>Baseline Operational Reality</span>
            <span className="panel-meta" style={{ color: '#A0A0A0' }}>grounded · live telemetry</span>
          </div>
          <div className="panel-body">
            <h3 style={{ fontSize: 15, fontWeight: 700, color: '#FAFAFA', margin: '0 0 10px', lineHeight: 1.4 }}>
              {activeScenario.subtitle}
            </h3>
            <div style={{ fontSize: 13, lineHeight: 1.8, color: '#FAFAFA' }}>
              <CitationTextParser
                text={activeScenario.base_case_text}
                citations={activeScenario.citations}
              />
            </div>
            <p className="infer" style={{ color: '#A0A0A0', marginTop: 10 }}>
              Highlighted terms link to the verified governing hydrodynamics formula, Admiralty nautical distance, or port authority circular.
            </p>
          </div>
        </section>

        {/* 2. Hypothetical "Assume & Prove" Card */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">
              {activeScenario.assumed_situation_title}
            </span>
          </div>
          <div className="panel-body">
            <div
              style={{
                fontSize: 13,
                lineHeight: 1.6,
                color: 'var(--sail-200)',
                whiteSpace: 'pre-wrap',
                padding: '12px 14px',
                background: 'var(--sail-900)',
                border: '1px solid var(--sail-800)',
                borderRadius: 'var(--r)',
              }}
            >
              {highlightDataTerms(activeScenario.assumed_situation_text)}
            </div>
          </div>
        </section>

        {/* 3. Mathematical Proof Matrix */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Calculated Proof Matrix</span>
            <span className="panel-meta">Baseline vs Assumed Delta</span>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--sail-800)', background: 'var(--sail-950)', textAlign: 'left', color: 'var(--sail-400)', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>Operational Dimension</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>Baseline (Current Reality)</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>Assumed Condition</th>
                  <th style={{ padding: '10px 16px', fontWeight: 600 }}>Calculated Delta</th>
                </tr>
              </thead>
              <tbody>
                {activeScenario.comparative_metrics.map((m, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: '1px solid var(--sail-800)',
                      backgroundColor: idx % 2 === 0 ? 'var(--sail-900)' : 'color-mix(in srgb, var(--sail-900) 80%, var(--sail-950))',
                    }}
                  >
                    <td style={{ padding: '10px 16px', fontWeight: 600, color: 'var(--sail-100)' }}>
                      {m.label}
                    </td>
                    <td style={{ padding: '10px 16px', fontFamily: 'var(--f-mono)', color: 'var(--sail-300)' }}>
                      {m.baseline}
                    </td>
                    <td style={{ padding: '10px 16px', fontFamily: 'var(--f-mono)', color: 'var(--sail-200)' }}>
                      {m.assumed}
                    </td>
                    <td
                      style={{
                        padding: '10px 16px',
                        fontFamily: 'var(--f-mono)',
                        fontWeight: 700,
                        color: m.favorable ? 'var(--emerald)' : 'var(--warn)',
                      }}
                    >
                      {m.delta}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
};

export default SituationalProofLab;
