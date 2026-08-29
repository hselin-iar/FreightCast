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

const EXAMPLE_QUERIES = [
  'What\'s the best vessel for 70,000 MT from Australia to Paradip?',
  'Should I lock in three voyages or keep buying spot?',
  'What if I can\'t use a Capesize and need this done in 12 days?',
  'Why are you recommending Panamax?',
  'What will the Panamax rate be in 2 weeks?',
];

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
    <div className="panel" id="chat-panel" style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      minHeight: 420,
    }}>
      {/* Header */}
      <div className="panel-hd" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: 'linear-gradient(135deg, var(--accent) 0%, var(--indigo-hi) 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, flexShrink: 0,
          }}>✦</div>
          <div>
            <div className="panel-title">Decision Assistant</div>
            <div className="panel-meta" style={{ marginTop: 1 }}>
              Powered by Claude · tool-calling · server-side key
            </div>
          </div>
        </div>
        {isThinking && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className="spinner" />
            <span style={{ fontSize: 11, color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>
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
            <p style={{ fontSize: 12, color: 'var(--sail-400)', margin: '0 0 4px' }}>
              Ask about any cargo scenario — the assistant calls the same engine as the dashboard.
            </p>
            {EXAMPLE_QUERIES.map(q => (
              <button key={q} onClick={() => handleExampleClick(q)}
                className="example-query-btn"
                style={{
                  background: 'rgba(13,148,136,0.07)',
                  border: '1px solid var(--sail-800)',
                  borderRadius: 6,
                  padding: '6px 10px',
                  textAlign: 'left',
                  fontSize: 11.5,
                  color: 'var(--sail-300)',
                  cursor: 'pointer',
                  transition: 'background 0.15s, border-color 0.15s',
                }}
                onMouseEnter={e => {
                  (e.target as HTMLButtonElement).style.background = 'rgba(13,148,136,0.14)';
                  (e.target as HTMLButtonElement).style.borderColor = 'var(--accent-20)';
                }}
                onMouseLeave={e => {
                  (e.target as HTMLButtonElement).style.background = 'rgba(13,148,136,0.07)';
                  (e.target as HTMLButtonElement).style.borderColor = 'var(--sail-800)';
                }}
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
        borderTop: '1px solid var(--sail-800)',
        padding: '10px 12px',
        display: 'flex',
        gap: 8,
        alignItems: 'flex-end',
        flexShrink: 0,
        background: 'rgba(15,23,42,0.4)',
      }}>
        <textarea
          ref={textareaRef}
          id="chat-input"
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask a chartering question… (Enter to send, Shift+Enter for newline)"
          disabled={isThinking}
          rows={1}
          style={{
            flex: 1,
            background: 'var(--sail-900)',
            border: `1px solid ${isThinking ? 'var(--sail-800)' : 'var(--sail-700)'}`,
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
              ? 'var(--sail-800)'
              : 'linear-gradient(135deg, var(--accent) 0%, var(--indigo-hi) 100%)',
            border: 'none',
            borderRadius: 8,
            padding: '9px 14px',
            color: isThinking || !input.trim() ? 'var(--sail-500)' : '#fff',
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

      {/* Honesty footer */}
      <div style={{
        padding: '5px 14px 7px',
        fontSize: 10,
        color: 'var(--sail-600)',
        fontFamily: 'var(--f-mono)',
        borderTop: '1px solid var(--sail-900)',
        flexShrink: 0,
      }}>
        Every number in the reply is from a tool call · never estimated
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
          ? 'linear-gradient(135deg, rgba(13,148,136,0.35) 0%, rgba(99,102,241,0.2) 100%)'
          : msg.error
            ? 'rgba(239,68,68,0.12)'
            : 'rgba(30,41,59,0.7)',
        border: `1px solid ${
          isUser ? 'rgba(13,148,136,0.3)'
          : msg.error ? 'rgba(239,68,68,0.3)'
          : 'var(--sail-800)'}`,
        fontSize: 12.5,
        lineHeight: 1.55,
        color: msg.error ? '#fca5a5' : 'var(--sail-100)',
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
          background: 'rgba(13,148,136,0.1)',
          border: '1px solid rgba(13,148,136,0.25)',
          borderRadius: 6,
          fontSize: 10.5,
          color: 'var(--accent-hi)',
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
