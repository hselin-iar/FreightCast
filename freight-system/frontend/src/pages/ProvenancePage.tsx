import React, { useState, useEffect } from 'react';
import { getProvenanceSituations, getProvenanceCatalog } from '../lib/apiClient';
import type { SituationalScenario, ParameterItem } from '../lib/types';
import SituationalProofLab from '../components/SituationalProofLab';
import EvidencePrimer from '../components/EvidencePrimer';
import ParameterCatalog from '../components/ParameterCatalog';
import HypothesisAuditor from '../components/HypothesisAuditor';

type ProvenanceTab = 'situations' | 'primer' | 'catalog' | 'auditor';

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
    <div className="page-grid">
      {/* ── TOP HEADER (col-12) ── */}
      <div className="col-12">
        <section className="panel">
          <div className="panel-hd">
            <div>
              <span className="panel-title" style={{ fontSize: 16 }}>
                Empirical Proof & Situational Dissection
              </span>
              <span className="panel-meta" style={{ marginLeft: 12 }}>
                First-Principles Audit · Provenance Lab
              </span>
            </div>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <span className="panel-meta">
                Parameters: <strong style={{ color: 'var(--badge-measured-text)' }}>{parameters.length || 15} Verified</strong>
              </span>
              <span className="panel-meta">
                Proofs: <strong style={{ color: 'var(--text-accent)' }}>{scenarios.length || 4} Available</strong>
              </span>
            </div>
          </div>
          <div
            className="panel-body"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 16,
              padding: '14px 16px',
            }}
          >
            <p style={{ fontSize: 13, color: 'var(--sail-300)', margin: 0, maxWidth: 840, lineHeight: 1.5 }}>
              A completely transparent breakdown of why the maritime freight system operates the way it does. 
              Explore hypothetical situations, hover over any highlighted claim to inspect verified telemetry citations, and audit every parameter.
            </p>

            {/* View Switcher Tabs */}
            <div style={{ display: 'flex', background: 'var(--sail-800)', padding: 3, borderRadius: 'var(--r)', gap: 3 }}>
              <button
                onClick={() => setActiveTab('situations')}
                className={`btn btn-sm ${activeTab === 'situations' ? 'btn-accent' : ''}`}
                style={{
                  background: activeTab === 'situations' ? 'var(--accent)' : 'transparent',
                  color: activeTab === 'situations' ? 'var(--accent-text)' : 'var(--sail-400)',
                  fontWeight: activeTab === 'situations' ? 700 : 500,
                }}
              >
                ⚡ Situational Proofs
              </button>
              <button
                onClick={() => setActiveTab('primer')}
                className={`btn btn-sm ${activeTab === 'primer' ? 'btn-accent' : ''}`}
                style={{
                  background: activeTab === 'primer' ? 'var(--accent)' : 'transparent',
                  color: activeTab === 'primer' ? 'var(--accent-text)' : 'var(--sail-400)',
                  fontWeight: activeTab === 'primer' ? 700 : 500,
                }}
              >
                📖 Evidence Primer
              </button>
              <button
                onClick={() => setActiveTab('catalog')}
                className={`btn btn-sm ${activeTab === 'catalog' ? 'btn-accent' : ''}`}
                style={{
                  background: activeTab === 'catalog' ? 'var(--accent)' : 'transparent',
                  color: activeTab === 'catalog' ? 'var(--accent-text)' : 'var(--sail-400)',
                  fontWeight: activeTab === 'catalog' ? 700 : 500,
                }}
              >
                🔍 Source Catalog
              </button>
              <button
                onClick={() => setActiveTab('auditor')}
                className={`btn btn-sm ${activeTab === 'auditor' ? 'btn-accent' : ''}`}
                style={{
                  background: activeTab === 'auditor' ? 'var(--accent)' : 'transparent',
                  color: activeTab === 'auditor' ? 'var(--accent-text)' : 'var(--sail-400)',
                  fontWeight: activeTab === 'auditor' ? 700 : 500,
                }}
              >
                💬 Agentic Auditor
              </button>
            </div>
          </div>
        </section>
      </div>

      {/* ── Error Banner (if any) ── */}
      {error && (
        <div className="col-12">
          <div
            style={{
              padding: 12,
              backgroundColor: 'rgba(239, 68, 68, 0.08)',
              borderRadius: 'var(--r)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              color: '#b91c1c',
              fontSize: 13,
            }}
          >
            {error}
          </div>
        </div>
      )}

      {/* ── Dynamic Tab View Content ── */}
      {loading ? (
        <div className="col-12">
          <div className="panel" style={{ padding: 40, textAlign: 'center', color: 'var(--sail-500)' }}>
            Loading empirical proof models and parameter registry...
          </div>
        </div>
      ) : (
        <>
          {activeTab === 'situations' && <SituationalProofLab scenarios={scenarios} />}
          {activeTab === 'primer' && <EvidencePrimer />}
          {activeTab === 'catalog' && <ParameterCatalog parameters={parameters} loading={loading} />}
          {activeTab === 'auditor' && <HypothesisAuditor />}
        </>
      )}
    </div>
  );
};

export default ProvenancePage;
