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
    <div className="col-12 col-space">
      {/* ── Search & Filter Panel ── */}
      <section className="panel">
        <div className="panel-hd">
          <span className="panel-title">Filter & Search Grounded Evidence</span>
          <span className="panel-meta">{filteredParams.length} of {parameters.length} parameters</span>
        </div>
        <div
          className="panel-body"
          style={{
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
                    padding: '5px 12px',
                    borderRadius: 'var(--r)',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: isActive ? '2px solid var(--accent-dim)' : '1px solid var(--sail-800)',
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--sail-900)',
                    color: isActive ? 'var(--text-accent)' : 'var(--sail-400)',
                    transition: 'all 0.12s ease',
                  }}
                >
                  {cat}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Table Panel ── */}
      <section className="panel">
        <div className="panel-hd">
          <span className="panel-title">Verified Parameter Encyclopedia</span>
          <span className="panel-meta">audit trail · signed off</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr
                  style={{
                    borderBottom: '1px solid var(--sail-800)',
                    background: 'var(--sail-800)',
                    textAlign: 'left',
                    color: 'var(--sail-500)',
                    fontWeight: 600,
                  }}
                >
                  <th style={{ padding: '10px 16px' }}>Parameter Name</th>
                  <th style={{ padding: '10px 16px' }}>Value</th>
                  <th style={{ padding: '10px 16px' }}>Classification</th>
                  <th style={{ padding: '10px 16px' }}>Data Source / Authority Citation</th>
                  <th style={{ padding: '10px 16px' }}>Status</th>
                  <th style={{ padding: '10px 16px' }}>Operational Notes</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 28, textAlign: 'center', color: 'var(--sail-500)' }}>
                      Loading grounded parameter catalog...
                    </td>
                  </tr>
                ) : filteredParams.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 28, textAlign: 'center', color: 'var(--sail-500)' }}>
                      No parameters match your search criteria.
                    </td>
                  </tr>
                ) : (
                  filteredParams.map((p, idx) => (
                    <tr
                      key={idx}
                      style={{
                        borderBottom: '1px solid var(--sail-800)',
                        backgroundColor: idx % 2 === 0 ? 'var(--sail-900)' : 'color-mix(in srgb, var(--sail-900) 80%, var(--sail-950))',
                      }}
                    >
                      <td style={{ padding: '12px 16px', fontWeight: 600, color: 'var(--sail-100)' }}>
                        {p.name}
                        <span
                          style={{
                            display: 'block',
                            fontSize: 11,
                            color: 'var(--sail-500)',
                            fontWeight: 400,
                            marginTop: 2,
                          }}
                        >
                          {p.category}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', fontFamily: 'var(--f-mono)', color: 'var(--sail-100)', fontWeight: 600 }}>
                        {p.value} <span style={{ fontSize: 11, color: 'var(--sail-500)', fontWeight: 400 }}>{p.unit}</span>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <ProvenanceBadge provenance={p.provenance} />
                      </td>
                      <td style={{ padding: '12px 16px', color: 'var(--sail-300)', fontSize: 12 }}>
                        {p.source}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        {p.verified ? (
                          <span style={{ color: 'var(--badge-measured-text)', fontSize: 12, fontWeight: 700 }}>
                            ✓ Verified
                          </span>
                        ) : (
                          <span style={{ color: 'var(--badge-assumed-text)', fontSize: 12 }}>
                            Pending
                          </span>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px', color: 'var(--sail-400)', fontSize: 12, maxWidth: 320, lineHeight: 1.4 }}>
                        {p.notes}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ParameterCatalog;
