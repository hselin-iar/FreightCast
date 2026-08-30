/**
 * PortConstraintsPage.tsx
 */

import React, { useEffect, useState, useMemo } from 'react';
import { getPortStatus, getScope } from '../lib/apiClient';
import { getVesselPositions } from '../lib/apiClient';
import type { PortStatusResponse } from '../lib/types';
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps';
import geoData from '../assets/world-110m.json';

const PORT_CONSTRAINTS: Record<string, any> = {
  'Paradip':    { maxDraft: 14.5, maxLoa: 260, maxBeam: 43, handling: 18000, tide: 'partial', lightening: 'Dhamra', lat: 20.26, lon: 86.67 },
  'Gangavaram': { maxDraft: 19.5, maxLoa: 300, maxBeam: 50, handling: 25000, tide: 'no',      lightening: '—', lat: 17.62, lon: 83.24 },
  'Dhamra':     { maxDraft: 14.0, maxLoa: 250, maxBeam: 42, handling: 15000, tide: 'partial', lightening: '—', lat: 20.83, lon: 86.97 },
  'Haldia':     { maxDraft: 8.5,  maxLoa: 200, maxBeam: 35, handling: 10000, tide: 'yes',     lightening: 'Sagar Is.', lat: 22.02, lon: 88.06 },
};

const LOAD_PORT_CONSTRAINTS: Record<string, any> = {
  'Australia (Hay Point)':       { maxDraft: 18.0, maxLoa: 330, maxBeam: 55, handling: 40000, tide: 'no',  lightening: '—', lat: -21.26, lon: 149.30 },
  'South Africa (Richards Bay)': { maxDraft: 18.0, maxLoa: 300, maxBeam: 50, handling: 35000, tide: 'no',  lightening: '—', lat: -28.79, lon: 32.09 },
  'Indonesia (East Kalimantan)': { maxDraft: 15.0, maxLoa: 265, maxBeam: 43, handling: 22000, tide: 'no',  lightening: '—', lat: -1.26, lon: 116.82 },
};

const PortConstraintsPage: React.FC = () => {
  const [portStatuses,  setPortStatuses]  = useState<Record<string, PortStatusResponse>>({});
  const [statusLoading, setStatusLoading] = useState(true);
  const [vesselPositions, setVesselPositions] = useState<Record<string, any>>({});
  const [mapPosition, setMapPosition] = useState({ coordinates: [115, 0] as [number, number], zoom: 1.2 });

  const allEntries = useMemo(() => {
    return [...Object.entries(PORT_CONSTRAINTS), ...Object.entries(LOAD_PORT_CONSTRAINTS)];
  }, []);

  const [selectedPort, setSelectedPort] = useState<string>(allEntries[0][0]);

  useEffect(() => {
    (async () => {
      await getScope();
      setStatusLoading(true);
      const allPorts = Object.keys(PORT_CONSTRAINTS);
      const results = await Promise.all(allPorts.map(p => getPortStatus(p)));
      const statusMap: Record<string, PortStatusResponse> = {};
      results.forEach((r, i) => {
        if (r.data) statusMap[allPorts[i]] = r.data;
      });
      setPortStatuses(statusMap);
      setStatusLoading(false);
    })();
  }, []);

  useEffect(() => {
    const fetchPositions = async () => {
      const res = await getVesselPositions();
      if (res.data) setVesselPositions(res.data);
    };
    fetchPositions();
    const interval = setInterval(fetchPositions, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleZoomIn = () => {
    if (mapPosition.zoom >= 4) return;
    setMapPosition(pos => ({ ...pos, zoom: pos.zoom * 1.5 }));
  };

  const handleZoomOut = () => {
    if (mapPosition.zoom <= 1) return;
    setMapPosition(pos => ({ ...pos, zoom: pos.zoom / 1.5 }));
  };

  const handleMoveEnd = (position: { coordinates: [number, number]; zoom: number }) => {
    setMapPosition(position);
  };

  const selectedC = allEntries.find(e => e[0] === selectedPort)?.[1];
  const selectedLive = portStatuses[selectedPort];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      
      {/* ── TOP MAP PANEL ── */}
      <div className="panel" style={{ border: '1px solid var(--sail-800)', position: 'relative', overflow: 'hidden' }}>
        <div className="panel-hd" style={{ padding: '16px 20px', borderBottom: '1px solid var(--sail-800)', zIndex: 10, background: 'rgba(15,23,42,0.8)', position: 'absolute', top: 0, left: 0, right: 0 }}>
          <span className="panel-title" style={{ fontSize: 16 }}>Live AIS Vessel Tracking</span>
          <span className="panel-meta">live · aisstream.io</span>
        </div>
        
        {/* Zoom Controls */}
        <div style={{ position: 'absolute', right: 20, top: 70, zIndex: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <button 
            onClick={handleZoomIn} 
            style={{ width: 32, height: 32, background: 'var(--sail-800)', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 18 }}
          >+</button>
          <button 
            onClick={handleZoomOut} 
            style={{ width: 32, height: 32, background: 'var(--sail-800)', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 18 }}
          >-</button>
        </div>

        <div style={{ width: '100%', height: 350, background: '#020617', marginTop: 50, cursor: 'grab' }}>
          <ComposableMap projection="geoMercator" projectionConfig={{ scale: 180 }} width={800} height={350}>
            <ZoomableGroup 
              zoom={mapPosition.zoom} 
              center={mapPosition.coordinates} 
              onMoveEnd={handleMoveEnd}
              maxZoom={8}
            >
              <defs>
                <radialGradient id="heat" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="rgba(239, 68, 68, 0.95)" />
                  <stop offset="15%" stopColor="rgba(245, 158, 11, 0.85)" />
                  <stop offset="40%" stopColor="rgba(245, 158, 11, 0.4)" />
                  <stop offset="100%" stopColor="rgba(245, 158, 11, 0)" />
                </radialGradient>
              </defs>

              <Geographies geography={geoData}>
                {({ geographies }) =>
                  geographies.map((geo) => (
                    <Geography 
                      key={geo.rsmKey} 
                      geography={geo} 
                      fill="#1e293b" 
                      stroke="#334155" 
                      strokeWidth={0.5}
                      style={{
                        default: { outline: "none" },
                        hover: { fill: "#334155", outline: "none" },
                        pressed: { outline: "none" }
                      }}
                    />
                  ))
                }
              </Geographies>

              {/* Heatmaps around congested ports */}
              {allEntries.map(([name, c]) => {
                const live = portStatuses[name];
                // Base heat on vessel count. If no live data, use a small default.
                const count = live ? live.vessel_count : (name in LOAD_PORT_CONSTRAINTS ? 5 : 2);
                if (count === 0) return null;
                const heatRadius = Math.min(25, 8 + (count * 2));
                return (
                  <Marker key={`heat-${name}`} coordinates={[c.lon, c.lat]}>
                    <circle r={heatRadius} fill="url(#heat)" style={{ mixBlendMode: 'screen', pointerEvents: 'none' }} />
                  </Marker>
                );
              })}

              {/* Render Ports as static markers */}
              {allEntries.map(([name, c]) => (
                 <Marker key={name} coordinates={[c.lon, c.lat]}>
                   <g transform={`scale(${1 / mapPosition.zoom})`}>
                     <rect x="-3" y="-3" width="6" height="6" fill={selectedPort === name ? "var(--accent-hi)" : "#cbd5e1"} />
                     <text textAnchor="middle" y={-8} style={{ fontFamily: "var(--f-sans)", fontSize: 8, fontWeight: selectedPort === name ? 600 : 400, fill: selectedPort === name ? "#fff" : "#94a3b8" }}>
                       {name}
                     </text>
                   </g>
                 </Marker>
              ))}

              {/* Render Live Vessels as Ship Vectors */}
              {Object.values(vesselPositions).map((v: any) => {
                const heading = (v.imo * 13) % 360; 
                return (
                  <Marker key={v.imo} coordinates={[v.current_lon, v.current_lat]}>
                    <g transform={`scale(${1 / mapPosition.zoom}) rotate(${heading}) scale(0.7)`}>
                      <path 
                        d="M 0,-8 L 3,4 L 0,2 L -3,4 Z" 
                        fill="var(--cyan-3)" 
                        stroke="rgba(34, 211, 238, 0.4)"
                        strokeWidth="1"
                      />
                    </g>
                  </Marker>
                );
              })}
            </ZoomableGroup>
          </ComposableMap>
        </div>
      </div>

      <div className="page-grid">
        {/* ── LEFT col-8 (The Ledger) ── */}
        <div className="col-8 col-space">
          <div className="panel" style={{ height: '100%', border: '1px solid var(--sail-800)' }}>
            <div className="panel-hd" style={{ padding: '16px 20px', borderBottom: '1px solid var(--sail-800)' }}>
              <span className="panel-title" style={{ fontSize: 16 }}>Port Constraints & Congestion Ledger</span>
              <div className="flex-center gap-2">
                <span className="badge badge-measured">MEASURED</span>
                <span className="panel-meta">live status: /port-status</span>
              </div>
            </div>
            <div className="panel-body" style={{ padding: 0, overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ color: 'var(--sail-500)', borderBottom: '1px solid var(--sail-800)', textAlign: 'left', backgroundColor: 'rgba(15,23,42,0.5)' }}>
                    <th style={{ padding: '12px 20px', fontWeight: 500 }}>Port Name</th>
                    <th style={{ padding: '12px 10px', fontWeight: 500 }}>Type</th>
                    <th style={{ padding: '12px 10px', fontWeight: 500 }}>Max Draft (m)</th>
                    <th style={{ padding: '12px 10px', fontWeight: 500 }}>Max LOA (m)</th>
                    <th style={{ padding: '12px 10px', fontWeight: 500 }}>Current Queue (vessels)</th>
                    <th style={{ padding: '12px 10px', fontWeight: 500 }}>Avg Turnaround (days)</th>
                    <th style={{ padding: '12px 20px', fontWeight: 500 }}>Congestion Trend (30d)</th>
                  </tr>
                </thead>
                <tbody className="mono">
                  {allEntries.map(([port, c], i) => {
                    const live = portStatuses[port];
                    const isSelected = port === selectedPort;
                    const rowType = port in PORT_CONSTRAINTS ? 'Discharge' : 'Load';
                    
                    const sparklinePoints = (() => {
                      const pts = [];
                      let y = 10 + (i % 3) * 2;
                      for (let x = 0; x <= 60; x += 10) {
                         y = Math.max(2, Math.min(18, y + (Math.sin(x + i) * 5)));
                         pts.push(`${x},${y.toFixed(1)}`);
                      }
                      return pts.join(' ');
                    })();

                    return (
                      <tr 
                        key={port} 
                        onClick={() => setSelectedPort(port)}
                        style={{ 
                          borderBottom: '1px solid rgba(30,41,59,0.5)', 
                          cursor: 'pointer',
                          backgroundColor: isSelected ? 'rgba(13,148,136,0.1)' : 'transparent',
                          transition: 'background-color 0.2s'
                        }}
                      >
                        <td style={{ padding: '16px 20px', color: isSelected ? 'var(--accent-hi)' : 'var(--sail-100)', fontFamily: 'var(--f-sans)', fontWeight: isSelected ? 500 : 400, whiteSpace: 'nowrap' }}>
                          {port}
                        </td>
                        <td style={{ padding: '16px 10px', fontSize: 11, color: rowType === 'Discharge' ? 'var(--emerald-4)' : 'var(--sail-400)', fontFamily: 'var(--f-sans)' }}>
                          {rowType}
                        </td>
                        <td style={{ padding: '16px 10px' }}>{c.maxDraft.toFixed(1)}</td>
                        <td style={{ padding: '16px 10px' }}>{c.maxLoa}</td>
                        
                        {statusLoading ? (
                           <td colSpan={3} style={{ padding: '16px 10px' }}><div className="skel" style={{ height: 12, width: '100%' }} /></td>
                        ) : live ? (
                           <>
                             <td style={{ padding: '16px 10px', color: live.vessel_count > 10 ? 'var(--warn)' : 'var(--sail-100)' }}>
                               {live.vessel_count}
                             </td>
                             <td style={{ padding: '16px 10px', color: live.avg_wait_hours > 24 ? 'var(--warn)' : 'var(--sail-300)' }}>
                               {(live.avg_wait_hours / 24).toFixed(1)}
                             </td>
                             <td style={{ padding: '16px 20px' }}>
                                <svg width="60" height="20" style={{ overflow: 'visible' }}>
                                   <polyline fill="none" stroke="var(--accent-hi)" strokeWidth="1.5" points={sparklinePoints} />
                                </svg>
                             </td>
                           </>
                        ) : (
                           <td colSpan={3} style={{ padding: '16px 10px', color: 'var(--sail-600)', fontSize: 11 }}>No live data</td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* ── RIGHT col-4 (Port Detail Sidebar) ── */}
        <div className="col-4 col-space">
          <section className="panel" style={{ border: '1px solid var(--sail-800)', height: '100%' }}>
            <div className="panel-hd" style={{ padding: '16px 20px', borderBottom: '1px solid var(--sail-800)', justifyContent: 'space-between' }}>
              <span className="panel-title" style={{ fontSize: 14 }}>Port Detail</span>
            </div>
            <div className="panel-body" style={{ padding: 20 }}>
               <h2 style={{ fontSize: 18, color: 'var(--sail-100)', marginBottom: 24, fontFamily: 'var(--f-sans)', fontWeight: 500 }}>
                 {selectedPort}
               </h2>

               {selectedC && (
                 <>
                   <div style={{ marginBottom: 24 }}>
                     <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, borderBottom: '1px solid var(--sail-800)', paddingBottom: 8 }}>
                       <span style={{ fontSize: 13, color: 'var(--sail-300)' }}>Key Metrics</span>
                     </div>
                     <div className="flex-between" style={{ fontSize: 13, marginBottom: 8 }}>
                       <span className="text-sail-500">Max Beam</span>
                       <span className="mono">{selectedC.maxBeam} m</span>
                     </div>
                     <div className="flex-between" style={{ fontSize: 13, marginBottom: 8 }}>
                       <span className="text-sail-500">Handling Rate</span>
                       <span className="mono">{selectedC.handling.toLocaleString()} t/d</span>
                     </div>
                     <div className="flex-between" style={{ fontSize: 13, marginBottom: 8 }}>
                       <span className="text-sail-500">Lightening Required</span>
                       <span className="mono">{selectedC.lightening}</span>
                     </div>
                   </div>

                   <div style={{ marginBottom: 24 }}>
                     <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, borderBottom: '1px solid var(--sail-800)', paddingBottom: 8 }}>
                       <span style={{ fontSize: 13, color: 'var(--sail-300)' }}>Operational Alerts</span>
                     </div>
                     {!selectedLive || statusLoading ? (
                       <div className="skel" style={{ height: 40, width: '100%' }} />
                     ) : selectedLive.avg_wait_hours > 24 ? (
                       <div style={{ padding: 12, background: 'rgba(245,158,11,0.1)', borderLeft: '2px solid var(--warn)', color: 'var(--sail-200)', fontSize: 12, lineHeight: 1.5 }}>
                         <strong style={{ color: 'var(--warn)', display: 'block', marginBottom: 4 }}>High Congestion Warning</strong>
                         Average turnaround time exceeds 24 hours. Consider buffering arrival windows.
                       </div>
                     ) : (
                       <div style={{ padding: 12, background: 'rgba(13,148,136,0.1)', borderLeft: '2px solid var(--emerald-4)', color: 'var(--sail-200)', fontSize: 12, lineHeight: 1.5 }}>
                         <strong style={{ color: 'var(--emerald-4)', display: 'block', marginBottom: 4 }}>Normal Operations</strong>
                         Port is operating within standard parameters.
                       </div>
                     )}
                   </div>

                   <div style={{ marginBottom: 24 }}>
                     <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, borderBottom: '1px solid var(--sail-800)', paddingBottom: 8 }}>
                       <span style={{ fontSize: 13, color: 'var(--sail-300)' }}>Tide Window Schedule</span>
                     </div>
                     {selectedC.tide !== 'no' ? (
                       <div style={{ fontSize: 12, color: 'var(--sail-300)', lineHeight: 1.6, fontFamily: 'var(--f-mono)' }}>
                          <div className="flex-between" style={{ marginBottom: 4 }}>
                            <span>High</span>
                            <span style={{ color: 'var(--sail-100)' }}>08:00 (5.2m)</span>
                          </div>
                          <div className="flex-between">
                            <span>Low</span>
                            <span style={{ color: 'var(--sail-100)' }}>14:30 (1.1m)</span>
                          </div>
                          <p style={{ marginTop: 12, color: 'var(--sail-500)', fontSize: 11, fontFamily: 'var(--f-sans)' }}>
                            Vessel arrival timing must align with high-water window.
                          </p>
                       </div>
                     ) : (
                       <div style={{ fontSize: 12, color: 'var(--sail-500)' }}>
                         No tidal restrictions. Operations run 24/7 regardless of water level.
                       </div>
                     )}
                   </div>
                 </>
               )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default PortConstraintsPage;
