import React, { useEffect, useState } from 'react';
import { getFleetStatus } from '../lib/apiClient';
import type { FleetStatusResponse, VesselClassEntry, LiveVesselStatus } from '../lib/types';
import ProvenanceBadge from '../components/ProvenanceBadge';

function fmtDate(d?: string) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return d;
  }
}

/* ── Canonical vessel class catalog card ───────────────────── */
function VesselClassCard({ vc }: { vc: VesselClassEntry }) {
  return (
    <div
      style={{
        borderRadius: '6px',
        padding: '12px',
        background: 'var(--sail-950)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        border: '1px solid transparent',
        transition: 'background 0.15s, border-color 0.15s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = 'var(--sail-900)';
        e.currentTarget.style.borderColor = 'var(--sail-800)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'var(--sail-950)';
        e.currentTarget.style.borderColor = 'transparent';
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 600, color: 'var(--sail-100)', fontSize: '0.95rem' }}>
          {vc.class_name}
        </div>
        <div style={{ color: 'var(--sail-500)', fontSize: '11px', fontFamily: 'var(--f-mono)' }}>
          {Math.round(vc.typical_capacity_tonnes).toLocaleString()} MT
        </div>
      </div>
      <div style={{ display: 'flex', gap: 16, fontSize: '11px', fontFamily: 'var(--f-mono)' }}>
        <div><span style={{ color: 'var(--sail-500)' }}>Draft:</span> {vc.draft_m}m</div>
        <div><span style={{ color: 'var(--sail-500)' }}>LOA:</span> {vc.loa_m}m</div>
        <div><span style={{ color: 'var(--sail-500)' }}>Beam:</span> {vc.beam_m}m</div>
      </div>
    </div>
  );
}

/* ── Live vessel row ────────────────────────────────────────── */
function LiveVesselRow({ v }: { v: LiveVesselStatus }) {
  return (
    <tr
      style={{
        borderBottom: '1px solid color-mix(in srgb, var(--sail-700) 40%, transparent)',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'color-mix(in srgb, var(--sail-800) 50%, transparent)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
    >
      <td style={{ padding: '12px 16px' }}>
        <div style={{ fontWeight: 700, color: 'var(--text-accent)' }}>{v.vessel_name || 'UNKNOWN'}</div>
        <div style={{ fontSize: '11px', color: 'var(--sail-500)', fontFamily: 'var(--f-mono)' }}>
          IMO: {v.imo}
        </div>
      </td>
      <td style={{ padding: '12px 16px' }}>
        <div style={{ fontWeight: 600, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)' }}>
          {v.vessel_class || 'Unknown'}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--sail-400)' }}>
          {v.dwt ? `${Math.round(v.dwt).toLocaleString()} DWT` : '—'}
        </div>
      </td>
      <td style={{ padding: '12px 16px', fontFamily: 'var(--f-mono)', fontSize: '12px', color: 'var(--sail-200)' }}>
        {v.current_lat?.toFixed(4) || '—'}, {v.current_lon?.toFixed(4) || '—'}
      </td>
      <td style={{ padding: '12px 16px', textAlign: 'right', fontFamily: 'var(--f-mono)' }}>
        <span style={{ fontWeight: 600, color: v.speed_knots > 0.5 ? 'var(--emerald-4)' : 'var(--warn)' }}>
          {v.speed_knots ? v.speed_knots.toFixed(1) : '0.0'}
        </span>{' '}
        <span style={{ fontSize: '10px', color: 'var(--sail-500)' }}>kn</span>
      </td>
      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: '11px', fontFamily: 'var(--f-mono)', color: 'var(--sail-300)' }}>
        {fmtDate(v.recorded_at)}
      </td>
      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
        <button
          className="btn-primary"
          style={{ padding: '4px 12px', fontSize: '11px', opacity: 0.8 }}
          onClick={() => alert(`Phase 3: Assign cargo to ${v.vessel_name}`)}
        >
          Assign
        </button>
      </td>
    </tr>
  );
}

/* ── Page ───────────────────────────────────────────────────── */
const FleetSchedulePage: React.FC = () => {
  const [data, setData] = useState<FleetStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      const res = await getFleetStatus();
      if (res.data) {
        setData(res.data);
      } else if (res.error) {
        setError(res.error.message);
      }
      setLoading(false);
    })();
  }, []);

  const filteredVessels = React.useMemo(() => {
    if (!data?.vessels) return [];
    if (!searchQuery.trim()) return data.vessels;
    const q = searchQuery.toLowerCase();
    return data.vessels.filter(v =>
      (v.vessel_name || '').toLowerCase().includes(q) ||
      (v.vessel_class || '').toLowerCase().includes(q) ||
      String(v.imo).includes(q)
    );
  }, [data, searchQuery]);

  if (loading) {
    return (
      <div className="panel" style={{ padding: '4rem', textAlign: 'center' }}>
        <div style={{ fontSize: '1.75rem', marginBottom: '0.75rem' }}>⏳ Connecting to Fleet…</div>
        <div style={{ color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>
          Retrieving vessel classes and live AIS positions
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel" style={{ padding: '2.5rem', borderColor: 'var(--warn)' }}>
        <div style={{ fontSize: '1.25rem', color: '#f87171', fontWeight: 700, marginBottom: '0.5rem' }}>
          ⚠️ Backend Unreachable
        </div>
        <div style={{ color: 'var(--sail-300)', marginBottom: '1rem' }}>
          Could not connect to the FreightCast API. Make sure the backend is running on <code>localhost:8000</code>.
        </div>
        <div style={{ fontFamily: 'var(--f-mono)', fontSize: '12px', color: 'var(--sail-500)' }}>{error}</div>
      </div>
    );
  }

  return (
    <div className="page-grid">
      {/* ── Left Column: Configuration & Meta ── */}
      <section className="col-3 col-space">
        <div className="panel panel-ink" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#FAFAFA', letterSpacing: '-0.02em', marginBottom: '0.4rem' }}>
              Fleet Portfolio
            </h2>
            <div style={{ fontSize: '0.85rem', color: '#9ca3af', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{
                  display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                  background: data?.ais_live ? 'var(--emerald-4)' : 'var(--warn)'
                }} />
                {data?.ais_live
                  ? `${data.vessels.length} vessels live via AIS`
                  : `AIS listener offline`}
              </div>
              <ProvenanceBadge
                provenance={data?.ais_live ? 'measured' : 'assumed'}
                note={data?.ais_live ? 'Based on live AIS positioning.' : 'Canonical vessel class specs from VesselSpec DB.'}
              />
            </div>
          </div>
          <input
            type="text"
            className="input-field"
            placeholder="Search vessel, class, IMO…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{ width: '100%', padding: '8px 12px', fontSize: '13px' }}
          />
        </div>

        {/* ── Section 1: Canonical Vessel Class Catalog ── */}
        <div className="panel">
          <div className="panel-hd">
            <span className="panel-title">Vessel Class Catalog</span>
          </div>
          <div className="panel-body" style={{ padding: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ fontSize: '11px', color: 'var(--sail-500)', marginBottom: '0.25rem', padding: '0 0.5rem' }}>
              Classes used by the MILP optimizer to make SAIL/KILL decisions.
            </div>
            {data?.vessel_classes?.map(vc => (
              <VesselClassCard key={vc.class_name} vc={vc} />
            ))}
          </div>
        </div>
      </section>

      {/* ── Right Column: Live AIS Vessel Tracking ── */}
      <section className="col-9 col-space">
        <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="panel-hd" style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--sail-800)' }}>
            <div>
              <span className="panel-title" style={{ fontSize: '1rem' }}>Live AIS Tracking</span>
              <div style={{ fontSize: '12px', color: 'var(--sail-500)', marginTop: 2, fontWeight: 400 }}>
                Real vessels observed inside monitored port geofences by the AIS listener.
              </div>
            </div>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'color-mix(in srgb, var(--sail-800) 80%, transparent)', borderBottom: '1px solid var(--sail-800)' }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left' }}>Vessel</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left' }}>Class / DWT</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left' }}>Location (Lat, Lon)</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right' }}>Speed</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right' }}>Last Seen</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center' }}>Assign</th>
                </tr>
              </thead>
              <tbody>
                {filteredVessels.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center' }}>
                      {searchQuery.trim() ? (
                        <span style={{ color: 'var(--sail-500)' }}>No vessels match your search.</span>
                      ) : (
                        <div>
                          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📡</div>
                          <div style={{ color: 'var(--sail-300)', fontWeight: 600, marginBottom: '0.25rem' }}>
                            AIS Listener Not Running
                          </div>
                          <div style={{ color: 'var(--sail-500)', fontSize: '12px', fontFamily: 'var(--f-mono)' }}>
                            Start the AIS listener to see real ships appear here as they enter monitored port regions.
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                ) : (
                  filteredVessels.map(v => <LiveVesselRow key={v.imo} v={v} />)
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
};

export default FleetSchedulePage;
