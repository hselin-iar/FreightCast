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
    return <div className="panel panel-tinted" style={{ padding: 24 }}>No situational scenarios available.</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* ── Scenario Selection Bar ── */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          overflowX: 'auto',
          paddingBottom: 4,
        }}
      >
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
                padding: '12px 16px',
                borderRadius: 'var(--r)',
                border: isSelected ? '2px solid var(--accent-dim)' : '1px solid var(--sail-700)',
                backgroundColor: isSelected ? 'var(--accent-bg)' : 'var(--sail-900)',
                color: 'var(--sail-100)',
                cursor: 'pointer',
                textAlign: 'left',
                minWidth: 240,
                flex: 1,
                boxShadow: 'var(--shadow-panel)',
                transition: 'all 0.15s ease',
              }}
            >
              <span
                style={{
                  fontSize: 10,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: isSelected ? 'var(--text-accent)' : 'var(--sail-500)',
                  fontWeight: 700,
                  marginBottom: 4,
                }}
              >
                {sc.category}
              </span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--sail-100)' }}>
                {sc.title}
              </span>
            </button>
          );
        })}
      </div>

      {/* ── Active Scenario Dissection Card ── */}
      <div className="panel panel-tinted" style={{ padding: 24 }}>
        {/* Header */}
        <div style={{ marginBottom: 20, borderBottom: '1px solid var(--sail-800)', paddingBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '3px 8px',
                borderRadius: 4,
                backgroundColor: 'rgba(59, 130, 246, 0.12)',
                color: '#1d4ed8',
              }}
            >
              Situational Stress-Test
            </span>
            <span style={{ fontSize: 12, color: 'var(--sail-500)', fontWeight: 600 }}>
              First-Principles Empirical Proof
            </span>
          </div>
          <h2 style={{ fontSize: 18, color: 'var(--sail-100)', fontWeight: 700, margin: '4px 0 6px' }}>
            {activeScenario.subtitle}
          </h2>
          <p style={{ fontSize: 13, color: 'var(--sail-400)', margin: 0 }}>
            Hover or click any underlined claim to inspect underlying hydrographic charts, telemetry sources, and physics formulas.
          </p>
        </div>

        {/* 1. Baseline Case Narrative */}
        <div
          style={{
            backgroundColor: '#ffffff',
            borderRadius: 'var(--r)',
            padding: 20,
            border: '1px solid var(--sail-800)',
            boxShadow: 'var(--shadow-panel)',
            marginBottom: 20,
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
              color: 'var(--sail-500)',
              letterSpacing: '0.05em',
              marginBottom: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span style={{ color: '#059669', fontSize: 14 }}>●</span> Baseline Operational Reality (Grounded Data)
          </div>
          <div
            style={{
              fontSize: 14,
              lineHeight: 1.8,
              color: 'var(--sail-100)',
            }}
          >
            <CitationTextParser
              text={activeScenario.base_case_text}
              citations={activeScenario.citations}
            />
          </div>
        </div>

        {/* 2. Hypothetical "Assume & Prove" Card */}
        <div
          style={{
            backgroundColor: 'var(--accent-bg)',
            borderRadius: 'var(--r)',
            padding: 20,
            border: '1.5px solid var(--accent-dim)',
            marginBottom: 24,
          }}
        >
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: 'var(--sail-100)',
              marginBottom: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span>⚡</span> {activeScenario.assumed_situation_title}
          </div>
          <div
            style={{
              fontSize: 13.5,
              lineHeight: 1.7,
              color: 'var(--sail-200)',
              whiteSpace: 'pre-line',
            }}
          >
            {activeScenario.assumed_situation_text}
          </div>
        </div>

        {/* 3. Comparative Delta Proof Matrix */}
        <div>
          <h3 style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--sail-500)', letterSpacing: '0.05em', fontWeight: 700, marginBottom: 12 }}>
            Mathematical Proof: Baseline vs Assumed Situation
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--sail-800)', textAlign: 'left', color: 'var(--sail-500)' }}>
                  <th style={{ padding: '10px 14px' }}>Operational Dimension</th>
                  <th style={{ padding: '10px 14px' }}>Baseline (Current Reality)</th>
                  <th style={{ padding: '10px 14px' }}>Assumed Situation</th>
                  <th style={{ padding: '10px 14px' }}>Calculated Delta</th>
                </tr>
              </thead>
              <tbody>
                {activeScenario.comparative_metrics.map((m, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: '1px solid var(--sail-800)',
                      backgroundColor: idx % 2 === 0 ? '#ffffff' : 'var(--sail-950)',
                    }}
                  >
                    <td style={{ padding: '12px 14px', fontWeight: 600, color: 'var(--sail-100)' }}>
                      {m.label}
                    </td>
                    <td style={{ padding: '12px 14px', color: 'var(--sail-300)', fontFamily: 'var(--f-mono)' }}>
                      {m.baseline}
                    </td>
                    <td style={{ padding: '12px 14px', color: 'var(--sail-100)', fontWeight: 600, fontFamily: 'var(--f-mono)' }}>
                      {m.assumed}
                    </td>
                    <td style={{ padding: '12px 14px', fontFamily: 'var(--f-mono)' }}>
                      <span
                        style={{
                          padding: '3px 8px',
                          borderRadius: 4,
                          fontSize: 12,
                          fontWeight: 700,
                          backgroundColor: m.favorable ? 'rgba(16, 185, 129, 0.14)' : 'rgba(239, 68, 68, 0.14)',
                          color: m.favorable ? '#047857' : '#b91c1c',
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
        </div>
      </div>
    </div>
  );
};

export default SituationalProofLab;
