import React, { useEffect, useState, useMemo, useRef } from 'react';
import { getPortStatus, getVesselPositions, getPortConstraints } from '../lib/apiClient';
import type { PortStatusResponse, PortConstraintItem } from '../lib/types';
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps';
import geoData from '../assets/world-110m.json';
import ProvenanceBadge from '../components/ProvenanceBadge';

/* ── Fallback port coordinates if network fails ── */
const FALLBACK_PORTS: PortConstraintItem[] = [
  { name: 'Paradip', max_draft_m: 14.5, max_loa_m: 260, max_beam_m: 43, handling_rate_tpd: 40000, tidal_dependent: true, verified: true, source: 'measured', lat: 20.26, lon: 86.67, role: 'discharge', lightening_point: 'Dhamra' },
  { name: 'Gangavaram', max_draft_m: 18.5, max_loa_m: 300, max_beam_m: 50, handling_rate_tpd: 60000, tidal_dependent: false, verified: true, source: 'measured', lat: 17.62, lon: 83.24, role: 'discharge', lightening_point: '—' },
  { name: 'Dhamra', max_draft_m: 15.0, max_loa_m: 280, max_beam_m: 45, handling_rate_tpd: 50000, tidal_dependent: true, verified: true, source: 'measured', lat: 20.83, lon: 86.97, role: 'discharge', lightening_point: '—' },
  { name: 'Haldia', max_draft_m: 8.5, max_loa_m: 200, max_beam_m: 32, handling_rate_tpd: 15000, tidal_dependent: true, verified: true, source: 'measured', lat: 22.02, lon: 88.06, role: 'discharge', lightening_point: 'Sagar Island' },
  { name: 'Visakhapatnam', max_draft_m: 18.0, max_loa_m: 300, max_beam_m: 50, handling_rate_tpd: 55000, tidal_dependent: false, verified: true, source: 'measured', lat: 17.69, lon: 83.29, role: 'discharge', lightening_point: '—' },
  { name: 'Kamarajar (Ennore)', max_draft_m: 16.0, max_loa_m: 295, max_beam_m: 45, handling_rate_tpd: 45000, tidal_dependent: false, verified: true, source: 'measured', lat: 13.25, lon: 80.33, role: 'discharge', lightening_point: '—' },
  { name: 'Australia (Hay Point)', max_draft_m: 19.0, max_loa_m: 330, max_beam_m: 55, handling_rate_tpd: 80000, tidal_dependent: false, verified: true, source: 'measured', lat: -21.26, lon: 149.30, role: 'load', lightening_point: '—' },
  { name: 'South Africa (Richards Bay)', max_draft_m: 18.0, max_loa_m: 310, max_beam_m: 50, handling_rate_tpd: 70000, tidal_dependent: false, verified: true, source: 'measured', lat: -28.79, lon: 32.09, role: 'load', lightening_point: '—' },
  { name: 'Indonesia (East Kalimantan)', max_draft_m: 15.5, max_loa_m: 270, max_beam_m: 45, handling_rate_tpd: 45000, tidal_dependent: false, verified: true, source: 'measured', lat: -1.26, lon: 116.82, role: 'load', lightening_point: '—' },
];

/* ── Collision-free map label offsets tailored by geographical quadrant ── */
const PORT_LABEL_OFFSETS: Record<string, { dx: number; dy: number; anchor: 'start' | 'end' | 'middle' }> = {
  'Haldia':                      { dx: 10,  dy: -8, anchor: 'start' },
  'Dhamra':                      { dx: 11,  dy: -1, anchor: 'start' },
  'Paradip':                     { dx: 11,  dy: 10, anchor: 'start' },
  'Visakhapatnam':               { dx: -10, dy: -6, anchor: 'end'   },
  'Gangavaram':                  { dx: -10, dy: 9,  anchor: 'end'   },
  'Kamarajar (Ennore)':          { dx: -10, dy: 1,  anchor: 'end'   },
  'Australia (Hay Point)':       { dx: 10,  dy: 4,  anchor: 'start' },
  'South Africa (Richards Bay)': { dx: -10, dy: 2,  anchor: 'end'   },
  'Indonesia (East Kalimantan)': { dx: 10,  dy: 0,  anchor: 'start' },
};

const PortConstraintsPage: React.FC = () => {
  const [ports, setPorts] = useState<PortConstraintItem[]>(FALLBACK_PORTS);
  const [portStatuses, setPortStatuses] = useState<Record<string, PortStatusResponse>>({});
  const [vesselPositions, setVesselPositions] = useState<Record<string, any>>({});
  const [, setLoading] = useState<boolean>(true);
  const [selectedPortName, setSelectedPortName] = useState<string>('Paradip');
  const [roleFilter, setRoleFilter] = useState<'all' | 'discharge' | 'load'>('all');
  const [mapPosition, setMapPosition] = useState({ coordinates: [95, 5] as [number, number], zoom: 1.4 });
  const mapContainerRef = useRef<HTMLDivElement>(null);

  // Native non-passive wheel & pinch gesture listeners for trackpads and touchscreens
  useEffect(() => {
    const el = mapContainerRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const zoomMultiplier = e.ctrlKey ? Math.exp(-e.deltaY * 0.015) : (e.deltaY < 0 ? 1.08 : 0.92);
      setMapPosition(prev => ({
        ...prev,
        zoom: Math.min(6.0, Math.max(1.0, prev.zoom * zoomMultiplier)),
      }));
    };

    let initialDist = 0;
    let initialZoom = 1;

    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        initialDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
        initialZoom = mapPosition.zoom;
      }
    };

    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 2 && initialDist > 0) {
        e.preventDefault();
        const t1 = e.touches[0];
        const t2 = e.touches[1];
        const currentDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
        const factor = currentDist / initialDist;
        setMapPosition(prev => ({
          ...prev,
          zoom: Math.min(6.0, Math.max(1.0, initialZoom * factor)),
        }));
      }
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    el.addEventListener('touchstart', onTouchStart, { passive: false });
    el.addEventListener('touchmove', onTouchMove, { passive: false });

    return () => {
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
    };
  }, [mapPosition.zoom]);

  // Dredging & Capability Simulator States
  const [simDraft, setSimDraft] = useState<number>(14.5);
  const [simHandling, setSimHandling] = useState<number>(40000);
  const [simCargoMT, setSimCargoMT] = useState<number>(150000);

  // Fetch dynamic verified constraints from backend
  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      const res = await getPortConstraints();
      if (active && res.data && res.data.length > 0) {
        setPorts(res.data);
      }
      setLoading(false);
    })();
    return () => { active = false; };
  }, []);

  // Fetch live AIS port status & congestion
  useEffect(() => {
    let active = true;
    (async () => {
      const results = await Promise.all(ports.map(p => getPortStatus(p.name)));
      if (!active) return;
      const statusMap: Record<string, PortStatusResponse> = {};
      results.forEach((r, i) => {
        if (r.data) statusMap[ports[i].name] = r.data;
      });
      setPortStatuses(statusMap);
    })();
    return () => { active = false; };
  }, [ports]);

  // Fetch real AIS vessel coordinates every 5s
  useEffect(() => {
    let active = true;
    const fetchPositions = async () => {
      const res = await getVesselPositions();
      if (active && res.data) setVesselPositions(res.data);
    };
    fetchPositions();
    const interval = setInterval(fetchPositions, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  // Active selected port object
  const activePort = useMemo(() => {
    return ports.find(p => p.name === selectedPortName) || ports[0];
  }, [ports, selectedPortName]);

  // Sync simulator sliders when active port changes
  useEffect(() => {
    if (activePort) {
      setSimDraft(activePort.max_draft_m);
      setSimHandling(activePort.handling_rate_tpd);
    }
  }, [activePort]);

  const activeLiveStatus = portStatuses[selectedPortName];

  // Simulator Calculations
  const simMetrics = useMemo(() => {
    const capeFeasibleDirect = simDraft >= 18.0;
    const panamaxFeasible = simDraft >= 14.5;
    const supramaxFeasible = simDraft >= 12.8;

    const lighteningSaved = !capeFeasibleDirect ? 0 : 75000;
    const allowedLaytimeDays = (simCargoMT / Math.max(simHandling, 5000)) + 1.0;
    const dischargeDays = simCargoMT / Math.max(simHandling, 5000);
    const waitHours = activeLiveStatus?.avg_wait_hours || 24.0;
    const totalTimeAtPortDays = (waitHours / 24.0) + dischargeDays;

    const demurrageDays = Math.max(0, totalTimeAtPortDays - allowedLaytimeDays);
    const demurrageCostUsd = demurrageDays * 18000;

    return {
      capeFeasibleDirect,
      panamaxFeasible,
      supramaxFeasible,
      lighteningSaved,
      allowedLaytimeDays,
      dischargeDays,
      totalTimeAtPortDays,
      demurrageDays,
      demurrageCostUsd,
    };
  }, [simDraft, simHandling, simCargoMT, activeLiveStatus]);

  // Filtered port list
  const filteredPorts = useMemo(() => {
    if (roleFilter === 'discharge') return ports.filter(p => p.role === 'discharge');
    if (roleFilter === 'load') return ports.filter(p => p.role === 'load');
    return ports;
  }, [ports, roleFilter]);

  const handleZoomIn = () => {
    if (mapPosition.zoom >= 5.5) return;
    setMapPosition(pos => ({ ...pos, zoom: Math.min(6.0, pos.zoom * 1.35) }));
  };

  const handleZoomOut = () => {
    if (mapPosition.zoom <= 1.0) return;
    setMapPosition(pos => ({ ...pos, zoom: Math.max(1.0, pos.zoom / 1.35) }));
  };

  const handleResetView = () => {
    setMapPosition({ coordinates: [95, 5], zoom: 1.4 });
  };

  // Center map on selected port
  const handleSelectPort = (p: PortConstraintItem) => {
    setSelectedPortName(p.name);
    setMapPosition({ coordinates: [p.lon, p.lat], zoom: Math.max(mapPosition.zoom, 2.2) });
  };

  /* ── Dynamic Inverse Zoom Scaling for Map Markers ── */
  const z = Math.max(1.0, mapPosition.zoom);
  const zoomFactor = Math.pow(z, 1.35); // Power > 1 ensures screen radius shrinks as user zooms in
  const vesselDotR = Math.max(0.9, 3.2 / zoomFactor);
  const vesselStrokeR = Math.max(1.8, 6.0 / zoomFactor);
  const portPinR = Math.max(2.0, 5.5 / zoomFactor);
  const portPulseR = Math.max(4.5, 12.0 / zoomFactor);
  const fontScale = Math.max(7.0, Math.min(10.5, 9.0 / Math.pow(z, 0.4)));

  const vesselCountTotal = Object.keys(vesselPositions).length;

  return (
    <div className="page-grid">
      {/* ══════════════════════════════════════════════════════════════ */}
      {/* ── LEFT COLUMN: PORT CATALOG & HYDRODYNAMIC SPECS (col-4) ── */}
      {/* ══════════════════════════════════════════════════════════════ */}
      <div className="col-4 col-space">
        {/* Panel 1: Port Constraints Directory */}
        <section className="panel">
          <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="panel-title">Port Directory</span>
              <span className="panel-meta" style={{ marginLeft: 6 }}>{ports.length} ports</span>
            </div>
            {/* Filter Tabs */}
            <div style={{ display: 'flex', gap: 3, background: 'color-mix(in srgb, var(--sail-800) 40%, transparent)', padding: 2, borderRadius: 6, border: '1px solid var(--sail-800)' }}>
              {(['all', 'discharge', 'load'] as const).map(role => (
                <button
                  key={role}
                  onClick={() => setRoleFilter(role)}
                  style={{
                    padding: '3px 9px',
                    fontSize: 10.5,
                    fontWeight: 600,
                    textTransform: 'capitalize',
                    background: roleFilter === role ? '#ffffff' : 'transparent',
                    color: roleFilter === role ? 'var(--sail-100)' : 'var(--sail-400)',
                    borderRadius: 4,
                    border: 'none',
                    boxShadow: roleFilter === role ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.12s ease',
                  }}
                >
                  {role === 'all' ? 'All' : role === 'discharge' ? 'Discharge' : 'Load'}
                </button>
              ))}
            </div>
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 440, overflowY: 'auto' }}>
            {filteredPorts.map(port => {
              const isSelected = port.name === selectedPortName;
              const status = portStatuses[port.name];
              const queueCount = status?.vessel_count ?? 0;

              return (
                <div
                  key={port.name}
                  onClick={() => handleSelectPort(port)}
                  style={{
                    borderRadius: 'var(--r)',
                    padding: '12px 14px',
                    background: isSelected ? 'color-mix(in srgb, var(--accent) 10%, #ffffff)' : '#ffffff',
                    border: isSelected ? '1.5px solid var(--accent)' : '1px solid var(--sail-700)',
                    boxShadow: isSelected ? '0 2px 8px rgba(0, 0, 0, 0.05)' : '0 1px 3px rgba(0, 0, 0, 0.03)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontWeight: 700, color: 'var(--sail-100)', fontSize: 13.5 }}>
                        {port.name}
                      </span>
                    </div>
                    <span className={`badge ${port.role === 'discharge' ? 'badge-primary' : 'badge-assumed'}`} style={{ fontSize: 9.5 }}>
                      {port.role.toUpperCase()}
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 8, fontSize: 11.5 }}>
                    <div>
                      <div style={{ color: 'var(--sail-500)', fontSize: 10 }}>Draft</div>
                      <div style={{ fontWeight: 700, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)' }}>{port.max_draft_m}m</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--sail-500)', fontSize: 10 }}>LOA</div>
                      <div style={{ fontWeight: 600, color: 'var(--sail-200)', fontFamily: 'var(--f-mono)' }}>{port.max_loa_m}m</div>
                    </div>
                    <div>
                      <div style={{ color: 'var(--sail-500)', fontSize: 10 }}>Handling</div>
                      <div style={{ fontWeight: 700, color: '#047857', fontFamily: 'var(--f-mono)' }}>{Math.round(port.handling_rate_tpd / 1000)}k t/d</div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, paddingTop: 6, borderTop: '1px solid var(--sail-800)', fontSize: 11 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--sail-400)' }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: queueCount > 5 ? 'var(--warn)' : queueCount > 0 ? 'var(--emerald)' : 'var(--sail-500)' }} />
                      Queue: <strong style={{ color: queueCount > 5 ? 'var(--warn)' : queueCount > 0 ? '#047857' : 'var(--sail-300)' }}>{queueCount} ships</strong>
                    </span>
                    <span style={{ color: 'var(--sail-400)', fontFamily: 'var(--f-mono)', fontSize: 10.5 }}>
                      Avg wait: {status?.avg_wait_hours ? `${status.avg_wait_hours.toFixed(1)}h` : '—'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Panel 2: Selected Port Hydrodynamics Specs */}
        <section className="panel">
          <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="panel-title">Hydrodynamic Specs</span>
              <span className="panel-meta" style={{ marginLeft: 6 }}>{activePort.name}</span>
            </div>
            <ProvenanceBadge provenance="measured" note="Physical bathymetric survey and pilotage parameters from port authority records." />
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* Clean Spec Metric Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
              <div style={{ background: '#ffffff', padding: '10px 12px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--sail-500)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Max Allowable Draft
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)', marginTop: 2 }}>
                  {activePort.max_draft_m} meters
                </div>
              </div>

              <div style={{ background: '#ffffff', padding: '10px 12px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--sail-500)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Mechanical Handling
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#047857', fontFamily: 'var(--f-mono)', marginTop: 2 }}>
                  {activePort.handling_rate_tpd.toLocaleString()} TPD
                </div>
              </div>

              <div style={{ background: '#ffffff', padding: '10px 12px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--sail-500)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Max LOA / Beam
                </div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)', marginTop: 2 }}>
                  {activePort.max_loa_m}m / {activePort.max_beam_m}m
                </div>
              </div>

              <div style={{ background: '#ffffff', padding: '10px 12px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--sail-500)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Tidal Window Status
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: activePort.tidal_dependent ? '#b45309' : '#047857', marginTop: 3 }}>
                  {activePort.tidal_dependent ? 'Tidal Window ⚠' : 'All-Weather ✓'}
                </div>
              </div>
            </div>

            {/* Lightening point row */}
            <div style={{ background: '#ffffff', padding: '10px 14px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', fontSize: 12 }}>
              <span style={{ color: 'var(--sail-500)', fontWeight: 500 }}>Lightening Anchor Point:</span>{' '}
              <span style={{ fontWeight: 700, color: activePort.lightening_point !== '—' ? 'var(--text-accent)' : 'var(--sail-200)' }}>
                {activePort.lightening_point !== '—' ? activePort.lightening_point : 'None required (direct deepwater berth)'}
              </span>
            </div>

            <p className="infer" style={{ fontSize: 11, marginTop: 2 }}>
              Physical limits feed directly into MILP vessel class selection (x_iv) and lightening penalty logic (q_i · ℓ_ip).
            </p>
          </div>
        </section>
      </div>

      {/* ══════════════════════════════════════════════════════════════ */}
      {/* ── RIGHT COLUMN: GIS MAP & DREDGING SIMULATOR (col-8) ─────── */}
      {/* ══════════════════════════════════════════════════════════════ */}
      <div className="col-8 col-space">
        {/* Panel 1: Interactive GIS Maritime Corridor & AIS Geofence Map */}
        <section className="panel" style={{ overflow: 'hidden' }}>
          <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="panel-title">Global Maritime Corridor & Port Congestion Map</span>
              <span className="panel-meta" style={{ marginLeft: 6 }}>
                Live AIS geofences · Indian East Coast & Origin Hubs
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="badge badge-emerald" style={{ fontSize: 10 }}>
                {vesselCountTotal} bulk carriers tracked
              </span>
              <ProvenanceBadge provenance="measured" note="Live AIS vessel coordinates & verified port coordinates." />
            </div>
          </div>

          {/* Map Canvas with Floating Controls & Precision Inverse Scaling */}
          <div
            ref={mapContainerRef}
            style={{
              position: 'relative',
              height: 380,
              width: '100%',
              background: '#0a0f1d',
              touchAction: 'none',
            }}
          >
            {/* Zoom Controls */}
            <div
              style={{
                position: 'absolute',
                right: 14,
                top: 14,
                zIndex: 10,
                display: 'flex',
                flexDirection: 'column',
                gap: 5,
              }}
            >
              <button
                onClick={handleZoomIn}
                style={{
                  width: 32,
                  height: 32,
                  padding: 0,
                  fontWeight: 700,
                  fontSize: 16,
                  background: '#ffffff',
                  color: 'var(--sail-100)',
                  border: '1px solid var(--sail-700)',
                  borderRadius: 6,
                  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.2)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                title="Zoom In (+)"
              >
                +
              </button>
              <button
                onClick={handleZoomOut}
                style={{
                  width: 32,
                  height: 32,
                  padding: 0,
                  fontWeight: 700,
                  fontSize: 16,
                  background: '#ffffff',
                  color: 'var(--sail-100)',
                  border: '1px solid var(--sail-700)',
                  borderRadius: 6,
                  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.2)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                title="Zoom Out (−)"
              >
                −
              </button>
              <button
                onClick={handleResetView}
                style={{
                  width: 32,
                  height: 32,
                  padding: 0,
                  fontSize: 13,
                  background: '#ffffff',
                  color: 'var(--sail-100)',
                  border: '1px solid var(--sail-700)',
                  borderRadius: 6,
                  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.2)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                title="Reset View (⟲)"
              >
                ⟲
              </button>
            </div>

            {/* Map Legend */}
            <div
              style={{
                position: 'absolute',
                left: 14,
                bottom: 12,
                zIndex: 10,
                display: 'flex',
                gap: 12,
                padding: '6px 12px',
                background: 'rgba(10, 15, 29, 0.9)',
                borderRadius: 6,
                border: '1px solid rgba(255, 255, 255, 0.1)',
                fontSize: 10.5,
                color: '#94a3b8',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} /> Origin Hub
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} /> Clear Berth
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} /> Congested ({'>'}5)
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#38bdf8', display: 'inline-block' }} /> AIS Vessel
              </span>
            </div>

            <ComposableMap
              projection="geoMercator"
              projectionConfig={{ scale: 190, center: [95, 5] }}
              style={{ width: '100%', height: '100%' }}
            >
              <ZoomableGroup
                zoom={mapPosition.zoom}
                center={mapPosition.coordinates}
                onMoveEnd={pos => setMapPosition(pos)}
                minZoom={1}
                maxZoom={6}
              >
                <Geographies geography={geoData}>
                  {({ geographies }) =>
                    geographies.map(geo => (
                      <Geography
                        key={geo.rsmKey}
                        geography={geo}
                        fill="#182234"
                        stroke="#2e3c54"
                        strokeWidth={0.5 / z}
                        style={{
                          default: { outline: 'none' },
                          hover: { fill: '#223047', outline: 'none' },
                          pressed: { outline: 'none' },
                        }}
                      />
                    ))
                  }
                </Geographies>

                {/* Live Tracked AIS Vessels with Dynamic Scaling */}
                {Object.entries(vesselPositions).map(([vesselKey, pos]) => {
                  const lat = pos?.lat ?? pos?.current_lat;
                  const lon = pos?.lon ?? pos?.current_lon;
                  if (lat === undefined || lon === undefined) return null;
                  return (
                    <Marker key={vesselKey} coordinates={[lon, lat]}>
                      <circle r={vesselDotR} fill="#38bdf8" opacity={0.85} />
                      <circle r={vesselStrokeR} fill="none" stroke="#38bdf8" strokeWidth={0.6 / z} opacity={0.4} />
                    </Marker>
                  );
                })}

                {/* Port Markers & Geofences with Tailored De-collided Labels */}
                {ports.map(port => {
                  const isSelected = port.name === selectedPortName;
                  const isOrigin = port.role === 'load';
                  const status = portStatuses[port.name];
                  const vesselCount = status?.vessel_count || 0;
                  const geofenceRadius = Math.max(5.0, (11 + Math.min(vesselCount * 2.2, 16)) / zoomFactor);
                  const labelCfg = PORT_LABEL_OFFSETS[port.name] || { dx: 10, dy: -4, anchor: 'start' };
                  const pinColor = isOrigin ? '#f59e0b' : (vesselCount > 5 ? '#ef4444' : '#10b981');

                  return (
                    <Marker
                      key={port.name}
                      coordinates={[port.lon, port.lat]}
                      onClick={() => handleSelectPort(port)}
                      style={{ default: { cursor: 'pointer', outline: 'none' } }}
                    >
                      {/* Live Congestion Geofence Indicator */}
                      <circle
                        r={geofenceRadius}
                        fill={isOrigin ? 'none' : pinColor}
                        fillOpacity={0.12}
                        stroke={pinColor}
                        strokeWidth={1.0 / z}
                        strokeDasharray={isOrigin ? `${2 / z} ${2 / z}` : undefined}
                      />

                      {/* Selected Pulse Ring */}
                      {isSelected && (
                        <circle
                          r={portPulseR}
                          fill="none"
                          stroke="var(--accent)"
                          strokeWidth={1.4 / z}
                          opacity={0.85}
                        />
                      )}

                      {/* Core Port Pin */}
                      <circle
                        r={portPinR}
                        fill={pinColor}
                        stroke="#ffffff"
                        strokeWidth={1.2 / z}
                      />

                      {/* De-collided Label with Dark Backplate for readability */}
                      <text
                        x={labelCfg.dx / Math.pow(z, 0.4)}
                        y={labelCfg.dy / Math.pow(z, 0.4)}
                        textAnchor={labelCfg.anchor}
                        alignmentBaseline="central"
                        paintOrder="stroke"
                        stroke="#0a0f1d"
                        strokeWidth={2.5 / z}
                        strokeLinejoin="round"
                        style={{
                          fontFamily: 'var(--f-sans)',
                          fontSize: fontScale,
                          fill: isSelected ? 'var(--accent)' : '#e2e8f0',
                          fontWeight: isSelected ? 700 : 500,
                          pointerEvents: 'none',
                        }}
                      >
                        {port.name.replace(/\s*\(.*\)/, '')} {vesselCount > 0 ? `(${vesselCount})` : ''}
                      </text>
                    </Marker>
                  );
                })}
              </ZoomableGroup>
            </ComposableMap>
          </div>
        </section>

        {/* Panel 2: Port Dredging & Capability Simulator */}
        <section className="panel">
          <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span className="panel-title">Port Dredging & Capability Simulator</span>
              <span className="panel-meta" style={{ marginLeft: 6 }}>
                Active Port: <span style={{ color: 'var(--text-accent)', fontWeight: 600 }}>{selectedPortName}</span>
              </span>
            </div>
            <span className="badge badge-emerald" style={{ fontSize: 10 }}>Interactive Model</span>
          </div>

          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Sliders Grid — Clean, consistent with Recommendation WhatIfSliders */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
              {/* Draft Slider */}
              <div style={{ background: '#ffffff', padding: '14px 16px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--sail-300)' }}>Simulated Berth Draft</label>
                  <span style={{ fontFamily: 'var(--f-mono)', fontSize: 15, fontWeight: 700, color: 'var(--sail-100)' }}>
                    {simDraft.toFixed(1)} meters
                  </span>
                </div>
                <input
                  type="range"
                  min={10.0}
                  max={22.0}
                  step={0.1}
                  value={simDraft}
                  onChange={e => setSimDraft(parseFloat(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--sail-500)', marginTop: 3, fontFamily: 'var(--f-mono)' }}>
                  <span>10.0m (Handymax)</span>
                  <span style={{ color: 'var(--sail-400)' }}>Actual: {activePort.max_draft_m}m</span>
                  <span>22.0m (Chinamax)</span>
                </div>
              </div>

              {/* Handling Throughput Slider */}
              <div style={{ background: '#ffffff', padding: '14px 16px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--sail-300)' }}>Mechanical Handling Rate</label>
                  <span style={{ fontFamily: 'var(--f-mono)', fontSize: 15, fontWeight: 700, color: '#047857' }}>
                    {Math.round(simHandling).toLocaleString()} TPD
                  </span>
                </div>
                <input
                  type="range"
                  min={10000}
                  max={90000}
                  step={2500}
                  value={simHandling}
                  onChange={e => setSimHandling(parseInt(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--sail-500)', marginTop: 3, fontFamily: 'var(--f-mono)' }}>
                  <span>10k TPD</span>
                  <span style={{ color: 'var(--sail-400)' }}>Actual: {Math.round(activePort.handling_rate_tpd).toLocaleString()} TPD</span>
                  <span>90k TPD</span>
                </div>
              </div>
            </div>

            {/* Consignment Parcel Volume Test */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#ffffff', padding: '10px 16px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)' }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--sail-300)' }}>Test Consignment Parcel:</span>
              <div style={{ display: 'flex', gap: 8 }}>
                {[75000, 100000, 150000, 180000].map(vol => {
                  const active = simCargoMT === vol;
                  return (
                    <button
                      key={vol}
                      onClick={() => setSimCargoMT(vol)}
                      style={{
                        padding: '5px 14px',
                        fontSize: 11,
                        fontWeight: active ? 700 : 500,
                        background: active ? 'var(--accent)' : '#ffffff',
                        color: active ? '#1A1A1A' : 'var(--sail-300)',
                        border: active ? '1.5px solid var(--accent-dim)' : '1px solid var(--sail-700)',
                        borderRadius: 6,
                        boxShadow: active ? '0 1px 4px rgba(0,0,0,0.1)' : 'none',
                        cursor: 'pointer',
                        transition: 'all 0.12s ease',
                      }}
                    >
                      {vol / 1000}k MT
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Clearance Matrix */}
            <div>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--sail-500)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Vessel Class Clearance at {simDraft.toFixed(1)}m Draft
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                {/* Capesize */}
                <div
                  style={{
                    padding: '14px 16px',
                    borderRadius: 'var(--r)',
                    background: simMetrics.capeFeasibleDirect ? 'color-mix(in srgb, var(--emerald) 5%, #ffffff)' : 'color-mix(in srgb, var(--warn) 5%, #ffffff)',
                    border: '1px solid var(--sail-700)',
                    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--sail-100)' }}>Capesize (18.0m)</span>
                    <span className={`badge ${simMetrics.capeFeasibleDirect ? 'badge-emerald' : 'badge-warn'}`} style={{ fontSize: 9.5 }}>
                      {simMetrics.capeFeasibleDirect ? '✓ Direct' : '⚠️ Lighten'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11.5, color: simMetrics.capeFeasibleDirect ? '#047857' : '#b45309', fontWeight: 600 }}>
                    {simMetrics.capeFeasibleDirect ? 'Direct Clearance' : 'Lightening Required'}
                  </div>
                  <div style={{ fontSize: 10.5, color: 'var(--sail-500)', marginTop: 4 }}>
                    {simMetrics.capeFeasibleDirect ? 'Saves $75k mobilization' : 'Penalty: $75k + barge'}
                  </div>
                </div>

                {/* Panamax */}
                <div
                  style={{
                    padding: '14px 16px',
                    borderRadius: 'var(--r)',
                    background: simMetrics.panamaxFeasible ? 'color-mix(in srgb, var(--emerald) 5%, #ffffff)' : 'color-mix(in srgb, var(--warn) 5%, #ffffff)',
                    border: '1px solid var(--sail-700)',
                    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--sail-100)' }}>Panamax (14.5m)</span>
                    <span className={`badge ${simMetrics.panamaxFeasible ? 'badge-emerald' : 'badge-warn'}`} style={{ fontSize: 9.5 }}>
                      {simMetrics.panamaxFeasible ? '✓ Direct' : '⚠️ Exceeded'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11.5, color: simMetrics.panamaxFeasible ? '#047857' : '#b45309', fontWeight: 600 }}>
                    {simMetrics.panamaxFeasible ? 'Direct Clearance' : 'Draft Exceeded'}
                  </div>
                  <div style={{ fontSize: 10.5, color: 'var(--sail-500)', marginTop: 4 }}>
                    Standard 75k–85k MT parcel
                  </div>
                </div>

                {/* Supramax */}
                <div
                  style={{
                    padding: '14px 16px',
                    borderRadius: 'var(--r)',
                    background: simMetrics.supramaxFeasible ? 'color-mix(in srgb, var(--emerald) 5%, #ffffff)' : 'color-mix(in srgb, var(--warn) 5%, #ffffff)',
                    border: '1px solid var(--sail-700)',
                    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--sail-100)' }}>Supramax (12.8m)</span>
                    <span className={`badge ${simMetrics.supramaxFeasible ? 'badge-emerald' : 'badge-warn'}`} style={{ fontSize: 9.5 }}>
                      {simMetrics.supramaxFeasible ? '✓ Direct' : '⚠️ Exceeded'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11.5, color: simMetrics.supramaxFeasible ? '#047857' : '#b45309', fontWeight: 600 }}>
                    {simMetrics.supramaxFeasible ? 'Direct Clearance' : 'Draft Exceeded'}
                  </div>
                  <div style={{ fontSize: 10.5, color: 'var(--sail-500)', marginTop: 4 }}>
                    Geared self-discharge
                  </div>
                </div>
              </div>
            </div>

            {/* Turnaround & Demurrage Simulation Box — Clean 4-card metric grid */}
            <div>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--sail-500)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Turnaround & Demurrage Exposure ({simCargoMT.toLocaleString()} MT Cargo)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
                <div style={{ background: '#ffffff', padding: '12px 14px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                  <div style={{ color: 'var(--sail-500)', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Discharge Time
                  </div>
                  <div style={{ fontWeight: 700, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)', fontSize: 16, marginTop: 4 }}>
                    {simMetrics.dischargeDays.toFixed(1)} Days
                  </div>
                </div>

                <div style={{ background: '#ffffff', padding: '12px 14px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                  <div style={{ color: 'var(--sail-500)', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Allowed Laytime
                  </div>
                  <div style={{ fontWeight: 700, color: 'var(--sail-100)', fontFamily: 'var(--f-mono)', fontSize: 16, marginTop: 4 }}>
                    {simMetrics.allowedLaytimeDays.toFixed(1)} Days
                  </div>
                </div>

                <div style={{ background: '#ffffff', padding: '12px 14px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                  <div style={{ color: 'var(--sail-500)', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Demurrage Incurred
                  </div>
                  <div style={{ fontWeight: 700, color: simMetrics.demurrageDays > 0 ? '#b45309' : '#047857', fontFamily: 'var(--f-mono)', fontSize: 16, marginTop: 4 }}>
                    {simMetrics.demurrageDays.toFixed(1)} Days
                  </div>
                </div>

                <div style={{ background: '#ffffff', padding: '12px 14px', borderRadius: 'var(--r)', border: '1px solid var(--sail-700)', boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
                  <div style={{ color: 'var(--sail-500)', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Financial Exposure
                  </div>
                  <div style={{ fontWeight: 700, color: simMetrics.demurrageCostUsd > 0 ? '#dc2626' : '#047857', fontFamily: 'var(--f-mono)', fontSize: 16, marginTop: 4 }}>
                    ${Math.round(simMetrics.demurrageCostUsd).toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default PortConstraintsPage;
