/**
 * WhatIfSliders.tsx — DOC2 §16.3 item 1 / DOC3 Dashboard sellable layer / Build Step 12
 *
 * Debounced (~400ms) live re-solve on three parameters:
 *   - cargo_quantity
 *   - timing_flexibility_days
 *   - commitment_benchmark_pct
 *
 * IMPORTANT CONTRACT (from DOC4 Step 12 "Common drift"):
 *   - Calls the SAME getRecommendation() the form submit calls — no separate code path.
 *   - Cancels stale in-flight requests via AbortController (not just delays firing).
 *   - Does NO cost math; purely composes a new RecommendationRequest and calls the parent.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { RecommendationRequest } from '../lib/types';

interface Props {
  /** The last successful request (pre-filled into sliders) */
  baseRequest: RecommendationRequest;
  /** Called each time the debounced slider fires — parent re-fetches and updates result */
  onRequestChange: (req: RecommendationRequest, signal: AbortSignal) => void;
  /** True while the parent is fetching — shows spinner in the slider header */
  loading: boolean;
}

/** Debounce hook: fires fn only after delay ms of silence */
function useDebouncedCallback<T extends unknown[]>(
  fn: (...args: T) => void,
  delay: number,
): (...args: T) => void {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fnRef  = useRef(fn);
  fnRef.current = fn;
  return useCallback((...args: T) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => fnRef.current(...args), delay);
  }, [delay]);
}

/* ── Slider row ─────────────────────────────────────────────── */
interface SliderRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
  id: string;
}

function SliderRow({ label, value, min, max, step, format, onChange, id }: SliderRowProps) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
        <label htmlFor={id} style={{ fontSize: 12, color: 'var(--sail-400)' }}>{label}</label>
        <span style={{ fontSize: 14, fontFamily: 'var(--f-mono)', fontWeight: 600, color: 'var(--accent-hi)' }}>
          {format(value)}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%' }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9,
        fontFamily: 'var(--f-mono)', color: 'var(--sail-600)', marginTop: 1 }}>
        <span>{format(min)}</span>
        <span style={{ color: 'var(--sail-500)' }}>{pct.toFixed(0)}%</span>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}

/* ── WhatIfSliders ──────────────────────────────────────────── */
const WhatIfSliders: React.FC<Props> = ({ baseRequest, onRequestChange, loading }) => {
  const [qty,   setQty]   = useState(baseRequest.cargo_quantity);
  const [flex,  setFlex]  = useState(baseRequest.timing_flexibility_days);
  const [bench, setBench] = useState(baseRequest.commitment_benchmark_pct ?? 95);

  const abortRef = useRef<AbortController | null>(null);

  // Sync if parent resets the base request (e.g. form re-submit)
  useEffect(() => {
    setQty(baseRequest.cargo_quantity);
    setFlex(baseRequest.timing_flexibility_days);
    setBench(baseRequest.commitment_benchmark_pct ?? 95);
  }, [baseRequest]);

  const fireRequest = useCallback((newQty: number, newFlex: number, newBench: number) => {
    // Cancel stale in-flight request before sending new one
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    onRequestChange(
      { ...baseRequest, cargo_quantity: newQty, timing_flexibility_days: newFlex, commitment_benchmark_pct: newBench },
      abortRef.current.signal,
    );
  }, [baseRequest, onRequestChange]);

  const debouncedFire = useDebouncedCallback(fireRequest, 400);

  // Cleanup on unmount
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const handleQty   = (v: number) => { setQty(v);   debouncedFire(v, flex, bench); };
  const handleFlex  = (v: number) => { setFlex(v);  debouncedFire(qty, v, bench); };
  const handleBench = (v: number) => { setBench(v); debouncedFire(qty, flex, v); };

  return (
    <section className="panel" id="what-if-sliders">
      <div className="panel-hd">
        <span className="panel-title">What-If Sliders</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {loading && <span className="spinner" />}
          <span className="panel-meta">400ms debounce · stale cancel</span>
        </div>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <SliderRow
          id="slider-qty"
          label="Cargo quantity"
          value={qty} min={10000} max={200000} step={5000}
          format={v => `${(v / 1000).toFixed(0)}k MT`}
          onChange={handleQty}
        />
        <SliderRow
          id="slider-flex"
          label="Timing flexibility"
          value={flex} min={1} max={60} step={1}
          format={v => `${v}d`}
          onChange={handleFlex}
        />
        <SliderRow
          id="slider-bench"
          label="commitment_benchmark"
          value={bench} min={80} max={100} step={0.5}
          format={v => `${v.toFixed(1)}%`}
          onChange={handleBench}
        />
        <p className="infer">
          Drag to re-solve live. Stale in-flight requests are cancelled (not just delayed).
          Same <span style={{ fontFamily: 'var(--f-mono)' }}>/recommendation</span> call as the form — no separate code path.
        </p>
      </div>
    </section>
  );
};

export default WhatIfSliders;
