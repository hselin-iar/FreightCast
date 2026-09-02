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
    <div
      className="panel panel-tinted"
      style={{
        padding: 24,
        border: '1.5px solid var(--accent-dim)',
        backgroundColor: '#ffffff',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            padding: '3px 8px',
            borderRadius: 4,
            backgroundColor: 'var(--accent-bg)',
            color: 'var(--text-accent)',
          }}
        >
          Agentic Hypothesis Auditor
        </span>
        <span style={{ fontSize: 12, color: 'var(--sail-500)', fontWeight: 600 }}>
          On-demand multi-stage solver experiments & empirical proofs
        </span>
      </div>

      <p style={{ fontSize: 13.5, color: 'var(--sail-300)', marginBottom: 16 }}>
        Ask any hypothetical or operational question to prove why the maritime system behaves the way it does:
      </p>

      {/* Suggested Chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        {suggestedQuestions.map((sq, idx) => (
          <button
            key={idx}
            onClick={() => handleAsk(sq)}
            style={{
              padding: '6px 14px',
              borderRadius: 'var(--r)',
              fontSize: 12,
              fontWeight: 600,
              backgroundColor: 'var(--sail-900)',
              color: 'var(--sail-100)',
              border: '1px solid var(--sail-700)',
              cursor: 'pointer',
              textAlign: 'left',
              boxShadow: 'var(--shadow-panel)',
              transition: 'all 0.15s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--accent-dim)';
              e.currentTarget.style.backgroundColor = 'var(--accent-bg)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--sail-700)';
              e.currentTarget.style.backgroundColor = 'var(--sail-900)';
            }}
          >
            💬 {sq}
          </button>
        ))}
      </div>

      {/* Input Bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: response || error || loading ? 20 : 0 }}>
        <input
          type="text"
          className="input-field"
          placeholder="e.g. Prove why distance alone does not decide the optimal discharge port..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAsk(question)}
          style={{ flex: 1, fontSize: 13.5 }}
        />
        <button
          onClick={() => handleAsk(question)}
          disabled={loading || !question.trim()}
          className="btn btn-primary"
          style={{ padding: '0 24px', whiteSpace: 'nowrap' }}
        >
          {loading ? 'Proving Hypothesis...' : 'Audit & Prove'}
        </button>
      </div>

      {/* Loading State */}
      {loading && (
        <div
          style={{
            padding: 20,
            textAlign: 'center',
            color: 'var(--text-accent)',
            fontSize: 13,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
          }}
        >
          <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⏳</span>
          Running multi-turn MILP solver scenarios and drafting empirical proof...
        </div>
      )}

      {/* Error State */}
      {error && (
        <div
          style={{
            padding: 14,
            backgroundColor: 'rgba(239, 68, 68, 0.08)',
            borderRadius: 'var(--r)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
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
            backgroundColor: 'var(--sail-950)',
            borderRadius: 'var(--r)',
            padding: 20,
            border: '1px solid var(--sail-800)',
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
              color: '#047857',
              letterSpacing: '0.05em',
              marginBottom: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span>✓</span> Auditor Synthesis & Proof
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
  );
};

export default HypothesisAuditor;
