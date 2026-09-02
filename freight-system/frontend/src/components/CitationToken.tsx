import React, { useState, useRef, useEffect } from 'react';
import type { CitationItem } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  citation: CitationItem;
  children: React.ReactNode;
}

export const CitationToken: React.FC<Props> = ({ citation, children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

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
      ? '#059669'
      : citation.provenance === 'modeled'
      ? '#2563eb'
      : '#d97706';

  const badgeBg =
    citation.provenance === 'measured'
      ? 'rgba(16, 185, 129, 0.14)'
      : citation.provenance === 'modeled'
      ? 'rgba(59, 130, 246, 0.14)'
      : 'rgba(245, 158, 11, 0.14)';

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
          color: 'var(--sail-100)',
          fontWeight: 600,
          cursor: 'pointer',
          padding: '1px 3px',
          borderRadius: 3,
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
      {isOpen && (
        <div
          ref={popoverRef}
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 8px)',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 360,
            maxWidth: '90vw',
            backgroundColor: '#ffffff',
            border: `1.5px solid ${badgeBorder}`,
            boxShadow: '0 12px 30px rgba(0, 0, 0, 0.15)',
            borderRadius: 8,
            padding: '14px 16px',
            zIndex: 9999,
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
            <div
              style={{
                marginBottom: 8,
                padding: '6px 10px',
                backgroundColor: 'var(--sail-950)',
                borderRadius: 4,
                border: '1px solid var(--sail-800)',
                fontFamily: 'var(--f-mono)',
                fontSize: 11,
                color: 'var(--sail-100)',
                fontWeight: 600,
              }}
            >
              <span style={{ color: 'var(--sail-500)', fontSize: 9, display: 'block', marginBottom: 2 }}>
                FORMULA / DERIVATION:
              </span>
              {citation.equation}
            </div>
          )}

          {/* Confidence & Rationale */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 6 }}>
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

          {/* Arrow */}
          <div
            style={{
              position: 'absolute',
              bottom: -6,
              left: '50%',
              transform: 'translateX(-50%) rotate(45deg)',
              width: 10,
              height: 10,
              backgroundColor: '#ffffff',
              borderRight: `1.5px solid ${badgeBorder}`,
              borderBottom: `1.5px solid ${badgeBorder}`,
            }}
          />
        </div>
      )}
    </span>
  );
};

export default CitationToken;
