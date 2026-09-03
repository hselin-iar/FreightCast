import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import type { CitationItem } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';
import MathFormula from './MathFormula';

interface Props {
  citation: CitationItem;
  children: React.ReactNode;
}

export const CitationToken: React.FC<Props> = ({ citation, children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [popoverCoords, setPopoverCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLSpanElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      const halfWidth = 190;
      const idealLeft = rect.left + window.scrollX + rect.width / 2;
      const minLeft = halfWidth + 16;
      const maxLeft = Math.max(minLeft, window.innerWidth - halfWidth - 16);
      const clampedLeft = Math.max(minLeft, Math.min(maxLeft, idealLeft));
      setPopoverCoords({
        top: rect.top + window.scrollY - 8, // Just above the trigger
        left: clampedLeft,
      });
    }
  }, [isOpen]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        triggerRef.current &&
        !triggerRef.current.contains(event.target as Node) &&
        popoverRef.current &&
        !popoverRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const badgeBorder =
    citation.provenance === 'measured'
      ? 'var(--emerald)'
      : citation.provenance === 'modeled'
      ? '#2563eb'
      : 'var(--warn)';

  const badgeBg =
    citation.provenance === 'measured'
      ? 'var(--badge-measured-bg)'
      : citation.provenance === 'modeled'
      ? 'var(--badge-modeled-bg)'
      : 'var(--badge-assumed-bg)';

  return (
    <span
      ref={triggerRef}
      style={{ position: 'relative', display: 'inline' }}
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      <span
        onClick={() => setIsOpen((prev) => !prev)}
        style={{
          borderBottom: `2px dotted ${badgeBorder}`,
          color: '#FAFAFA',
          fontWeight: 600,
          cursor: 'pointer',
          padding: '1px 3px',
          borderRadius: 'var(--r)',
          backgroundColor: isOpen ? badgeBg : 'transparent',
          transition: 'all 0.15s ease',
        }}
      >
        {children}
        <span
          style={{
            fontSize: 10,
            verticalAlign: 'super',
            marginLeft: 3,
            color: badgeBorder,
            fontFamily: 'var(--f-mono)',
            fontWeight: 700,
          }}
        >
          [{citation.provenance === 'measured' ? 'DATA' : citation.provenance === 'modeled' ? 'MODEL' : 'ASSUMED'}]
        </span>
      </span>

      {/* Floating Evidence Inspector Popover */}
      {isOpen && createPortal(
        <div
          ref={popoverRef}
          style={{
            position: 'absolute',
            top: popoverCoords.top,
            left: popoverCoords.left,
            transform: 'translate(-50%, -100%)',
            width: 360,
            maxWidth: '90vw',
            backgroundColor: 'var(--sail-900)',
            border: `1.5px solid ${badgeBorder}`,
            boxShadow: 'var(--shadow-panel)',
            borderRadius: 'var(--r-lg)',
            padding: '14px 16px',
            zIndex: 999999, // Ensure absolute top layer
            fontSize: 12,
            lineHeight: 1.5,
            color: 'var(--sail-200)',
            pointerEvents: 'auto',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid var(--sail-800)',
              paddingBottom: 6,
              marginBottom: 8,
            }}
          >
            <span style={{ fontWeight: 700, color: 'var(--sail-100)', fontSize: 13 }}>
              {citation.title}
            </span>
            <ProvenanceBadge provenance={citation.provenance} />
          </div>

          {/* Source Citation */}
          <div style={{ marginBottom: 8 }}>
            <span style={{ color: 'var(--sail-500)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
              Data Source / Authority
            </span>
            <div style={{ color: 'var(--sail-100)', fontWeight: 600, marginTop: 2 }}>
              {citation.source}
            </div>
          </div>

          {/* Governing Equation / Math (if present) */}
          {citation.equation && (
            <div style={{ marginTop: 8, padding: '8px 10px', backgroundColor: 'var(--ink-700)', borderLeft: '2px solid var(--accent)', borderRadius: '0 4px 4px 0', overflowX: 'auto' }}>
              <div style={{ fontSize: 9.5, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: 4 }}>
                Mathematical Grounding
              </div>
              <div style={{ color: '#FAFAFA', fontSize: 12 }}>
                <MathFormula math={citation.equation} block={true} />
              </div>
            </div>
          )}

          {/* Confidence & Rationale */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 6, marginTop: 12 }}>
            <div>
              <span style={{ color: 'var(--sail-500)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                Confidence & Calibration
              </span>
              <div style={{ color: 'var(--sail-200)', fontSize: 11, fontWeight: 500 }}>
                {citation.confidence}
              </div>
            </div>
            <div>
              <span style={{ color: 'var(--sail-500)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
                Why This Grounding Matters
              </span>
              <div style={{ color: 'var(--sail-300)', fontSize: 11, marginTop: 2 }}>
                {citation.rationale}
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </span>
  );
};

export default CitationToken;
