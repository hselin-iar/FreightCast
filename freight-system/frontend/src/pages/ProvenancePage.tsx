import React, { useState, useEffect } from 'react';
import { getProvenanceSituations, getProvenanceCatalog } from '../lib/apiClient';
import type { SituationalScenario, ParameterItem } from '../lib/types';
import SituationalProofLab from '../components/SituationalProofLab';
import EvidencePrimer from '../components/EvidencePrimer';
import ParameterCatalog from '../components/ParameterCatalog';
import HypothesisAuditor from '../components/HypothesisAuditor';

type ProvenanceTab = 'situations' | 'primer' | 'catalog';

export const ProvenancePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ProvenanceTab>('situations');
  const [scenarios, setScenarios] = useState<SituationalScenario[]>([]);
  const [parameters, setParameters] = useState<ParameterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      setLoading(true);
      const [situationsRes, catalogRes] = await Promise.all([
        getProvenanceSituations(),
        getProvenanceCatalog(),
      ]);

      if (!isMounted) return;

      if (situationsRes.data) {
        setScenarios(situationsRes.data.scenarios);
      }
      if (catalogRes.data) {
        setParameters(catalogRes.data.parameters);
      }
      if (situationsRes.error && catalogRes.error) {
        setError(situationsRes.error.message || 'Failed to load provenance data.');
      }
      setLoading(false);
    })();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* ── Page Header ── */}
      <div
        className="panel panel-tinted"
        style={{
          padding: '24px 28px',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          borderBottom: '1px solid var(--sail-800)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '3px 9px',
                borderRadius: 4,
                backgroundColor: 'var(--accent-bg)',
                color: 'var(--text-accent)',
              }}
            >
              First-Principles Audit
            </span>
            <span style={{ fontSize: 12, color: 'var(--sail-500)', fontFamily: 'var(--f-mono)', fontWeight: 600 }}>
              Provenance & Understanding Lab
            </span>
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--sail-100)', margin: '4px 0 6px' }}>
            Empirical Proof & Situational Dissection
          </h1>
          <p style={{ fontSize: 13.5, color: 'var(--sail-300)', margin: 0, maxWidth: 880, lineHeight: 1.6 }}>
            A completely transparent, plain-text breakdown of why the maritime freight system operates the way it does. 
            Explore hypothetical situations, hover over any claim to inspect verified telemetry citations, and audit every parameter.
          </p>
        </div>

        {/* Status Indicators */}
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ backgroundColor: '#ffffff', padding: '10px 16px', borderRadius: 'var(--r)', border: '1px solid var(--sail-800)', boxShadow: 'var(--shadow-panel)', textAlign: 'right' }}>
            <span style={{ fontSize: 10, color: 'var(--sail-500)', textTransform: 'uppercase', fontWeight: 700, display: 'block' }}>Grounded Parameters</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: '#047857' }}>{parameters.length || 15} Verified</span>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '10px 16px', borderRadius: 'var(--r)', border: '1px solid var(--sail-800)', boxShadow: 'var(--shadow-panel)', textAlign: 'right' }}>
            <span style={{ fontSize: 10, color: 'var(--sail-500)', textTransform: 'uppercase', fontWeight: 700, display: 'block' }}>Situational Proofs</span>
            <span style={{ fontSize: 15, fontWeight: 700, color: '#1d4ed8' }}>{scenarios.length || 4} Available</span>
          </div>
        </div>
      </div>

      {/* ── View Switcher Navigation Bar ── */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          borderBottom: '1px solid var(--sail-800)',
          paddingBottom: 12,
        }}
      >
        <button
          onClick={() => setActiveTab('situations')}
          className={`btn ${activeTab === 'situations' ? 'btn-primary' : 'btn-outline'}`}
          style={{ padding: '8px 18px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}
        >
          <span>⚡</span> Situational Proofs & Scenarios
        </button>
        <button
          onClick={() => setActiveTab('primer')}
          className={`btn ${activeTab === 'primer' ? 'btn-primary' : 'btn-outline'}`}
          style={{ padding: '8px 18px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}
        >
          <span>📖</span> The Maritime Evidence Primer
        </button>
        <button
          onClick={() => setActiveTab('catalog')}
          className={`btn ${activeTab === 'catalog' ? 'btn-primary' : 'btn-outline'}`}
          style={{ padding: '8px 18px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}
        >
          <span>🔍</span> Source & Parameter Catalog
        </button>
      </div>

      {/* ── Main View Content ── */}
      {error && (
        <div
          style={{
            padding: 16,
            backgroundColor: 'rgba(239, 68, 68, 0.08)',
            borderRadius: 'var(--r)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#b91c1c',
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="panel panel-tinted" style={{ padding: 40, textAlign: 'center', color: 'var(--sail-400)' }}>
          Loading empirical proof models and parameter registry...
        </div>
      ) : (
        <>
          {activeTab === 'situations' && <SituationalProofLab scenarios={scenarios} />}
          {activeTab === 'primer' && <EvidencePrimer />}
          {activeTab === 'catalog' && <ParameterCatalog parameters={parameters} loading={loading} />}
        </>
      )}

      {/* ── Persistent Hypothesis Auditor ("Ask the Auditor") ── */}
      <HypothesisAuditor />
    </div>
  );
};

export default ProvenancePage;
