import React, { useState, useRef, useLayoutEffect, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { DataSourceDefinition } from '../lib/dataSources';
import ProvenanceBadge from './ProvenanceBadge';
import MathFormula from './MathFormula';

interface Props {
  term: string;
  definition: DataSourceDefinition;
  children?: React.ReactNode;
}

export const DataTermToken: React.FC<Props> = ({ term, definition, children }) => {
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
        top: rect.top + window.scrollY - 8,
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
    definition.provenance === 'measured'
      ? 'var(--emerald)'
      : definition.provenance === 'modeled'
      ? '#3b82f6'
      : 'var(--warn)';

  const badgeBg =
    definition.provenance === 'measured'
      ? 'var(--badge-measured-bg)'
      : definition.provenance === 'modeled'
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
          borderBottom: `1.5px dotted ${badgeBorder}`,
          color: 'var(--sail-100)',
          fontWeight: 600,
          cursor: 'help',
          padding: '0 2px',
          borderRadius: 2,
          backgroundColor: isOpen ? badgeBg : 'transparent',
          transition: 'all 0.15s ease',
        }}
      >
        {children || term}
      </span>

      {/* Floating Evidence Inspector Popover */}
      {isOpen &&
        createPortal(
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
              <div>
                <span style={{ fontWeight: 700, color: 'var(--sail-100)', fontSize: 13 }}>
                  {definition.title}
                </span>
                {definition.variable && (
                  <span style={{ marginLeft: 6, display: 'inline-block', verticalAlign: 'middle' }}>
                    <MathFormula math={definition.variable} block={false} style={{ fontSize: 11.5, color: 'var(--text-accent)' }} />
                  </span>
                )}
              </div>
              <ProvenanceBadge provenance={definition.provenance} />
            </div>

            {/* Source Authority */}
            <div style={{ marginBottom: 8 }}>
              <span
                style={{
                  color: 'var(--sail-500)',
                  fontSize: 10,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  fontWeight: 600,
                }}
              >
                Data Source / Authority
              </span>
              <div style={{ color: 'var(--sail-100)', fontWeight: 600, marginTop: 2 }}>
                {definition.source}
              </div>
            </div>

            {/* Mathematical Equation */}
            {definition.equation && (
              <div
                style={{
                  marginTop: 8,
                  marginBottom: 8,
                  padding: '8px 10px',
                  backgroundColor: 'var(--ink-700)',
                  borderLeft: '2px solid var(--accent)',
                  borderRadius: '0 4px 4px 0',
                  overflowX: 'auto',
                }}
              >
                <div style={{ fontSize: 9.5, color: 'var(--sail-400)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600, marginBottom: 4 }}>
                  Mathematical Grounding
                </div>
                <div style={{ color: '#FAFAFA', fontSize: 12 }}>
                  <MathFormula math={definition.equation} block={true} />
                </div>
              </div>
            )}

            {/* Description & Confidence */}
            <div style={{ fontSize: 11.5, color: 'var(--sail-300)', marginTop: 4 }}>
              {definition.description}
            </div>

            {definition.confidence && (
              <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px dashed var(--sail-800)', fontSize: 10.5, color: 'var(--sail-400)' }}>
                <strong style={{ color: 'var(--sail-300)' }}>Calibration: </strong>
                {definition.confidence}
              </div>
            )}
          </div>,
          document.body
        )}
    </span>
  );
};

export default DataTermToken;
