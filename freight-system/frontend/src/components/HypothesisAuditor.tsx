import React, { useState } from 'react';
import { postChat } from '../lib/apiClient';

export const HypothesisAuditor: React.FC = () => {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const suggestedQuestions = [
    'Why does Dhamra take 2 voyages to transport 120k cargo when Gangavaram takes 1?',
    'Prove why Capesize is cheaper per tonne despite costing more overall.',
    'Explain the exact mathematical derivation of the 5% maritime freight tax.',
    'Why is Gangavaram preferred even if rail freight to inland plants is higher?',
  ];

  const handleAsk = async (q: string) => {
    if (!q.trim() || loading) return;
    setQuestion(q);
    setLoading(true);
    setError(null);
    setResponse(null);

    const promptMessage = `[PROVENANCE AUDIT REQUEST]: Please provide a rigorous, first-principles mathematical and operational proof explaining the following question in clear English with exact data sources and numbers: "${q}".`;

    const res = await postChat({
      message: promptMessage,
      conversation_history: [],
      cargo_context: {
        cargo_quantity: 120000,
        origin_port: 'Australia (Hay Point)',
        discharge_ports: ['Dhamra', 'Gangavaram', 'Paradip'],
        timing_flexibility_days: 30,
      },
    });

    setLoading(false);
    if (res.error) {
      setError(res.error.message || 'Audit query failed. Please check connection or API keys.');
    } else if (res.data) {
      setResponse(res.data.reply);
    }
  };

  return (
    <div className="col-12 col-space">
      <section className="panel">
        <div className="panel-hd">
          <span className="panel-title">Agentic Hypothesis Auditor</span>
          <span className="panel-meta">On-Demand Empirical Proofs</span>
        </div>
        <div className="panel-body" style={{ maxWidth: 900, margin: '0 auto', width: '100%' }}>
          <p style={{ fontSize: 13.5, color: 'var(--sail-300)', marginBottom: 14 }}>
            Ask any hypothetical or operational question to prove why the maritime system behaves the way it does:
          </p>

          {/* Suggested Chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
            {suggestedQuestions.map((sq, idx) => (
              <button
                key={idx}
                onClick={() => handleAsk(sq)}
                style={{
                  padding: '6px 12px',
                  borderRadius: 'var(--r)',
                  fontSize: 12,
                  fontWeight: 500,
                  backgroundColor: 'var(--sail-800)',
                  color: 'var(--sail-200)',
                  border: '1px solid var(--sail-700)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.12s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--accent-dim)';
                  e.currentTarget.style.backgroundColor = 'var(--accent-bg)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--sail-700)';
                  e.currentTarget.style.backgroundColor = 'var(--sail-800)';
                }}
              >
                💬 {sq}
              </button>
            ))}
          </div>

          {/* Input Bar */}
          <div style={{ display: 'flex', gap: 10, marginBottom: response || error || loading ? 16 : 0 }}>
            <input
              type="text"
              className="input-field"
              placeholder="e.g. Prove why distance alone does not decide the optimal discharge port..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk(question)}
              style={{ flex: 1, fontSize: 13 }}
            />
            <button
              onClick={() => handleAsk(question)}
              disabled={loading || !question.trim()}
              className="btn btn-accent"
              style={{ padding: '0 20px', whiteSpace: 'nowrap' }}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  <span>Proving...</span>
                </>
              ) : (
                'Audit & Prove'
              )}
            </button>
          </div>

          {/* Error State */}
          {error && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                borderRadius: 'var(--r)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                color: '#b91c1c',
                fontSize: 12.5,
              }}
            >
              {error}
            </div>
          )}

          {/* Response Box */}
          {response && (
            <div
              style={{
                marginTop: 16,
                backgroundColor: 'var(--sail-800)',
                borderRadius: 'var(--r)',
                padding: 16,
                border: '1px solid var(--sail-700)',
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: 'var(--badge-measured-text)',
                  letterSpacing: '0.05em',
                  marginBottom: 8,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                <span>✓</span> Auditor Synthesis & Empirical Proof
              </div>
              <div
                style={{
                  fontSize: 13.5,
                  lineHeight: 1.8,
                  color: 'var(--sail-100)',
                  whiteSpace: 'pre-line',
                }}
              >
                {response}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default HypothesisAuditor;
