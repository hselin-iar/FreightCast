/**
 * AISRouteMap.tsx — DOC3 Dashboard sellable layer / Build Step 12
 *
 * Plots origin + discharge ports with live congestion density from /port-status.
 * "Reuses /port-status — no new backend data." (DOC3)
 *
 * Uses an SVG route map with geographically-proportioned port positions.
 * Australia (Hay Point) is left; East Coast India ports are right.
 * Congestion density shown as animated rings on high-traffic ports.
 */
import React, { useMemo } from 'react';
import type { PortStatusResponse } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  origin: string;
  dischargePorts: string[];
  portStatuses: PortStatusResponse[];
}

/* ── Port coordinates (in 800x200 viewBox) ── */
const PORT_COORDS: Record<string, { x: number; y: number; label: string }> = {
  'Australia (Hay Point)': { x: 130, y: 110, label: 'Hay Point' },
  'Hay Point':             { x: 130, y: 110, label: 'Hay Point' },
  'Richards Bay':          { x: 70,  y: 145, label: 'Richards Bay' },
  'Kalimantan':            { x: 280, y: 100, label: 'Kalimantan' },
  'Paradip':               { x: 620, y: 75,  label: 'Paradip' },
  'Gangavaram':            { x: 660, y: 110, label: 'Gangavaram' },
  'Vizag':                 { x: 640, y: 95,  label: 'Vizag' },
  'Dhamra':                { x: 600, y: 65,  label: 'Dhamra' },
  'Haldia':                { x: 575, y: 55,  label: 'Haldia' },
  'Dakar':                 { x: 50,  y: 60,  label: 'Dakar' },
  'Maputo':                { x: 80,  y: 155, label: 'Maputo' },
  'Rotterdam':             { x: 100, y: 40,  label: 'Rotterdam' },
  'Saldanha Bay':          { x: 60,  y: 165, label: 'Saldanha Bay' },
};

function congColor(vessels: number): string {
  if (vessels > 12) return '#ef4444';
  if (vessels > 6)  return 'var(--warn)';
  if (vessels > 2)  return '#eab308';
  return 'var(--emerald-4)';
}

function congLabel(vessels: number): string {
  if (vessels > 12) return 'high';
  if (vessels > 6)  return 'moderate';
  if (vessels > 2)  return 'light';
  return 'clear';
}

/** Draw a dashed great-circle arc between two coordinates. */
function RouteArc({ x1, y1, x2, y2, color }: { x1: number; y1: number; x2: number; y2: number; color: string }) {
  const mx = (x1 + x2) / 2;
  const my = Math.min(y1, y2) - 30; // control point pulled up for arc effect
  return (
    <path
      d={`M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`}
      fill="none" stroke={color} strokeWidth={1.8}
      strokeDasharray="4 3" strokeOpacity={0.8}
    />
  );
}

const AISRouteMap: React.FC<Props> = ({ origin, dischargePorts, portStatuses }) => {
  const statusMap = useMemo(() => {
    const m: Record<string, PortStatusResponse> = {};
    portStatuses.forEach(ps => { m[ps.port] = ps; });
    return m;
  }, [portStatuses]);

  const allPorts = Array.from(new Set([origin, ...dischargePorts]));
  const originCoord  = PORT_COORDS[origin] ?? { x: 130, y: 110, label: origin };

  return (
    <div className="panel" id="ais-route-map">
      <div className="panel-hd">
        <span className="panel-title">AIS Route Map</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <ProvenanceBadge provenance="measured" note="Port positions fixed; vessel counts from /port-status (AIS geofence)." />
          <span className="panel-meta">Origin · discharge ports · congestion</span>
        </div>
      </div>
      <div className="panel-body">
        {/* Map SVG */}
        <div style={{
          position: 'relative', height: 200,
          background: 'rgba(15,23,42,0.7)',
          border: '1px solid var(--sail-800)',
          borderRadius: 4, overflow: 'hidden',
        }}>
          {/* Grid dots */}
          <div style={{
            position: 'absolute', inset: 0, opacity: 0.15,
            backgroundImage: 'radial-gradient(circle, #0d9488 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }} />

          <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
            viewBox="0 0 800 200" preserveAspectRatio="xMidYMid meet">

            {/* Route arcs: origin → each discharge */}
            {dischargePorts.map(dp => {
              const dc = PORT_COORDS[dp];
              if (!dc) return null;
              const isSelected = dischargePorts.includes(dp);
              return (
                <RouteArc key={dp}
                  x1={originCoord.x} y1={originCoord.y}
                  x2={dc.x} y2={dc.y}
                  color={isSelected ? 'var(--accent)' : 'var(--sail-600)'}
                />
              );
            })}

            {/* Port markers */}
            {allPorts.map(portName => {
              const coord  = PORT_COORDS[portName];
              if (!coord) return null;
              const status = statusMap[portName];
              const isOrigin = portName === origin;
              const vessels  = status?.vessel_count ?? 0;
              const color    = isOrigin ? 'var(--accent-hi)' : congColor(vessels);
              const r = isOrigin ? 6 : 5;

              return (
                <g key={portName}>
                  {/* Congestion pulse ring for high-traffic ports */}
                  {vessels > 6 && !isOrigin && (
                    <circle cx={coord.x} cy={coord.y} r={r + 4}
                      fill="none" stroke={color} strokeWidth={1.2} strokeOpacity={0.4}
                    />
                  )}
                  <circle cx={coord.x} cy={coord.y} r={r}
                    fill={color} stroke="rgba(255,255,255,0.4)" strokeWidth={1.5}
                  />
                  {/* Label */}
                  <text x={coord.x} y={coord.y - r - 4}
                    fill="#94a3b8" fontSize={11} fontFamily="var(--f-mono)"
                    textAnchor="middle" fontWeight={500}>
                    {coord.label}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Legend */}
          <div style={{
            position: 'absolute', bottom: 4, right: 6,
            display: 'flex', flexDirection: 'column', gap: 2,
          }}>
            {[
              { color: 'var(--emerald)', label: 'clear' },
              { color: 'var(--warn)',    label: 'moderate' },
              { color: '#ef4444',        label: 'high' },
            ].map(l => (
              <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 8, fontFamily: 'monospace', color: 'var(--sail-400)' }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: l.color, display: 'inline-block' }} />
                {l.label}
              </div>
            ))}
          </div>
        </div>

        {/* Port status table */}
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {dischargePorts.map(portName => {
            const status = statusMap[portName];
            const vessels = status?.vessel_count ?? 0;
            const pct = Math.min(100, Math.round((vessels / 20) * 100));
            return (
              <div key={portName} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: 'var(--sail-300)' }}>{portName}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontFamily: 'var(--f-mono)', fontSize: 11, color: congColor(vessels) }}>
                    {vessels} vessels · {congLabel(vessels)}
                  </span>
                  <div style={{ width: 64, height: 5, background: 'var(--sail-800)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: congColor(vessels), borderRadius: 3 }} />
                  </div>
                </div>
              </div>
            );
          })}
          {!dischargePorts.length && (
            <p className="infer">Select discharge ports to see congestion.</p>
          )}
        </div>
        <p className="infer">
          Congestion is not a hard block — it adds a risk-buffer term and biases entry timing. Source: /port-status, AIS geofence.
        </p>
      </div>
    </div>
  );
};

export default AISRouteMap;
