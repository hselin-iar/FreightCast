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

const LABELS: Record<Provenance, string> = {
  measured: 'MEASURED',
  modeled:  'MODELED',
  assumed:  'ASSUMED',
};

const DEFAULT_NOTES: Record<Provenance, string> = {
  measured: 'Sourced from live AIS or exchange data — directly observed.',
  modeled:  'Output of the trained forecasting model — not directly observed.',
  assumed:  'User-supplied or fallback parameter — not derived from data.',
};

const ProvenanceBadge: React.FC<Props> = ({ provenance, note, compact = false }) => {
  const tip = note ?? DEFAULT_NOTES[provenance];
  return (
    <span className="tip-wrap">
      <span className={`badge badge-${provenance}`}>
        {compact ? provenance[0].toUpperCase() : LABELS[provenance]}
      </span>
      {tip && <span className="tip-box">{tip}</span>}
    </span>
  );
};

export default ProvenanceBadge;
