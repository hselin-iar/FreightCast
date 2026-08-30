/**
 * ProvenanceBadge.tsx — mirrors index.html badge-measured/modeled/assumed classes.
 */
import React from 'react';
import type { Provenance } from '../lib/types';

interface Props {
  provenance: Provenance;
  note?: string | null;
  /** Show full label (default) or just icon */
  compact?: boolean;
}



const DEFAULT_NOTES: Record<Provenance, string> = {
  measured: 'Sourced from live AIS or exchange data — directly observed.',
  modeled:  'Output of the trained forecasting model — not directly observed.',
  assumed:  'User-supplied or fallback parameter — not derived from data.',
};

const ProvenanceBadge: React.FC<Props> = ({ provenance, note, compact = false }) => {
  const tip = note ?? DEFAULT_NOTES[provenance];
  return (
    <span className="tip-wrap">
      <span style={{ 
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        fontFamily: 'var(--f-sans)', fontSize: 11, fontWeight: 500, color: 'var(--sail-400)'
      }}>
        <span style={{ 
          color: provenance === 'measured' ? 'var(--emerald-4)' 
               : provenance === 'modeled' ? '#3b82f6' 
               : 'var(--amber)',
          fontSize: 14 
        }}>●</span>
        <span style={{ textTransform: 'capitalize' }}>
          {compact ? provenance[0] : provenance}
        </span>
      </span>
      {tip && <span className="tip-box">{tip}</span>}
    </span>
  );
};

export default ProvenanceBadge;
