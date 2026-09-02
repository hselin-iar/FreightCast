/**
 * ChatPanel.tsx — Decision Assistant chatbot panel.
 *
 * DOC3 §FEATURE: Chatbot / DOC2 §3b, §3c, §16.2
 *
 * Architecture:
 *  - All backend calls via postChat() from apiClient.ts — no direct fetch().
 *  - conversation_history is shipped to the server each turn; the server echoes
 *    back the updated history. Zero server-side session state.
 *  - cargo_context = the last RecommendationRequest from the dashboard form,
 *    passed in as a prop so the chatbot can resolve "what if I can't use a
 *    Capesize" follow-ups without re-asking for cargo/origin/destination.
 *  - onDashboardUpdate fires when the server returns an updated_recommendation
 *    (i.e. a genuine re-solve from a constraint-change message — DOC2 §3c step 4).
 *    RecommendationPage re-renders with the new plan + "changed because you asked" note.
 *  - AbortController cancels in-flight Claude turns if the user sends a follow-up
 *    before the previous one completes.
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { postChat } from '../lib/apiClient';
import type {
  ChatMessage,
  RecommendationRequest,
  RecommendationResponse,
} from '../lib/types';

/* ═══════════════════════════════════════════════════════════
   Types
═══════════════════════════════════════════════════════════ */

interface UiMessage {
  id:        string;
  role:      'user' | 'assistant' | 'system';
  content:   string;
  /** True while the assistant is waiting for Claude + the tool call. */
  loading?:  boolean;
  /** True when this assistant turn triggered a dashboard update. */
  updated?:  boolean;
  constraintNote?: string;
  toolCalled?: boolean;
  error?:    string;
}

interface Props {
  /** Last cargo_request submitted via the dashboard form. */
  cargoContext:    RecommendationRequest | null;
  /** Fired when a re-solve happens — updates the open RecommendationPage. */
  onDashboardUpdate: (result: RecommendationResponse, constraintNote: string | null) => void;
}

/* ═══════════════════════════════════════════════════════════
   Example prompts shown on empty state
═══════════════════════════════════════════════════════════ */



/* ═══════════════════════════════════════════════════════════
   Helpers
═══════════════════════════════════════════════════════════ */

function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

function TypingDots() {
  return (
    <span style={{ display: 'inline-flex', gap: 3, alignItems: 'center', height: 14 }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 5, height: 5, borderRadius: '50%',
          background: 'var(--accent)',
          animation: `typingDot 1.2s ${i * 0.2}s ease-in-out infinite`,
          display: 'inline-block',
        }} />
      ))}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════
   ChatPanel component
═══════════════════════════════════════════════════════════ */

const ChatPanel: React.FC<Props> = ({ cargoContext, onDashboardUpdate }) => {
  const [messages,    setMessages]    = useState<UiMessage[]>([]);
  const [history,     setHistory]     = useState<ChatMessage[]>([]);
  const [input,       setInput]       = useState('');
  const [isThinking,  setIsThinking]  = useState(false);
  const bottomRef    = useRef<HTMLDivElement>(null);
  const abortRef     = useRef<AbortController | null>(null);
  const textareaRef  = useRef<HTMLTextAreaElement>(null);

  const exampleQueries = cargoContext
    ? [
        `What's the best vessel for ${cargoContext.cargo_quantity.toLocaleString()} MT from ${cargoContext.origin_port} to ${cargoContext.discharge_ports[0] ?? 'destination'}?`,
        `Should I lock in voyages or keep buying spot?`,
        `What if I can't use a Capesize and need this done in ${cargoContext.timing_flexibility_days} days?`,
        `Why are you recommending this vessel?`,
        `What will the rate be in 2 weeks?`
      ]
    : [
        'How do I use this dashboard?',
        'What does the robustness score mean?',
        'How is the predicted freight rate calculated?',
        'What vessel classes are supported?',
        'Where does the AIS data come from?'
      ];

  /* Auto-scroll to bottom on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /* Auto-resize textarea */
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  };

  const send = useCallback(async (text: string) => {
    if (!text.trim() || isThinking) return;
    const userMsg: UiMessage = { id: uid(), role: 'user', content: text.trim() };
    const thinkingMsg: UiMessage = { id: uid(), role: 'assistant', content: '', loading: true };

    setMessages(prev => [...prev, userMsg, thinkingMsg]);
    setInput('');
    setIsThinking(true);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    /* Cancel any previous in-flight request */
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const { data, error } = await postChat(
      {
        message:              text.trim(),
        conversation_history: history,
        cargo_context:        cargoContext ?? undefined,
      },
      ctrl.signal,
    );

    setIsThinking(false);

    if (data === null && error === null) {
      /* Aborted by a subsequent send — remove the thinking bubble */
      setMessages(prev => prev.filter(m => m.id !== thinkingMsg.id));
      return;
    }

    if (error || !data) {
      setMessages(prev => prev.map(m =>
        m.id === thinkingMsg.id
          ? { ...m, loading: false, error: error?.message ?? 'Unknown error' }
          : m
      ));
      return;
    }

    /* Dashboard update — fire before updating chat so the plan switches atomically */
    if (data.updated_recommendation) {
      onDashboardUpdate(data.updated_recommendation, data.constraint_note ?? null);
    }

    /* Update the thinking bubble with the real reply */
    setMessages(prev => prev.map(m =>
      m.id === thinkingMsg.id
        ? {
            ...m,
            content:        data.reply,
            loading:        false,
            updated:        !!data.updated_recommendation,
            constraintNote: data.constraint_note ?? undefined,
            toolCalled:     data.tool_called,
          }
        : m
    ));

    setHistory(data.conversation_history);
  }, [isThinking, history, cargoContext, onDashboardUpdate]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  const handleExampleClick = (q: string) => { send(q); };

  /* ── Render ─────────────────────────────────────────────── */

  return (
    <div id="chat-panel" style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      minHeight: 420,
    }}>
      {/* Header — charcoal grey with yellow accent stripe */}
      <div style={{
        flexShrink: 0,
        background: 'var(--ink-800)',
        borderBottom: '1px solid var(--ink-600)',
        padding: '14px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, flexShrink: 0, color: 'var(--accent-text)',
          }}>✦</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-hi)', letterSpacing: '-0.2px' }}>Chartering Agent</div>
          </div>
        </div>
        {isThinking && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className="spinner" />
            <span style={{ fontSize: 11, color: 'var(--sail-500)', fontFamily: 'var(--f-mono)' }}>
              thinking…
            </span>
          </div>
        )}
      </div>

      {/* Message thread */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}>
        {/* Empty state */}
        {messages.length === 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
            <p style={{ fontSize: 13, color: '#FAFAFA', margin: '0 0 4px', fontWeight: 500 }}>
              Ask about any cargo scenario.
            </p>
            {exampleQueries.map(q => (
              <button key={q} onClick={() => handleExampleClick(q)}
                className="example-query-btn"
                style={{}}
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Messages */}
        {messages.map(msg => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div style={{
        padding: '10px 12px',
        display: 'flex',
        gap: 8,
        alignItems: 'flex-end',
        flexShrink: 0,
        background: 'var(--ink-800)',
        borderTop: '1px solid var(--ink-600)',
      }}>
        <textarea
          ref={textareaRef}
          id="chat-input"
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything..."
          disabled={isThinking}
          rows={1}
          style={{
            flex: 1,
            background: 'var(--ink-700)',
            border: '1px solid var(--ink-600)',
            borderRadius: 8,
            padding: '8px 11px',
            fontSize: 13,
            color: 'var(--sail-100)',
            resize: 'none',
            outline: 'none',
            fontFamily: 'var(--f-sans)',
            lineHeight: 1.5,
            overflow: 'hidden',
            transition: 'border-color 0.15s',
          }}
          onFocus={e => { e.target.style.borderColor = 'var(--accent)'; }}
          onBlur={e => { e.target.style.borderColor = isThinking ? 'var(--sail-800)' : 'var(--sail-700)'; }}
        />
        <button
          id="chat-send-btn"
          onClick={() => send(input)}
          disabled={isThinking || !input.trim()}
          style={{
            background: isThinking || !input.trim()
              ? 'var(--ink-700)'
              : 'var(--accent)',
            border: 'none',
            borderRadius: 8,
            padding: '9px 14px',
            color: isThinking || !input.trim() ? '#6b7280' : 'var(--accent-text)',
            cursor: isThinking || !input.trim() ? 'not-allowed' : 'pointer',
            fontSize: 15,
            lineHeight: 1,
            transition: 'background 0.15s, color 0.15s',
            flexShrink: 0,
          }}
          title="Send (Enter)"
        >
          ▶
        </button>
      </div>



      {/* Typing animation keyframes */}
      <style>{`
        @keyframes typingDot {
          0%, 80%, 100% { opacity: 0.2; transform: translateY(0); }
          40%            { opacity: 1;   transform: translateY(-3px); }
        }
      `}</style>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════
   MessageBubble — individual chat bubble
═══════════════════════════════════════════════════════════ */

const MessageBubble: React.FC<{ msg: UiMessage }> = ({ msg }) => {
  const isUser      = msg.role === 'user';
  const isAssistant = msg.role === 'assistant';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      gap: 4,
    }}>
      {/* Bubble */}
      <div style={{
        maxWidth: '92%',
        padding: '9px 13px',
        borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
        background: isUser
          ? 'var(--accent)'
          : msg.error
            ? 'color-mix(in srgb, var(--error, #ef4444) 12%, transparent)'
            : 'color-mix(in srgb, var(--ink-700) 8%, var(--sail-900))',
        border: `1px solid ${
          isUser ? 'var(--accent-dim, var(--accent))'
          : msg.error ? 'color-mix(in srgb, var(--error, #ef4444) 30%, transparent)'
          : 'var(--sail-800)'}`,
        lineHeight: 1.55,
        color: isUser ? '#1A1A1A' : msg.error ? '#fca5a5' : 'var(--sail-100)',
        wordBreak: 'break-word',
      }}>
        {msg.loading ? (
          <TypingDots />
        ) : msg.error ? (
          <span style={{ whiteSpace: 'pre-wrap' }}>{msg.error}</span>
        ) : (
          <div className="chat-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {msg.content}
            </ReactMarkdown>
          </div>
        )}
      </div>

      {/* "Updated dashboard" annotation — appears below assistant bubble */}
      {isAssistant && msg.updated && msg.constraintNote && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '3px 8px',
          background: 'color-mix(in srgb, var(--accent) 10%, transparent)',
          border: '1px solid color-mix(in srgb, var(--accent) 25%, transparent)',
          borderRadius: 6,
          fontSize: 10.5,
          color: 'var(--accent)',
          fontFamily: 'var(--f-mono)',
          maxWidth: '88%',
        }}>
          <span>↗</span>
          <span>Dashboard updated · changed because you asked: {msg.constraintNote}</span>
        </div>
      )}

      {/* Tool-call badge */}
      {isAssistant && !msg.loading && msg.toolCalled && !msg.error && (
        <div style={{
          fontSize: 9.5,
          color: 'var(--sail-600)',
          fontFamily: 'var(--f-mono)',
          paddingLeft: 2,
        }}>
          ✓ engine called · numbers grounded in tool result
        </div>
      )}
    </div>
  );
};

export default ChatPanel;
