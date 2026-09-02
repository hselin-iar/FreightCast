import React, { useState, useEffect } from 'react';
import type { SituationalScenario, RecommendationRequest, RecommendationResponse } from '../lib/types';
import SituationalProofLab from '../components/SituationalProofLab';
import HypothesisAuditor from '../components/HypothesisAuditor';
// Using generic fetch for the new POST endpoint for now, can be moved to apiClient later.

export const ProvenancePage: React.FC<{
  requestContext?: RecommendationRequest | null;
  resultContext?: RecommendationResponse | null;
}> = ({ requestContext, resultContext }) => {
  const [scenarios, setScenarios] = useState<SituationalScenario[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!requestContext || !resultContext) {
      // Nothing to generate proofs for yet.
      return;
    }

    let isMounted = true;
    (async () => {
      setLoading(true);
      try {
        const response = await fetch('http://localhost:8000/provenance/situations/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            request: requestContext,
            result: resultContext
          }),
        });

        if (!response.ok) {
          throw new Error('Failed to generate situational proofs.');
        }

        const data = await response.json();
        if (!isMounted) return;
        
        if (data.scenarios) {
          setScenarios(data.scenarios);
        }
      } catch (err: any) {
        if (isMounted) setError(err.message || 'Failed to generate dynamic provenance.');
      } finally {
        if (isMounted) setLoading(false);
      }
    })();

    return () => {
      isMounted = false;
    };
  }, [requestContext, resultContext]);

  return (
    <div className="page-grid">
      {/* ── TOP HEADER (col-12) ── */}
      <div className="col-12">
        <section className="panel">
          <div className="panel-hd">
            <div>
              <span className="panel-title" style={{ fontSize: 16 }}>
                Dynamic Empirical Proof & Situational Dissection
              </span>
              <span className="panel-meta" style={{ marginLeft: 12 }}>
                First-Principles Audit · Provenance Lab
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
              Explore hypothetical situations, hover over any highlighted claim to inspect verified telemetry citations. 
              {requestContext ? ' These proofs are dynamically generated for your current cargo requirement.' : ' Run a recommendation first to generate situational proofs.'}
            </p>
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

      {/* ── Dynamic Layout ── */}
      {loading ? (
        <div className="col-12">
          <div className="panel" style={{ padding: 40, textAlign: 'center', color: 'var(--sail-500)' }}>
            <div className="spinner" style={{ marginBottom: 12 }} />
            <br />
            Agentic AI is actively dissecting your cargo strategy and formulating empirical proofs...
          </div>
        </div>
      ) : (
        <>
          {scenarios.length > 0 && <SituationalProofLab scenarios={scenarios} />}
          {!requestContext && !loading && (
             <div className="col-12">
                <div className="panel" style={{ padding: 40, textAlign: 'center', color: 'var(--sail-500)' }}>
                   Please submit a cargo request in the Recommendation tab to begin.
                </div>
             </div>
          )}
        </>
      )}

      {/* Agentic Auditor always sits at the bottom */}
      <div className="col-12" style={{ marginTop: 24 }}>
        <HypothesisAuditor requestContext={requestContext} />
      </div>
    </div>
  );
};

export default ProvenancePage;
