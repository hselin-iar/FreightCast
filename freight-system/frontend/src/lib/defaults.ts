import type { ScopeResponse, PortStatusResponse } from './types';

export const DEFAULT_SCOPE: ScopeResponse = {
  origins: [
    'Australia (Hay Point)',
    'Indonesia (East Kalimantan)',
    'South Africa (Richards Bay)',
  ],
  dest_ports: [
    'Paradip',
    'Gangavaram',
    'Dhamra',
  ],
  vessel_classes: [
    'Capesize',
    'Panamax/Kamsarmax',
    'Supramax/Ultramax',
  ],
};

export const DEFAULT_PORT_STATUSES: PortStatusResponse[] = [
  { port: 'Paradip', vessel_count: 2, avg_wait_hours: 18, recorded_at: null, is_live: true, source_note: 'AIS geofence baseline', bunker_price_usd: 620, provenance: 'modeled' },
  { port: 'Gangavaram', vessel_count: 1, avg_wait_hours: 12, recorded_at: null, is_live: true, source_note: 'AIS geofence baseline', bunker_price_usd: 620, provenance: 'modeled' },
  { port: 'Dhamra', vessel_count: 3, avg_wait_hours: 24, recorded_at: null, is_live: true, source_note: 'AIS geofence baseline', bunker_price_usd: 620, provenance: 'modeled' },
];

export function getCachedScope(): ScopeResponse {
  try {
    const raw = localStorage.getItem('freightcast_scope');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed?.origins?.length && parsed?.dest_ports?.length) {
        return parsed;
      }
    }
  } catch {
    /* ignore storage errors */
  }
  return DEFAULT_SCOPE;
}

export function setCachedScope(scope: ScopeResponse): void {
  try {
    localStorage.setItem('freightcast_scope', JSON.stringify(scope));
  } catch {
    /* ignore storage errors */
  }
}

export function getCachedPortStatuses(): PortStatusResponse[] {
  try {
    const raw = localStorage.getItem('freightcast_port_statuses');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed;
      }
    }
  } catch {
    /* ignore storage errors */
  }
  return DEFAULT_PORT_STATUSES;
}

export function setCachedPortStatuses(statuses: PortStatusResponse[]): void {
  try {
    localStorage.setItem('freightcast_port_statuses', JSON.stringify(statuses));
  } catch {
    /* ignore storage errors */
  }
}
