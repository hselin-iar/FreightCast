/**
 * AISRouteMap.tsx — Interactive Geographic Shipping Corridor & Congestion Map
 *
 * Renders real geographic maritime corridors from origin loading terminals
 * (Hay Point, Richards Bay, East Kalimantan) to Indian discharge ports
 * (Paradip, Gangavaram, Dhamra, Haldia) with live congestion density from /port-status.
 *
 * Features:
 *  - Zoomable & Draggable (ZoomableGroup with minZoom 1, maxZoom 6)
 *  - Centered and zoomed into the active shipping corridor by default
 *  - Floating Zoom / Pan / Reset Controls (+, −, ⟲)
 *  - Staggered port labels to prevent crowding
 *  - Great-circle navigation trajectories
 *  - Real-time AIS vessel position dots
 */
import React, { useMemo, useState, useEffect } from 'react';
import type { PortStatusResponse } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';
import { ComposableMap, Geographies, Geography, Marker, Line, ZoomableGroup } from 'react-simple-maps';
import geoData from '../assets/world-110m.json';
import { getVesselPositions } from '../lib/apiClient';

interface Props {
  origin: string;
  dischargePorts: string[];
  portStatuses: PortStatusResponse[];
}

const PORT_LOCATIONS: Record<string, [number, number]> = {
  'Australia (Hay Point)': [149.30, -21.26],
  'Hay Point':             [149.30, -21.26],
  'Richards Bay':          [32.09, -28.79],
  'South Africa (Richards Bay)': [32.09, -28.79],
  'Kalimantan':            [116.82, -1.26],
  'Indonesia (East Kalimantan)': [116.82, -1.26],
  'Indonesia (Samarinda)': [117.15, -0.50],
  'Paradip':               [86.67, 20.26],
  'Gangavaram':            [83.24, 17.62],
  'Vizag':                 [83.29, 17.69],
  'Visakhapatnam':         [83.29, 17.69],
  'Dhamra':                [86.97, 20.83],
  'Haldia':                [88.06, 22.02],
  'Kamarajar (Ennore)':    [80.33, 13.25],
  'Ennore':                [80.33, 13.25],
};

const PORT_LABEL_OFFSETS: Record<string, { dx: number; dy: number; anchor: 'start' | 'middle' | 'end' }> = {
  'Paradip': { dx: 10, dy: 3, anchor: 'start' },
  'Dhamra': { dx: 10, dy: -8, anchor: 'start' },
  'Gangavaram': { dx: -10, dy: 4, anchor: 'end' },
  'Visakhapatnam': { dx: -10, dy: -6, anchor: 'end' },
  'Vizag': { dx: -10, dy: -6, anchor: 'end' },
  'Haldia': { dx: 10, dy: -12, anchor: 'start' },
  'Kamarajar (Ennore)': { dx: -10, dy: 8, anchor: 'end' },
  'Ennore': { dx: -10, dy: 8, anchor: 'end' },
  'Australia (Hay Point)': { dx: 0, dy: 16, anchor: 'middle' },
  'Hay Point': { dx: 0, dy: 16, anchor: 'middle' },
  'South Africa (Richards Bay)': { dx: 0, dy: 16, anchor: 'middle' },
  'Richards Bay': { dx: 0, dy: 16, anchor: 'middle' },
  'Indonesia (East Kalimantan)': { dx: 12, dy: 3, anchor: 'start' },
  'Kalimantan': { dx: 12, dy: 3, anchor: 'start' },
};

function congColor(vessels: number): string {
  if (vessels > 10) return '#ef4444';
  if (vessels > 5)  return 'var(--warn)';
  if (vessels > 2)  return '#eab308';
  return 'var(--emerald-4)';
}

function congLabel(vessels: number): string {
  if (vessels > 10) return 'high';
  if (vessels > 5)  return 'moderate';
  if (vessels > 2)  return 'light';
  return 'clear';
}

function getInitialCorridorCenter(origin: string): { coordinates: [number, number]; zoom: number } {
  if (origin.includes('South Africa') || origin.includes('Richards')) {
    return { coordinates: [60, -5], zoom: 1.5 };
  }
  if (origin.includes('Indonesia') || origin.includes('Kalimantan')) {
    return { coordinates: [98, 8], zoom: 2.2 };
  }
  // Default: Australia Hay Point -> East Coast India
  return { coordinates: [115, -2], zoom: 1.6 };
}

const AISRouteMap: React.FC<Props> = ({ origin, dischargePorts, portStatuses }) => {
  const [mapPosition, setMapPosition] = useState<{ coordinates: [number, number]; zoom: number }>(() =>
    getInitialCorridorCenter(origin)
  );
  const [vesselPositions, setVesselPositions] = useState<Record<string, any>>({});
  const mapContainerRef = React.useRef<HTMLDivElement>(null);

  // Auto-focus when origin changes
  useEffect(() => {
    setMapPosition(getInitialCorridorCenter(origin));
  }, [origin]);

  // Attach native non-passive wheel & pinch gesture listeners for trackpads and touchscreens
  useEffect(() => {
    const el = mapContainerRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      // Prevent browser default window zoom / page scroll when interacting with map
      e.preventDefault();
      e.stopPropagation();

      // Trackpad pinch gesture sets e.ctrlKey = true
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

  // Fetch live tracked AIS ships
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

  const statusMap = useMemo(() => {
    const m: Record<string, PortStatusResponse> = {};
    portStatuses.forEach(ps => { m[ps.port] = ps; });
    return m;
  }, [portStatuses]);

  const originCoords = PORT_LOCATIONS[origin] || [149.30, -21.26];
  const allPorts = Array.from(new Set([origin, ...dischargePorts]));

  const handleZoomIn = () => {
    if (mapPosition.zoom >= 5) return;
    setMapPosition(pos => ({ ...pos, zoom: Math.min(5, pos.zoom * 1.35) }));
  };

  const handleZoomOut = () => {
    if (mapPosition.zoom <= 1) return;
    setMapPosition(pos => ({ ...pos, zoom: Math.max(1, pos.zoom / 1.35) }));
  };

  const handleResetView = () => {
    setMapPosition(getInitialCorridorCenter(origin));
  };

  return (
    <div className="panel" id="ais-route-map">
      <div className="panel-hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <span className="panel-title">Interactive AIS Maritime Corridors</span>
          <span className="panel-meta" style={{ marginLeft: 8 }}>
            Draggable & zoomable · Great-circle corridors · Port queue wait times
          </span>
        </div>
        <ProvenanceBadge provenance="measured" note="WGS84 great-circle corridors; AIS positions via live listener." />
      </div>

      <div className="panel-body">
        {/* GIS Projection Canvas with Controls */}
        <div
          ref={mapContainerRef}
          style={{
            position: 'relative',
            height: 320,
            background: '#080d1a',
            border: '1px solid var(--sail-800)',
            borderRadius: 6,
            overflow: 'hidden',
            touchAction: 'none',
          }}
        >
          {/* Floating Zoom / Reset Action Controls */}
          <div
            style={{
              position: 'absolute',
              top: 12,
              right: 12,
              zIndex: 10,
              display: 'flex',
              flexDirection: 'column',
              gap: 5,
            }}
          >
            <button
              onClick={handleZoomIn}
              className="btn-secondary"
              style={{
                width: 30,
                height: 30,
                padding: 0,
                fontWeight: 700,
                fontSize: 15,
                background: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(4px)',
                borderColor: 'var(--sail-700)',
              }}
              title="Zoom In (+)"
            >
              +
            </button>
            <button
              onClick={handleZoomOut}
              className="btn-secondary"
              style={{
                width: 30,
                height: 30,
                padding: 0,
                fontWeight: 700,
                fontSize: 15,
                background: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(4px)',
                borderColor: 'var(--sail-700)',
              }}
              title="Zoom Out (−)"
            >
              −
            </button>
            <button
              onClick={handleResetView}
              className="btn-secondary"
              style={{
                width: 30,
                height: 30,
                padding: 0,
                fontSize: 13,
                background: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(4px)',
                borderColor: 'var(--sail-700)',
              }}
              title="Reset Corridor View"
            >
              ⟲
            </button>
          </div>

          <ComposableMap
            projection="geoMercator"
            projectionConfig={{ scale: 220, center: [95, 0] }}
            style={{ width: '100%', height: '100%', cursor: 'grab' }}
          >
            <ZoomableGroup
              zoom={mapPosition.zoom}
              center={mapPosition.coordinates}
              onMoveEnd={pos => setMapPosition(pos)}
              minZoom={1}
              maxZoom={5}
            >
              {/* World Landmasses */}
              <Geographies geography={geoData}>
                {({ geographies }) =>
                  geographies.map(geo => (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      fill="#1e293b"
                      stroke="#334155"
                      strokeWidth={0.5}
                      style={{
                        default: { outline: 'none' },
                        hover: { fill: '#2e3d54', outline: 'none' },
                        pressed: { outline: 'none' },
                      }}
                    />
                  ))
                }
              </Geographies>

              {/* Maritime Corridors (Lines from Origin to Discharge Ports) */}
              {dischargePorts.map(dp => {
                const destCoords = PORT_LOCATIONS[dp];
                if (!destCoords) return null;
                return (
                  <Line
                    key={dp}
                    from={originCoords}
                    to={destCoords}
                    stroke="var(--accent)"
                    strokeWidth={2.2}
                    strokeDasharray="5 3"
                    strokeLinecap="round"
                    opacity={0.85}
                  />
                );
              })}

              {/* Live Tracked AIS Vessels */}
              {Object.entries(vesselPositions).map(([vesselKey, pos]) => {
                const lat = pos?.lat ?? pos?.current_lat;
                const lon = pos?.lon ?? pos?.current_lon;
                if (lat === undefined || lon === undefined) return null;
                return (
                  <Marker key={vesselKey} coordinates={[lon, lat]}>
                    <circle r={2.5} fill="#38bdf8" opacity={0.8} />
                    <circle r={5} fill="none" stroke="#38bdf8" strokeWidth={0.6} opacity={0.35} />
                  </Marker>
                );
              })}

              {/* Port Nodes */}
              {allPorts.map(portName => {
                const coords = PORT_LOCATIONS[portName];
                if (!coords) return null;
                const isOrigin = portName === origin;
                const status = statusMap[portName];
                const vessels = status?.vessel_count ?? 0;
                const color = isOrigin ? '#f59e0b' : congColor(vessels);
                const offset = PORT_LABEL_OFFSETS[portName] || { dx: 0, dy: -10, anchor: 'middle' };

                return (
                  <Marker
                    key={portName}
                    coordinates={coords}
                    style={{ default: { outline: 'none' }, hover: { outline: 'none' } }}
                  >
                    {/* Outer glow ring */}
                    <circle
                      r={isOrigin ? 7 : 5.5}
                      fill={color}
                      stroke="#ffffff"
                      strokeWidth={1.5}
                    />
                    {vessels > 6 && !isOrigin && (
                      <circle r={11} fill="none" stroke={color} strokeWidth={1.2} opacity={0.6} />
                    )}

                    {/* Staggered Port Name Label */}
                    <text
                      textAnchor={offset.anchor}
                      x={offset.dx}
                      y={offset.dy}
                      style={{
                        fontFamily: 'var(--f-mono)',
                        fontSize: 9.5,
                        fill: isOrigin ? '#fbbf24' : '#f1f5f9',
                        fontWeight: 700,
                        textShadow: '0 2px 4px rgba(0,0,0,0.95)',
                      }}
                    >
                      {portName.replace(/\s*\(.*\)/, '')} {vessels > 0 ? `(${vessels})` : ''}
                    </text>
                  </Marker>
                );
              })}
            </ZoomableGroup>
          </ComposableMap>

          {/* Map Status Legend */}
          <div
            style={{
              position: 'absolute',
              bottom: 8,
              right: 10,
              background: 'rgba(10, 15, 29, 0.85)',
              padding: '6px 12px',
              borderRadius: 4,
              border: '1px solid var(--sail-800)',
              display: 'flex',
              gap: 12,
              fontSize: 10,
              fontFamily: 'var(--f-mono)',
              color: 'var(--sail-300)',
              backdropFilter: 'blur(4px)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
              <span>Origin</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--emerald-4)', display: 'inline-block' }} />
              <span>Clear</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
              <span>Congested</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#38bdf8', display: 'inline-block' }} />
              <span>AIS Vessel</span>
            </div>
          </div>
        </div>

        {/* Port Status Summary Bars */}
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {dischargePorts.map(portName => {
            const status = statusMap[portName];
            const vessels = status?.vessel_count ?? 0;
            const pct = Math.min(100, Math.round((vessels / 15) * 100));
            return (
              <div key={portName} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: 'var(--sail-200)', fontWeight: 600 }}>{portName}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontFamily: 'var(--f-mono)', fontSize: 11, color: congColor(vessels), fontWeight: 600 }}>
                    {vessels} ships waiting · {congLabel(vessels)}
                  </span>
                  <div style={{ width: 80, height: 6, background: 'var(--sail-800)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: congColor(vessels), borderRadius: 3 }} />
                  </div>
                </div>
              </div>
            );
          })}
          {!dischargePorts.length && (
            <p className="infer" style={{ margin: '4px 0', fontSize: '11px' }}>
              Select discharge ports in the form to render route corridors and live wait times.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default AISRouteMap;
