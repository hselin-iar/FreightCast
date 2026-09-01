/**
 * App.tsx — top-level shell with 5 nav tabs:
 *   Recommendation | Forecast Explorer | Port Constraints | Scenario Lab | Data Provenance
 *
 * DOC3: "App.tsx is the top-level shell; all backend calls go through apiClient.ts."
 * - Nav bar health status pulled from GET /health (real data, never hardcoded)
 * - ChatPanel persists across tab switches so conversation history is preserved
 * - Recommendation tab renders in a 2-column grid with ChatPanel as sticky sidebar
 */
import React, { useCallback, useEffect, useState } from 'react';
import ChatPanel from './components/ChatPanel';
import { getHealth } from './lib/apiClient';
import type { HealthResponse, RecommendationRequest, RecommendationResponse } from './lib/types';
import faviconUrl from './assets/favicon.png';
import ForecastExplorerPage from './pages/ForecastExplorerPage';
import PortConstraintsPage from './pages/PortConstraintsPage';
import RecommendationPage from './pages/RecommendationPage';
import FleetSchedulePage from './pages/FleetSchedulePage';

type View = 'recommendation' | 'fleet' | 'forecast' | 'ports' | 'scenario' | 'provenance';

/* ── Placeholder for tabs not yet built as live pages ───────── */
function PlaceholderView({ title, meta }: { title: string; meta: string }) {
  return (
    <div className="page-grid">
      <div className="col-12">
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">{title}</span>
            <span className="panel-meta">{meta}</span>
          </div>
          <div className="empty-state">
            <div className="empty-icon">⬡</div>
            <div className="empty-title">{title}</div>
            <div className="empty-desc">
              This view is implemented in Build Step 15. Core form and results are fully functional on the Recommendation tab.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── App shell ─────────────────────────────────────────── */
const TABS: { id: View; label: string }[] = [
  { id: 'recommendation', label: 'Recommendation' },
  { id: 'forecast',       label: 'Forecast'        },
  { id: 'ports',          label: 'Ports'           },
  { id: 'provenance',     label: 'Provenance'      },
  { id: 'fleet',          label: 'Fleet'           },
];

const App: React.FC = () => {
  const [view,   setView]   = useState<View>('recommendation');
  const [health, setHealth] = useState<HealthResponse | null>(null);

  // Fetch health on mount + every 60 seconds for nav bar status
  useEffect(() => {
    const poll = async () => {
      const { data } = await getHealth();
      if (data) setHealth(data);
    };
    poll();
    const id = setInterval(poll, 60_000);
    return () => clearInterval(id);
  }, []);

  /**
   * Shared chatbot ↔ dashboard bridge (DOC2 §3c / DOC3 §FEATURE: Chatbot).
   * chatCargoContext: last form submission → passed to ChatPanel as cargo_context
   * chatResult:       re-solved result from ChatPanel → pushed into RecommendationPage
   * chatNote:         constraint annotation for "changed because you asked" banner
   */
  const [chatCargoContext, setChatCargoContext] = useState<RecommendationRequest | null>(null);
  const [chatResult,       setChatResult]       = useState<RecommendationResponse | null>(null);
  const [chatNote,         setChatNote]         = useState<string | null>(null);

  const handleDashboardUpdate = useCallback(
    (result: RecommendationResponse, note: string | null) => {
      setChatResult(result);
      setChatNote(note);
      setView('recommendation');
    },
    [],
  );

  const lastRetrainLabel = health?.last_retrain_at
    ? `Forecast gen: ${new Date(health.last_retrain_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })} IST`
    : null;

  const bunkerUpdatedLabel = health?.bunker_last_updated
    ? `Bunker: ${new Date(health.bunker_last_updated).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })} IST`
    : null;

  // AIS is considered "live" only if last seen within the past 60 minutes.
  // A stale timestamp from days ago is NOT live — show it as warn.
  const AIS_STALE_THRESHOLD_MS = 60 * 60 * 1000; // 60 minutes
  const aisLastSeen = health?.ais_listener_last_seen ? new Date(health.ais_listener_last_seen) : null;
  const aisIsRecent = aisLastSeen ? (Date.now() - aisLastSeen.getTime() < AIS_STALE_THRESHOLD_MS) : false;
  const aisStatus = health ? (aisIsRecent ? 'ok' : 'warn') : 'ok';
  const aisLabel  = !health ? 'AIS …'
    : aisIsRecent    ? 'AIS live'
    : aisLastSeen    ? 'AIS stale'
    : 'AIS offline';
  const dbStatus = health ? (health.warehouse_reachable ? 'ok' : 'warn') : 'ok';

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* ── Top nav ── */}
      <header className="nav-bar">
        <img src={faviconUrl} alt="FreightCast Logo" style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0, objectFit: 'contain' }} />
        <span className="nav-brand">
          FreightCast
        </span>

        <nav className="nav-tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              className={`nav-tab ${view === tab.id ? 'active' : ''}`}
              onClick={() => setView(tab.id)}
              id={`nav-${tab.id}`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="nav-right">
          {/* AIS status — live only if seen within last 60 min */}
          <span className="flex-center gap-1" title={aisLastSeen ? `Last seen: ${aisLastSeen.toLocaleString()}` : 'Never seen'}>
            <span className={`status-dot ${aisStatus}`} />
            {aisLabel}
          </span>
          {/* Warehouse status */}
          <span className="flex-center gap-1">
            <span className={`status-dot ${dbStatus}`} />
            {health ? (health.warehouse_reachable ? 'DB ok' : 'DB degraded') : 'DB ok'}
          </span>
        </div>
      </header>

      {/* ── View panels ── */}
      <div style={{ flex: 1 }}>
        {/* Recommendation + ChatPanel side-by-side
            ChatPanel persists (display:none vs unmount) so conversation history survives tab switches */}
        <div style={{
          display: view === 'recommendation' ? 'grid' : 'none',
          gridTemplateColumns: '1fr 320px',
          height: '100%',
        }}>
          <RecommendationPage
            onCargoContextChange={setChatCargoContext}
            externalResult={chatResult}
            chatConstraintNote={chatNote}
          />
          <div style={{
            borderLeft: '1px solid var(--ink-600)',
            background: 'var(--ink-700)',
            padding: '0',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            height: 'calc(100vh - 52px)',
            position: 'sticky',
            top: 52,
            overflowY: 'auto',
          }}>
            <ChatPanel
              cargoContext={chatCargoContext}
              onDashboardUpdate={handleDashboardUpdate}
            />
          </div>
        </div>

        {view === 'fleet'      && <div style={{ padding: '1.5rem', maxWidth: '1400px', margin: '0 auto' }}><FleetSchedulePage /></div>}
        {view === 'forecast'   && <ForecastExplorerPage />}
        {view === 'ports'      && <PortConstraintsPage />}
        {view === 'provenance' && <PlaceholderView title="Data Provenance" meta="Full audit trail · Build Step 12" />}
      </div>
    </div>
  );
};

export default App;
