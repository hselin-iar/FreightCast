import React, { useState } from 'react';
import type { SituationalScenario } from '../lib/types';
import CitationTextParser from './CitationTextParser';

interface Props {
  scenarios: SituationalScenario[];
}

export const SituationalProofLab: React.FC<Props> = ({ scenarios }) => {
  const [selectedId, setSelectedId] = useState<string>(scenarios[0]?.id ?? '');
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

  return (
    <>
      {/* ── LEFT COLUMN (col-4): Scenario Selector & Context ── */}
      <div className="col-4 col-space">
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Situational Stress-Tests</span>
            <span className="panel-meta">{scenarios.length} scenarios</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {scenarios.map((sc) => {
              const isSelected = sc.id === activeScenario.id;
              return (
                <button
                  key={sc.id}
                  onClick={() => setSelectedId(sc.id)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    padding: '12px 14px',
                    borderRadius: 'var(--r)',
                    border: isSelected ? '2px solid var(--accent-dim)' : '1px solid var(--sail-800)',
                    backgroundColor: isSelected ? 'var(--accent-bg)' : 'var(--sail-900)',
                    color: 'var(--sail-100)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.12s ease',
                  }}
                >
                  <span
                    style={{
                      fontSize: 10,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      color: isSelected ? 'var(--text-accent)' : 'var(--sail-500)',
                      fontWeight: 700,
                      marginBottom: 3,
                    }}
                  >
                    {sc.category}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--sail-100)', lineHeight: 1.3 }}>
                    {sc.title}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {/* Key Grounded Parameters for Active Scenario */}
        <section className="panel panel-tinted">
          <div className="panel-hd">
            <span className="panel-title">Grounding Citations</span>
            <span className="panel-meta">{Object.keys(activeScenario.citations).length} references</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Object.values(activeScenario.citations).map((cit) => (
              <div
                key={cit.id}
                style={{
                  padding: '8px 10px',
                  backgroundColor: 'var(--sail-900)',
                  borderRadius: 'var(--r)',
                  border: '1px solid var(--sail-800)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 3,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--sail-100)' }}>
                    {cit.title}
                  </span>
                  <span
                    className={`badge badge-${cit.provenance}`}
                    style={{ fontSize: 9 }}
                  >
                    {cit.provenance.toUpperCase()}
                  </span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--sail-500)' }}>
                  {cit.source}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* ── RIGHT COLUMN (col-8): Baseline Case, Assume & Prove, Delta Proof Matrix ── */}
      <div className="col-8 col-space">
        {/* 1. Baseline Case Reality */}
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Baseline Operational Reality</span>
            <span className="panel-meta">grounded · live telemetry</span>
          </div>
          <div className="panel-body">
            <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--sail-100)', margin: '0 0 10px', lineHeight: 1.4 }}>
              {activeScenario.subtitle}
            </h3>
            <div style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)' }}>
              <CitationTextParser
                text={activeScenario.base_case_text}
                citations={activeScenario.citations}
              />
            </div>
            <p className="infer">
              Hover or click any highlighted token to view the governing hydrodynamics formula, Admiralty nautical distance, or port authority bathymetry circular.
            </p>
          </div>
        </section>

        {/* 2. Hypothetical "Assume & Prove" Card */}
        <section className="panel panel-yellow">
          <div className="panel-hd">
            <span className="panel-title" style={{ color: 'var(--accent-text)' }}>
              ⚡ {activeScenario.assumed_situation_title}
            </span>
            <span className="panel-meta" style={{ color: 'rgba(0,0,0,0.6)' }}>
              Hypothetical Simulation
            </span>
          </div>
          <div className="panel-body">
            <div style={{ fontSize: 13.5, lineHeight: 1.75, color: 'var(--accent-text)', whiteSpace: 'pre-line' }}>
              {activeScenario.assumed_situation_text}
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
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--sail-800)', background: 'var(--sail-800)', textAlign: 'left', color: 'var(--sail-500)' }}>
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
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--sail-100)' }}>
                      {m.label}
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>
                      {m.baseline}
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--sail-100)', fontWeight: 600, fontFamily: 'var(--f-mono)' }}>
                      {m.assumed}
                    </td>
                    <td style={{ padding: '12px 16px', fontFamily: 'var(--f-mono)' }}>
                      <span
                        style={{
                          padding: '3px 8px',
                          borderRadius: 'var(--r)',
                          fontSize: 11.5,
                          fontWeight: 700,
                          backgroundColor: m.favorable ? 'var(--badge-measured-bg)' : 'rgba(239, 68, 68, 0.12)',
                          color: m.favorable ? 'var(--badge-measured-text)' : '#b91c1c',
                        }}
                      >
                        {m.delta}
                      </span>
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
