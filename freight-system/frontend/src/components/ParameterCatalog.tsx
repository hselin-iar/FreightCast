import React, { useState, useMemo } from 'react';
import type { ParameterItem } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  parameters: ParameterItem[];
  loading: boolean;
}

export const ParameterCatalog: React.FC<Props> = ({ parameters, loading }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');

  const categories = useMemo(() => {
    const set = new Set<string>();
    parameters.forEach((p) => set.add(p.category));
    return ['All', ...Array.from(set)];
  }, [parameters]);

  const filteredParams = useMemo(() => {
    return parameters.filter((p) => {
      const matchesCategory = selectedCategory === 'All' || p.category === selectedCategory;
      const matchesSearch =
        searchTerm === '' ||
        p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.source.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.notes.toLowerCase().includes(searchTerm.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [parameters, selectedCategory, searchTerm]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* ── Search & Filter Header ── */}
      <div
        className="panel panel-tinted"
        style={{
          padding: '16px 20px',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        {/* Search Box */}
        <div style={{ flex: '1 1 280px', maxWidth: 400 }}>
          <input
            type="text"
            className="input-field"
            placeholder="Search parameter, source, or authority..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ width: '100%', fontSize: 13 }}
          />
        </div>

        {/* Category Chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {categories.map((cat) => {
            const isActive = cat === selectedCategory;
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                style={{
                  padding: '6px 14px',
                  borderRadius: 20,
                  fontSize: 11.5,
                  fontWeight: 700,
                  cursor: 'pointer',
                  border: isActive ? '2px solid var(--accent-dim)' : '1px solid var(--sail-700)',
                  backgroundColor: isActive ? 'var(--accent-bg)' : '#ffffff',
                  color: isActive ? 'var(--text-accent)' : 'var(--sail-300)',
                  transition: 'all 0.15s ease',
                }}
              >
                {cat}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Table ── */}
      <div className="panel panel-tinted" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr
                style={{
                  borderBottom: '2px solid var(--sail-800)',
                  backgroundColor: 'var(--sail-950)',
                  textAlign: 'left',
                  color: 'var(--sail-500)',
                  fontWeight: 700,
                }}
              >
                <th style={{ padding: '12px 16px' }}>Parameter Name</th>
                <th style={{ padding: '12px 16px' }}>Value</th>
                <th style={{ padding: '12px 16px' }}>Classification</th>
                <th style={{ padding: '12px 16px' }}>Data Source / Authority Citation</th>
                <th style={{ padding: '12px 16px' }}>Verified</th>
                <th style={{ padding: '12px 16px' }}>Operational Notes</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} style={{ padding: 28, textAlign: 'center', color: 'var(--sail-400)' }}>
                    Loading grounded parameter catalog...
                  </td>
                </tr>
              ) : filteredParams.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 28, textAlign: 'center', color: 'var(--sail-400)' }}>
                    No parameters match your search criteria.
                  </td>
                </tr>
              ) : (
                filteredParams.map((p, idx) => (
                  <tr
                    key={idx}
                    style={{
                      borderBottom: '1px solid var(--sail-800)',
                      backgroundColor: idx % 2 === 0 ? '#ffffff' : 'var(--sail-900)',
                    }}
                  >
                    <td style={{ padding: '12px 16px', fontWeight: 700, color: 'var(--sail-100)' }}>
                      {p.name}
                      <span
                        style={{
                          display: 'block',
                          fontSize: 10.5,
                          color: 'var(--sail-500)',
                          fontWeight: 500,
                          marginTop: 2,
                        }}
                      >
                        {p.category}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', fontFamily: 'var(--f-mono)', color: 'var(--sail-100)', fontWeight: 700 }}>
                      {p.value} <span style={{ fontSize: 11, color: 'var(--sail-500)', fontWeight: 400 }}>{p.unit}</span>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <ProvenanceBadge provenance={p.provenance} />
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--sail-200)', fontSize: 11.5, fontWeight: 500 }}>
                      {p.source}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {p.verified ? (
                        <span style={{ color: '#047857', fontSize: 11.5, fontWeight: 700 }}>
                          ✓ Signed Off
                        </span>
                      ) : (
                        <span style={{ color: '#b45309', fontSize: 11.5 }}>
                          Pending
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--sail-300)', fontSize: 11.5, maxWidth: 300, lineHeight: 1.4 }}>
                      {p.notes}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ParameterCatalog;
