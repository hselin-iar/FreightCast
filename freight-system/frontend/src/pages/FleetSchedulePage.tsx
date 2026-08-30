import React, { useEffect, useState } from 'react';
import { getFleetSchedule } from '../lib/apiClient';
import type { FleetScheduleResponse } from '../lib/types';
import ProvenanceBadge from '../components/ProvenanceBadge';

function fmtK(n: number) {
  if (Math.abs(n) >= 1_000_000) return '$' + (n / 1_000_000).toFixed(2) + 'M';
  if (Math.abs(n) >= 1_000) return '$' + Math.round(n / 1_000) + 'k';
  return '$' + Math.round(n);
}

function fmtDate(d?: string) {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return d;
  }
}

const FleetSchedulePage: React.FC = () => {
  const [data, setData] = useState<FleetScheduleResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    const fetchSchedule = async () => {
      setLoading(true);
      setError(null);
      const res = await getFleetSchedule();
      if (res.data) {
        setData(res.data);
      } else if (res.error) {
        setError(res.error.message);
      }
      setLoading(false);
    };

    fetchSchedule();
  }, []);

  const filteredVessels = React.useMemo(() => {
    if (!data?.vessel_schedule) return [];
    return data.vessel_schedule.filter((v) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const origin = (v.origin || '').toLowerCase();
        const dest = (v.destination || '').toLowerCase();
        const vessel = (v.vessel_name || '').toLowerCase();
        const cid = (v.contract_id || '').toLowerCase();
        if (!origin.includes(q) && !dest.includes(q) && !vessel.includes(q) && !cid.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [data, searchQuery]);

  if (loading) {
    return (
      <div className="panel" style={{ padding: '4rem', textAlign: 'center' }}>
        <div style={{ fontSize: '1.75rem', marginBottom: '0.75rem' }}>⏳ Initializing Fleet Data…</div>
        <div style={{ color: 'var(--sail-400)', fontFamily: 'var(--f-mono)' }}>
          Retrieving active vessel schedules and AIS data
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="panel" style={{ padding: '2.5rem', borderColor: 'var(--warn)' }}>
        <div style={{ fontSize: '1.25rem', color: '#f87171', fontWeight: 700, marginBottom: '0.5rem' }}>
          ⚠️ Unable to Load Fleet Data
        </div>
        <div style={{ color: 'var(--sail-300)', marginBottom: '1rem' }}>{error ?? 'Unknown error loading data.'}</div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <div className="panel" style={{ padding: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--sail-100)', letterSpacing: '-0.02em', marginBottom: '0.4rem' }}>
            Fleet Portfolio
          </h2>
          <div style={{ fontSize: '0.85rem', color: 'var(--sail-400)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>Live schedule for <strong>{data.summary.sail_vessels} assigned vessels</strong>.</span>
            <ProvenanceBadge provenance="measured" note="Based on live AIS positioning and firm contract schedules." />
          </div>
        </div>
        
        <input
          type="text"
          className="input-field"
          placeholder="Search vessel, port, ID…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ width: '250px', padding: '8px 12px', fontSize: '13px' }}
        />
      </div>

      <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: 'color-mix(in srgb, var(--sail-800) 80%, transparent)', borderBottom: '1px solid var(--sail-800)' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left' }}>Vessel</th>
                <th style={{ padding: '12px 16px', textAlign: 'left' }}>Assigned Contract</th>
                <th style={{ padding: '12px 16px', textAlign: 'left' }}>Current Route</th>
                <th style={{ padding: '12px 16px', textAlign: 'right' }}>Parcel Volume</th>
                <th style={{ padding: '12px 16px', textAlign: 'center' }}>Schedule (Dep / ETA)</th>
                <th style={{ padding: '12px 16px', textAlign: 'right' }}>Expected Margin</th>
              </tr>
            </thead>
            <tbody>
              {filteredVessels.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--sail-500)' }}>
                    No vessels found matching your search.
                  </td>
                </tr>
              ) : (
                filteredVessels.map((v, idx) => (
                  <tr
                    key={`${v.imo}-${v.contract_id}-${idx}`}
                    style={{
                      borderBottom: '1px solid color-mix(in srgb, var(--sail-700) 40%, transparent)',
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'color-mix(in srgb, var(--sail-800) 50%, transparent)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    {/* Vessel Details */}
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 700, color: 'var(--text-accent)' }}>{v.vessel_name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--sail-500)', fontFamily: 'var(--f-mono)' }}>
                        IMO: {v.imo}
                      </div>
                    </td>

                    {/* Contract */}
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)' }}>
                        {v.contract_id}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--sail-400)' }}>
                        Seq #{v.voyage_sequence}
                      </div>
                    </td>

                    {/* Route */}
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--sail-200)' }}>
                        {v.origin ? v.origin.split(',')[0] : 'Origin'}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--sail-400)' }}>
                        ➔ {v.destination ? v.destination.split(',')[0] : 'Destination'}
                      </div>
                    </td>

                    {/* Volume */}
                    <td style={{ padding: '12px 16px', textAlign: 'right', fontFamily: 'var(--f-mono)' }}>
                      <span style={{ fontWeight: 600, color: 'var(--sail-200)' }}>
                        {v.contract_volume_mt ? Math.round(Number(v.contract_volume_mt)).toLocaleString() : '—'}
                      </span>{' '}
                      <span style={{ fontSize: '10px', color: 'var(--sail-500)' }}>MT</span>
                    </td>

                    {/* Window */}
                    <td style={{ padding: '12px 16px', textAlign: 'center', fontSize: '11px', fontFamily: 'var(--f-mono)' }}>
                      {v.departure_date ? (
                        <>
                          <div style={{ color: 'var(--sail-300)' }}>🛫 {fmtDate(v.departure_date)}</div>
                          <div style={{ color: 'var(--sail-400)' }}>🛬 {fmtDate(v.estimated_eta)}</div>
                        </>
                      ) : (
                        <span style={{ color: 'var(--sail-600)' }}>—</span>
                      )}
                    </td>

                    {/* Margin */}
                    <td style={{ padding: '12px 16px', textAlign: 'right', fontFamily: 'var(--f-mono)' }}>
                      <div style={{ fontWeight: 700, color: 'var(--emerald-4)' }}>
                        {v.expected_incremental > 0 ? `+${fmtK(v.expected_incremental)}` : fmtK(v.expected_incremental)}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default FleetSchedulePage;
