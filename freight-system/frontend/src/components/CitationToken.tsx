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
      const halfWidth = 180;
      const idealLeft = rect.left + window.scrollX + rect.width / 2;
      const minLeft = halfWidth + 16;
      const maxLeft = Math.max(minLeft, window.innerWidth - halfWidth - 16);
      const clampedLeft = Math.max(minLeft, Math.min(maxLeft, idealLeft));

      // Check if space above, otherwise position below
      const spaceAbove = rect.top;
      const popoverTop = spaceAbove > 280
        ? rect.top + window.scrollY - 8 // Above trigger
        : rect.bottom + window.scrollY + 8; // Below trigger

      setPopoverCoords({
        top: popoverTop,
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
      ? 'var(--accent)'
      : 'var(--warn)';

  return (
    <span
      ref={triggerRef}
      style={{ position: 'relative', display: 'inline' }}
    >
      <span
        onClick={() => setIsOpen((prev) => !prev)}
        style={{
          borderBottom: `1.5px solid ${badgeBorder}`,
          color: '#FAFAFA',
          fontWeight: 600,
          cursor: 'pointer',
          padding: '1px 5px',
          borderRadius: 4,
          backgroundColor: isOpen
            ? 'color-mix(in srgb, var(--accent) 25%, transparent)'
            : 'color-mix(in srgb, var(--sail-700) 45%, transparent)',
          transition: 'all 0.15s ease',
        }}
        title="Click to inspect grounding authority & formula"
      >
        {children}
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
            width: 340,
            maxWidth: '90vw',
            backgroundColor: 'var(--sail-900)',
            border: `1.5px solid ${badgeBorder}`,
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.45)',
            borderRadius: 8,
            padding: '12px 14px',
            zIndex: 999999,
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontWeight: 700, color: 'var(--sail-100)', fontSize: 12.5 }}>
                {citation.title}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <ProvenanceBadge provenance={citation.provenance} />
              <button
                onClick={() => setIsOpen(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--sail-400)',
                  cursor: 'pointer',
                  fontSize: 14,
                  padding: '0 2px',
                  lineHeight: 1,
                }}
                title="Close"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Source Citation */}
          <div style={{ marginBottom: 8 }}>
            <span style={{ color: 'var(--sail-400)', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>
              Authority / Data Source
            </span>
            <div style={{ color: 'var(--sail-100)', fontWeight: 600, marginTop: 2, fontSize: 11.5 }}>
              {citation.source}
            </div>
          </div>

          {/* Governing Equation / Math (if present) */}
          {citation.equation && (
            <div style={{ marginTop: 6, padding: '6px 10px', backgroundColor: 'var(--ink-800)', borderLeft: '2px solid var(--accent)', borderRadius: '0 4px 4px 0', overflowX: 'auto' }}>
              <div style={{ fontSize: 9.5, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700, marginBottom: 3 }}>
                Mathematical Grounding
              </div>
              <div style={{ color: '#FAFAFA', fontSize: 11.5 }}>
                <MathFormula math={citation.equation} block={true} />
              </div>
            </div>
          )}

          {/* Confidence & Rationale */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            <div>
              <span style={{ color: 'var(--sail-400)', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>
                Why This Grounding Matters
              </span>
              <div style={{ color: 'var(--sail-300)', fontSize: 11, marginTop: 2, lineHeight: 1.4 }}>
                {citation.rationale}
              </div>
            </div>
            <div style={{ fontSize: 10, color: 'var(--sail-500)', fontFamily: 'var(--f-mono)', borderTop: '1px solid var(--sail-800)', paddingTop: 5 }}>
              Calibration: <span style={{ color: 'var(--sail-200)' }}>{citation.confidence}</span>
            </div>
          </div>
        </div>,
        document.body
      )}
    </span>
  );
};

export default CitationToken;
