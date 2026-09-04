import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { postChat } from '../lib/apiClient';
import type { RecommendationRequest, RecommendationResponse } from '../lib/types';
import { DataTermToken } from './DataTermToken';
import { findDataSource } from '../lib/dataSources';
import { preprocessMathematicalMarkdown, rehypeUnescapeCurrency } from '../lib/mathUtils';
import { highlightDataTerms } from '../lib/termHighlighter';

export const HypothesisAuditor: React.FC<{
  requestContext?: RecommendationRequest | null;
  resultContext?: RecommendationResponse | null;
}> = ({ requestContext, resultContext }) => {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [auditPhase, setAuditPhase] = useState<string | null>(null);

  const getSuggestedQuestions = (): string[] => {
    if (!requestContext || !resultContext) {
      return [
        'Prove why Capesize is cheaper per tonne despite costing more overall.',
        'Explain the exact mathematical derivation of the 5% maritime freight tax.',
        'How does queuing delay at Paradip affect the overall demurrage risk?',
        'What physical draft restrictions force cargo parcel splitting at East Coast ports?',
      ];
    }

    const rec = resultContext.recommendation;
    const voyages = rec.voyages || [];
    const primaryVoyage = voyages[0];
    const vesselClass = primaryVoyage?.vessel_class || 'Panamax/Kamsarmax';
    const dischargePort = primaryVoyage?.port || requestContext.discharge_ports?.[0] || 'Paradip';
    const origin = requestContext.origin_port || 'Australia (Hay Point)';
    const qty = requestContext.cargo_quantity || 60000;
    const voyageCount = rec.voyage_count || 1;
    const fixDay = primaryVoyage?.fix_day ?? 28;
    const totalCost = rec.total_cost_worst_case || rec.cost_breakdown.total;
    const scenarioComp = resultContext.scenario_comparison || [];

    // Find spot alternative for comparison
    const spotAlt = scenarioComp.find((s) => s.commitment_mode === 'spot');
    const savingsVsSpot = spotAlt ? spotAlt.total_cost_worst_case - rec.total_cost_worst_case : null;

    // 1. Vessel Allocation & Sizing Physics
    let q1 = '';
    if (voyageCount === 1) {
      q1 = `Prove why a single ${vesselClass} (${qty / 1000}kt) is optimal for ${dischargePort} instead of splitting across multiple voyages.`;
    } else {
      const perVoyageQty = Math.round(qty / voyageCount / 1000);
      q1 = `Why does transporting ${qty / 1000}k tonnes to ${dischargePort} require ${voyageCount} ${vesselClass} voyages (~${perVoyageQty}kt each) instead of a single Capesize?`;
    }

    // 2. Commitment Mode Financial Alpha & Forward Curve
    let q2 = '';
    if (rec.commitment_mode === 'locked' && savingsVsSpot && savingsVsSpot > 0) {
      q2 = `Why does locking ${vesselClass} commitment on Day ${fixDay} save $${Math.round(savingsVsSpot).toLocaleString()} compared to spot market exposure?`;
    } else if (rec.commitment_mode === 'spot') {
      q2 = `Why did the solver select spot chartering on Day ${fixDay} despite market volatility risk buffer?`;
    } else {
      q2 = `How does fixing on Day ${fixDay} hedge forward freight rate volatility on the ${origin} route?`;
    }

    // 3. Port Hydrodynamics & Draft Constraints
    let q3 = '';
    if (dischargePort === 'Dhamra') {
      q3 = `How does Dhamra's 14.0m maximum draft limit constrain vessel allocation and tidal gate entry windows?`;
    } else if (dischargePort === 'Paradip') {
      q3 = `How do berth wait delays and tidal draft limits at Paradip impact demurrage exposure?`;
    } else if (dischargePort === 'Gangavaram') {
      q3 = `Why does Gangavaram's deep-water 18.5m draft eliminate vessel parcel splitting penalties?`;
    } else {
      q3 = `How do harbor draft constraints and discharge handling rates at ${dischargePort} drive the landed cost?`;
    }

    // 4. Scenario Comparison & Runner-Up Trade-off
    let q4 = '';
    if (scenarioComp.length > 0) {
      const runnerUp = scenarioComp[0];
      const delta = Math.abs(runnerUp.total_cost_worst_case - totalCost);
      q4 = `Compare the optimal plan ($${Math.round(totalCost).toLocaleString()}) against the runner-up (${runnerUp.voyage_count} voy, ${runnerUp.commitment_mode}): what trade-offs drove the $${Math.round(delta).toLocaleString()} delta?`;
    } else {
      q4 = `Explain the exact mathematical derivation of the 5% maritime freight tax.`;
    }

    return [q1, q2, q3, q4];
  };

  const suggestedQuestions = getSuggestedQuestions();

  const handleAsk = async (q: string) => {
    if (!q.trim() || loading) return;
    setQuestion(q);
    setLoading(true);
    setError(null);
    setResponse(null);

    const cargoContext = requestContext || {
      cargo_quantity: 60000,
      origin_port: 'Australia (Hay Point)',
      discharge_ports: ['Dhamra', 'Gangavaram', 'Paradip'],
      timing_flexibility_days: 30,
    };

    setAuditPhase('Generating operational physics and mathematical sections in parallel…');

    let groundTruthContext = '';
    if (resultContext) {
      const rec = resultContext.recommendation;
      const primaryVoyage = rec.voyages?.[0];
      const recBd = rec.cost_breakdown;
      groundTruthContext = `\n\nAUDIT GROUND TRUTH FACTS (from active solver recommendation — use these verified figures directly):
- Recommended Strategy: ${rec.commitment_mode}, Vessel: ${primaryVoyage?.vessel_class || 'N/A'}, Port: ${primaryVoyage?.port || 'N/A'}, Fix Day: ${primaryVoyage?.fix_day ?? 'N/A'}, Total Worst-Case Cost: $${Math.round(rec.total_cost_worst_case || 0).toLocaleString()}
  Cost Breakdown: Ocean Freight: $${Math.round(recBd?.ocean_freight || 0).toLocaleString()}, Bunker: $${Math.round(recBd?.bunker || 0).toLocaleString()}, OPEX: $${Math.round(recBd?.opex || 0).toLocaleString()}, Port Handling: $${Math.round(recBd?.port_handling || 0).toLocaleString()}, Tax: $${Math.round(recBd?.tax || 0).toLocaleString()}, Risk Buffer: $${Math.round(recBd?.risk_buffer || 0).toLocaleString()}
- Scenario Comparison:
${resultContext.scenario_comparison?.map(s => `  * Mode: ${s.commitment_mode}, Vessel: ${s.voyages?.[0]?.vessel_class || 'N/A'}, Total Worst-Case: $${Math.round(s.total_cost_worst_case || 0).toLocaleString()}, Total Base: $${Math.round(s.cost_breakdown?.total || 0).toLocaleString()}, Risk Buffer: $${Math.round(s.cost_breakdown?.risk_buffer || 0).toLocaleString()}, Ocean Freight: $${Math.round(s.cost_breakdown?.ocean_freight || 0).toLocaleString()}`).join('\n') || 'None'}`;
    }

    // Section 1: Physical & Operational Constraints
    const promptSec1 = `[AUDIT SECTION 1 - OPERATIONAL CONSTRAINTS & VESSEL PHYSICS]:
Regarding the maritime question: "${q}"
Please provide an exhaustive, multi-paragraph first-principles breakdown of the physical and operational constraints (e.g. vessel deadweight capacity, draft restrictions at discharge ports, approach channels, distance, and geofenced waiting time) with complete hydrodynamic depth and maritime domain detail.
STRICT INSTRUCTION: Output ONLY the final, polished response for the user. Never output any scratchpads, "Wait compute", or stream-of-consciousness thinking.
Format using clean Markdown with bold terms. Do not include bracketed technical variable tags like ( freight ).${groundTruthContext}`;

    // Section 2: Mathematical Derivation & Economic Proof
    const promptSec2 = `[AUDIT SECTION 2 - MATHEMATICAL COST DERIVATION & ECONOMIC PROOF]:
Regarding the maritime question: "${q}"
Please provide an exhaustive, in-depth mathematical derivation, full step-by-step cost reconciliation, and structured ledger table comparing the options.
STRICT INSTRUCTION: Output ONLY the final, polished response for the user. Never output any scratchpads, "Wait compute", or stream-of-consciousness thinking.
CRITICAL MATHEMATICAL & CURRENCY FORMATTING:
- Display/block equations MUST be enclosed in double dollar signs on separate lines with NO internal blank lines:
$$
\\mathbb{E}[C^{\\text{dem}}_v] = r^{\\text{dem}} \\cdot \\mathbb{E}[D_v] \\qquad (1)
$$
- NEVER write LaTeX "\\]" or "\\[" delimiters anywhere in your response.
- NEVER write equation numbers like "\\qquad (1) \\]" or "\\tag{1} \\]" with a closing bracket "\\]". Write "\\qquad (1)" inside "$$ ... $$" before the closing "$$".
- NEVER put English prose or sentences on the same line as an equation or immediately following a closing delimiter. Put all explanations, "where", and "If" clauses in separate paragraphs after a blank line.
- Every opening \\left[ or \\left( MUST be paired with a closing \\right] or \\right). Never emit a bare \\right without a closing delimiter.
- In variable definition bullet lists, ALWAYS wrap the mathematical variable in single dollar signs, e.g.:
  * $r^{\\text{dem}}$ = demurrage rate (USD / day)
  * $\\mathbb{E}[D_v]$ = expected delay at berth
  * $\\frac{C_v^{\\text{tot}}}{DWT_v}$ = cost per dwt
- Never write raw LaTeX commands or variables (like r^{\\text{dem}} or C^{\\text{tot}}) outside dollar signs.
- Never write semicolons around mathematical operators (write \\cdot or \\times, never ;\\times; or ;=;). Use commas for function arguments, e.g. \\max(0, x), never semicolons.
- For combined super/subscripts, always write C^{\\text{dem}}_{iv}, never omit the underscore like C^{\\text{dem}}{iv}.
- When writing dollar values, format as '$1,000,000' in plain prose outside LaTeX. Never write '$C = \\$1,000,000$'. Inside LaTeX equations, use '\\text{ USD}' (e.g. 'C^{\\text{oc}} = 1{,}002{,}300\\text{ USD}').
- Include a clean Markdown table comparing Ocean freight, Bunker, OPEX, Port handling, Tax, and Demurrage/Rail costs.
- Do not include bracketed technical variable tags like ( freight ).${groundTruthContext}`;

    try {
      // Execute both sections concurrently to prevent token limits and timeouts
      const [res1, res2] = await Promise.all([
        postChat({
          message: promptSec1,
          conversation_history: [],
          cargo_context: cargoContext,
        }),
        postChat({
          message: promptSec2,
          conversation_history: [],
          cargo_context: cargoContext,
        }),
      ]);

      setLoading(false);
      setAuditPhase(null);

      const text1 = res1.data?.reply?.trim() || '';
      const text2 = res2.data?.reply?.trim() || '';

      if (!text1 && !text2) {
        setError(res1.error?.message || res2.error?.message || 'Audit query failed. Please try again.');
        return;
      }

      // Compile both sections into a unified comprehensive proof
      let compiled = '';
      if (text1 && text2) {
        compiled = `### 1. Operational & Hydrodynamic Constraints\n\n${text1}\n\n---\n\n### 2. First-Principles Cost Breakdown & Mathematical Proof\n\n${text2}`;
      } else {
        compiled = text1 || text2;
      }

      setResponse(compiled);
    } catch (err: unknown) {
      setLoading(false);
      setAuditPhase(null);
      setError(err instanceof Error ? err.message : 'Audit query failed.');
    }
  };

  const handleCopy = () => {
    if (!response) return;
    navigator.clipboard.writeText(response);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="col-12 col-space">
      <section className="panel" style={{ border: '1px solid var(--sail-700)', overflow: 'hidden' }}>
        <div className="panel-hd" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px' }}>
          <div>
            <span className="panel-title" style={{ fontSize: 14, fontWeight: 700, letterSpacing: '0.02em' }}>
              Agentic Hypothesis Auditor
            </span>
          </div>
          <span className="panel-meta" style={{ fontFamily: 'var(--f-mono)', fontSize: 11, color: 'var(--sail-400)' }}>
            First-Principles Empirical Proofs
          </span>
        </div>

        <div className="panel-body" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
            <p style={{ fontSize: 13, color: 'var(--sail-300)', margin: 0 }}>
              Ask any hypothetical or operational question to prove why the maritime optimization system behaves the way it does:
            </p>
            {requestContext && (
              <span style={{
                fontSize: 11,
                fontFamily: 'var(--f-mono)',
                padding: '2px 8px',
                borderRadius: 4,
                background: 'color-mix(in srgb, var(--sail-800) 80%, transparent)',
                border: '1px solid var(--sail-700)',
                color: 'var(--sail-300)',
              }}>
                Context: {requestContext.cargo_quantity / 1000}kt · {requestContext.discharge_ports.join(', ')}
              </span>
            )}
          </div>

          {/* Suggested Chips */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
              Suggested Hypotheses to Audit:
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {suggestedQuestions.map((sq, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleAsk(sq)}
                  disabled={loading}
                  style={{
                    padding: '7px 12px',
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 500,
                    backgroundColor: 'var(--sail-800)',
                    color: 'var(--sail-200)',
                    border: '1px solid var(--sail-700)',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s ease',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                  onMouseEnter={(e) => {
                    if (!loading) {
                      e.currentTarget.style.borderColor = 'var(--accent)';
                      e.currentTarget.style.color = 'var(--text-accent)';
                      e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--accent) 10%, var(--sail-800))';
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--sail-700)';
                    e.currentTarget.style.color = 'var(--sail-200)';
                    e.currentTarget.style.backgroundColor = 'var(--sail-800)';
                  }}
                >
                  <span style={{ opacity: 0.6, fontSize: 10 }}>↗</span>
                  <span>{sq}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Input Bar */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input
              type="text"
              className="input-field"
              placeholder="e.g. Prove why distance alone does not decide the optimal discharge port..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk(question)}
              style={{
                flex: 1,
                fontSize: 13,
                padding: '10px 14px',
                height: 42,
              }}
            />
            <button
              onClick={() => handleAsk(question)}
              disabled={loading || !question.trim()}
              className="btn btn-accent"
              style={{
                padding: '0 24px',
                height: 42,
                whiteSpace: 'nowrap',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  <span>Auditing Proof...</span>
                </>
              ) : (
                <>
                  <span>Audit & Prove</span>
                  <span style={{ fontSize: 11, opacity: 0.8 }}>↵</span>
                </>
              )}
            </button>
          </div>

          {/* Error State */}
          {error && (
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                borderRadius: 6,
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#f87171',
                fontSize: 13,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <span>✕</span>
              <span>{error}</span>
            </div>
          )}

          {/* Loading Skeleton */}
          {loading && (
            <div style={{
              padding: 20,
              backgroundColor: 'var(--sail-800)',
              borderRadius: 8,
              border: '1px solid var(--sail-700)',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}>
              <div className="flex-between">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--sail-300)' }}>
                  <span className="spinner" />
                  <span>{auditPhase || 'Synthesizing mathematical derivation & empirical proofs…'}</span>
                </div>
              </div>
              <div className="skel" style={{ height: 18, width: '45%' }} />
              <div className="skel" style={{ height: 14, width: '90%' }} />
              <div className="skel" style={{ height: 14, width: '75%' }} />
              <div className="skel" style={{ height: 48, width: '100%' }} />
            </div>
          )}

          {/* Response Box with Rich KaTeX Math & Data Term Popovers */}
          {response && !loading && (
            <div
              style={{
                backgroundColor: 'var(--sail-800)',
                borderRadius: 8,
                padding: '20px 22px',
                border: '1px solid var(--sail-700)',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: 12,
                  marginBottom: 14,
                  borderBottom: '1px solid var(--sail-700)',
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    color: 'var(--badge-measured-text)',
                    letterSpacing: '0.06em',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span style={{ fontSize: 13 }}>✓</span> Auditor Synthesis & Empirical Proof
                </div>
                <button
                  type="button"
                  onClick={handleCopy}
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--sail-700)',
                    borderRadius: 4,
                    color: copied ? 'var(--badge-measured-text)' : 'var(--sail-300)',
                    fontSize: 11,
                    padding: '3px 8px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    fontFamily: 'var(--f-mono)',
                    transition: 'all 0.12s ease',
                  }}
                >
                  <span>{copied ? '✓ Copied' : '⧉ Copy Proof'}</span>
                </button>
              </div>

              <div
                className="chat-markdown"
                style={{
                  fontSize: 13.5,
                  lineHeight: 1.75,
                  color: 'var(--sail-100)',
                }}
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }], rehypeUnescapeCurrency]}
                  components={{
                    p({ children, ...props }) {
                      return <p {...props}>{highlightDataTerms(children)}</p>;
                    },
                    li({ children, ...props }) {
                      return <li {...props}>{highlightDataTerms(children)}</li>;
                    },
                    td({ children, ...props }) {
                      return <td {...props}>{highlightDataTerms(children)}</td>;
                    },
                    th({ children, ...props }) {
                      return <th {...props}>{highlightDataTerms(children)}</th>;
                    },
                    strong({ children, ...props }) {
                      return <strong {...props}>{highlightDataTerms(children)}</strong>;
                    },
                    em({ children, ...props }) {
                      return <em {...props}>{highlightDataTerms(children)}</em>;
                    },
                    code({ className, children, ...props }) {
                      const text = String(children).replace(/\n$/, '').trim();
                      const def = findDataSource(text);
                      if (def) {
                        return <DataTermToken term={text} definition={def}>{text}</DataTermToken>;
                      }
                      return <code className={className} {...props}>{children}</code>;
                    },
                  }}
                >
                  {preprocessMathematicalMarkdown(response)}
                </ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default HypothesisAuditor;


