/**
 * ForecastChart.tsx
 * DOC3: "ForecastChart.tsx — Recharts overlay of the confidence band
 *        and point estimate trajectory."
 * Build Step 11 scope: trajectory line + confidence band + provenance badge.
 * ScenarioFanChart (optimistic/pessimistic overlay) is Build Step 12.
 */
import React from 'react';
import {
  ResponsiveContainer,
  Area,
  Line,
  ComposedChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import type { ForecastResponse } from '../lib/types';
import ProvenanceBadge from './ProvenanceBadge';

interface Props {
  forecast: ForecastResponse;
}

/* Recharts custom tooltip */
function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-overlay)',
      border: '1px solid var(--border-bright)',
      borderRadius: 'var(--r-md)',
      padding: '8px 12px',
      fontSize: 11,
      fontFamily: 'var(--f-mono)',
      color: 'var(--text-body)',
      boxShadow: 'var(--shadow-md)',
    }}>
      <div style={{ color: 'var(--text-dim)', marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <span style={{ fontSize: 10, opacity: 0.7 }}>{p.name}</span>
          <span style={{ fontWeight: 600 }}>${p.value?.toFixed(2)}/t</span>
        </div>
      ))}
    </div>
  );
}

const ForecastChart: React.FC<Props> = ({ forecast }) => {
  /* Build chart data from trajectory + confidence band */
  const chartData = forecast.trajectory.map(pt => ({
    date:  pt.date,
    value: pt.value,
    lower: forecast.confidence_band.lower,
    upper: forecast.confidence_band.upper,
    band:  [forecast.confidence_band.lower, forecast.confidence_band.upper] as [number, number],
  }));

  /* Abbreviated x-axis labels */
  const xFmt = (d: string) => {
    try {
      const date = new Date(d);
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return d; }
  };

  const yDomain = (() => {
    const vals = chartData.map(d => d.value);
    const mn = Math.min(...vals, forecast.confidence_band.lower);
    const mx = Math.max(...vals, forecast.confidence_band.upper);
    const pad = (mx - mn) * 0.12;
    return [Math.floor(mn - pad), Math.ceil(mx + pad)];
  })();

  return (
    <div>
      {/* Header row */}
      <div style={{ padding: '10px 16px 8px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontFamily: 'var(--f-mono)', fontWeight: 600, color: 'var(--text-hi)', letterSpacing: '-0.5px' }}>
            ${forecast.point_estimate.toFixed(2)}
            <span style={{ fontSize: 11, color: 'var(--text-dim)', marginLeft: 4, fontWeight: 400 }}>/t</span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-faint)', marginTop: 2 }}>
            {forecast.horizon_days}d point estimate · {forecast.route}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          {forecast.is_high_uncertainty && (
            <span style={{
              fontSize: 9, padding: '2px 6px', borderRadius: 3, fontFamily: 'var(--f-mono)',
              fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.4px',
              background: 'var(--amber-bg)', border: '1px solid var(--amber-glow)', color: 'var(--amber)'
            }}>
              ⚠ High uncertainty
            </span>
          )}
          <span style={{
            fontSize: 9, padding: '2px 6px', borderRadius: 3, fontFamily: 'var(--f-mono)',
            fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px',
            background: 'var(--indigo-bg)', border: '1px solid rgba(99,102,241,0.2)', color: 'var(--indigo-hi)'
          }}>
            {forecast.model_used}
          </span>
          <ProvenanceBadge provenance={forecast.provenance} />
        </div>
      </div>

      {/* Chart */}
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="bandFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="#6366f1" stopOpacity={0.12} />
                <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
              </linearGradient>
            </defs>

            <CartesianGrid
              strokeDasharray="2 4"
              stroke="color-mix(in srgb, #ffffff 5%, transparent)"
              vertical={false}
            />

            <XAxis
              dataKey="date"
              tickFormatter={xFmt}
              tick={{ fill: 'var(--text-faint)', fontSize: 10, fontFamily: 'var(--f-mono)' }}
              axisLine={{ stroke: 'var(--border-dim)' }}
              tickLine={false}
              dy={6}
            />

            <YAxis
              domain={yDomain}
              tickFormatter={(v: number) => `$${v}`}
              tick={{ fill: 'var(--text-faint)', fontSize: 10, fontFamily: 'var(--f-mono)' }}
              axisLine={false}
              tickLine={false}
              width={46}
            />

            <Tooltip content={<ChartTooltip />} />

            {/* Confidence band — upper as area, lower as baseline */}
            <Area
              type="monotone"
              dataKey="upper"
              stroke="none"
              fill="url(#bandFill)"
              name="Upper band"
              legendType="none"
              activeDot={false}
            />
            <Area
              type="monotone"
              dataKey="lower"
              stroke="rgba(99,102,241,0.25)"
              strokeWidth={1}
              strokeDasharray="3 3"
              fill="var(--bg-base)"
              name="Lower band"
              legendType="none"
              activeDot={false}
            />

            {/* Point estimate line */}
            <Line
              type="monotone"
              dataKey="value"
              stroke="#6366f1"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#6366f1', stroke: 'var(--bg-base)', strokeWidth: 2 }}
              name="Forecast"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="chart-legend">
        <div className="legend-entry">
          <div className="legend-line" style={{ background: '#6366f1' }} />
          <span>{forecast.horizon_days}d forecast</span>
        </div>
        <div className="legend-entry">
          <div className="legend-line" style={{ background: 'rgba(99,102,241,0.3)', borderTop: '1px dashed rgba(99,102,241,0.4)' }} />
          <span>Confidence band</span>
        </div>
        {forecast.driver_explanation && (
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-dim)', fontStyle: 'italic', maxWidth: 240, textAlign: 'right' }}>
            {forecast.driver_explanation}
          </span>
        )}
      </div>
    </div>
  );
};

/* Skeleton shown while loading */
export function ForecastChartSkeleton() {
  return (
    <div style={{ padding: 16 }}>
      <div className="skel" style={{ width: 120, height: 22, marginBottom: 6 }} />
      <div className="skel" style={{ width: 220, height: 12, marginBottom: 16 }} />
      <div className="skel" style={{ width: '100%', height: 200 }} />
    </div>
  );
}

export default ForecastChart;
