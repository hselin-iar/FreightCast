import React, { useState } from 'react';
import CitationToken from './CitationToken';
import type { CitationItem } from '../lib/types';

export const EvidencePrimer: React.FC = () => {
  const [activeChapter, setActiveChapter] = useState<number>(1);

  const citations: Record<string, CitationItem> = {
    admiralty_law: {
      id: 'admiralty_law',
      token: 'Admiralty Coefficient Law',
      title: 'Cubic Speed-Power Law',
      source: 'Principles of Naval Architecture (PNA)',
      equation: 'Engine Power P = (Δ^(2/3) * V^3) / C_adm',
      provenance: 'measured',
      confidence: 'High (Hydrodynamic Physical Law)',
      rationale: 'Governs vessel drag in seawater: doubling speed requires 8x the engine power.',
    },
    sfoc_metric: {
      id: 'sfoc_metric',
      token: 'Specific Fuel Consumption (SFOC)',
      title: 'Main Engine Specific Fuel Consumption',
      source: 'MAN Energy Solutions 6S70ME-C Test Bed Data',
      equation: 'SFOC = 165.2 g / kWh (ISO standard conditions)',
      provenance: 'measured',
      confidence: 'High (Marine Engine Manufacturer Data)',
      rationale: 'Directly converts nautical shaft power into metric tonnes of VLSFO burned per day.',
    },
    ukc_policy: {
      id: 'ukc_policy',
      token: 'Under-Keel Clearance (UKC)',
      title: 'Under-Keel Clearance Standard',
      source: 'Ministry of Ports, Shipping and Waterways Marine Circular',
      equation: 'UKC_min = 1.50m (Channel) / 1.00m (Berth Basin)',
      provenance: 'measured',
      confidence: 'High (Statutory Safety Requirement)',
      rationale: 'Minimum vertical water cushion required beneath vessel keel to prevent squat grounding.',
    },
    gst_rcm: {
      id: 'gst_rcm',
      token: 'GST Reverse Charge Mechanism (5%)',
      title: 'Indian Maritime Ocean Freight GST',
      source: 'GST Notification 12/2017 & Notification 8/2017 - Central Tax',
      equation: 'Tax = 5.0% * (Effective Post-Discount Freight Cost)',
      provenance: 'assumed',
      confidence: 'High (Statutory Tax Statute)',
      rationale: 'Indian importer must pay 5% IGST on ocean freight paid to foreign shipowners under RCM.',
    },
    prophet_additive: {
      id: 'prophet_additive',
      token: 'Prophet Additive Model',
      title: 'Generalized Additive Model (GAM)',
      source: 'Meta Prophet Time-Series Architecture',
      equation: 'y(t) = g(t) [trend] + s(t) [seasonality] + h(t) [holidays] + ε_t',
      provenance: 'modeled',
      confidence: 'High (Cross-Validated Walk-Forward MAE < 1.4)',
      rationale: 'Decomposes Baltic Dry Index rate movements into isolated interpretable components.',
    },
    laytime_clause: {
      id: 'laytime_clause',
      token: 'Reversible Laytime Clause',
      title: 'Charterparty Laytime Calculation',
      source: 'Standard GENCON 1994 / NYPE 93 Charterparty',
      equation: 'Allowed Laytime = Cargo_Quantity / Port_Handling_Rate',
      provenance: 'assumed',
      confidence: 'High (Contractual Standard)',
      rationale: 'Defines the exact hours the charterer may occupy the berth before daily demurrage begins.',
    },
  };

  const chapters = [
    { id: 1, title: '1. Voyage Physics & Fuel Hydrodynamics', category: 'Naval Architecture' },
    { id: 2, title: '2. Port Bathymetry & Tidal Mechanics', category: 'Port Engineering' },
    { id: 3, title: '3. Econometric Rate Forecasting', category: 'Time-Series Econometrics' },
    { id: 4, title: '4. Statutory GST & Commercial Policy', category: 'Maritime Law & Tax' },
  ];

  return (
    <>
      {/* ── LEFT COLUMN (col-3): Chapter Navigator ── */}
      <div className="col-3 col-space">
        <section className="panel">
          <div className="panel-hd">
            <span className="panel-title">Evidence Chapters</span>
            <span className="panel-meta">4 chapters</span>
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {chapters.map((ch) => {
              const isActive = ch.id === activeChapter;
              return (
                <button
                  key={ch.id}
                  onClick={() => setActiveChapter(ch.id)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    padding: '12px 14px',
                    borderRadius: 'var(--r)',
                    border: isActive ? '2px solid var(--accent-dim)' : '1px solid var(--sail-800)',
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--sail-900)',
                    color: 'var(--sail-100)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.12s ease',
                  }}
                >
                  <span style={{ fontSize: 10, textTransform: 'uppercase', color: isActive ? 'var(--text-accent)' : 'var(--sail-500)', fontWeight: 700 }}>
                    {ch.category}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--sail-100)', marginTop: 2, lineHeight: 1.3 }}>
                    {ch.title}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="panel panel-tinted">
          <div className="panel-hd">
            <span className="panel-title">Mathematical Rigor</span>
            <span className="panel-meta">First-Principles</span>
          </div>
          <div className="panel-body" style={{ fontSize: 12, lineHeight: 1.6, color: 'var(--sail-400)' }}>
            Every equation and constant used by the MILP decision engine originates in naval physics, statutory tax circulars, or validated econometric models.
          </div>
        </section>
      </div>

      {/* ── RIGHT COLUMN (col-9): Chapter Content ── */}
      <div className="col-9 col-space">
        <section className="panel">
          {activeChapter === 1 && (
            <>
              <div className="panel-hd">
                <span className="panel-title">Naval Architecture & Hydrodynamics</span>
                <span className="panel-meta">Principles of Naval Architecture</span>
              </div>
              <div className="panel-body">
                <h2 style={{ fontSize: 18, color: 'var(--sail-100)', fontWeight: 700, margin: '0 0 14px' }}>
                  How Nautical Distance, Hull Resistance, and Bunker Fuel Burn are Calculated
                </h2>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)', marginBottom: 16 }}>
                  In international deep-sea shipping, voyage operating expenses are fundamentally dictated by fluid mechanics. 
                  When a bulk carrier moves through seawater, the friction between the hull surface and water follows the classic{' '}
                  <CitationToken citation={citations.admiralty_law}>Admiralty Coefficient Law</CitationToken>. 
                  This relationship dictates that the propulsive shaft power required to overcome hydrodynamic drag increases with the 
                  <strong> cube of the vessel's speed</strong> (P ∝ V³).
                </p>

                <div
                  style={{
                    backgroundColor: 'var(--sail-800)',
                    borderRadius: 'var(--r)',
                    padding: '12px 16px',
                    border: '1px solid var(--sail-700)',
                    fontFamily: 'var(--f-mono)',
                    fontSize: 12,
                    color: 'var(--sail-100)',
                    fontWeight: 600,
                    marginBottom: 18,
                  }}
                >
                  <div style={{ color: 'var(--sail-500)', fontSize: 10, marginBottom: 4 }}>FIRST-PRINCIPLES FUEL BURN EQUATION:</div>
                  Daily VLSFO Burn (t/day) = (Distance_NM / (Speed_kts * 24)) * Main_Engine_Power_kW * SFOC * 10^-6
                </div>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)', marginBottom: 18 }}>
                  The engine efficiency is governed by verified manufacturer{' '}
                  <CitationToken citation={citations.sfoc_metric}>Specific Fuel Consumption (SFOC)</CitationToken> test curves. 
                  Because larger vessels like Capesize carriers carry <strong>180,000 tonnes of cargo</strong> while consuming only ~42 t/day of fuel (0.00023 tonnes/MT-carried/day), 
                  their unit freight efficiency is <strong>38% superior to a Supramax</strong> (which burns ~24 t/day to move just 55,000 tonnes, or 0.00043 tonnes/MT-carried/day).
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginTop: 20 }}>
                  <div style={{ backgroundColor: 'var(--sail-900)', padding: 16, borderRadius: 'var(--r)', border: '1px solid var(--sail-800)', boxShadow: 'var(--shadow-panel)' }}>
                    <div style={{ fontSize: 11, color: 'var(--sail-500)', textTransform: 'uppercase', fontWeight: 700 }}>Capesize Burn</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--sail-100)', marginTop: 2 }}>42.0 t/day</div>
                    <div style={{ fontSize: 11, color: 'var(--badge-measured-text)', fontWeight: 600, marginTop: 4 }}>0.23 kg fuel / tonne cargo</div>
                  </div>
                  <div style={{ backgroundColor: 'var(--sail-900)', padding: 16, borderRadius: 'var(--r)', border: '1px solid var(--sail-800)', boxShadow: 'var(--shadow-panel)' }}>
                    <div style={{ fontSize: 11, color: 'var(--sail-500)', textTransform: 'uppercase', fontWeight: 700 }}>Panamax Burn</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--sail-100)', marginTop: 2 }}>30.0 t/day</div>
                    <div style={{ fontSize: 11, color: 'var(--badge-modeled-text)', fontWeight: 600, marginTop: 4 }}>0.40 kg fuel / tonne cargo</div>
                  </div>
                  <div style={{ backgroundColor: 'var(--sail-900)', padding: 16, borderRadius: 'var(--r)', border: '1px solid var(--sail-800)', boxShadow: 'var(--shadow-panel)' }}>
                    <div style={{ fontSize: 11, color: 'var(--sail-500)', textTransform: 'uppercase', fontWeight: 700 }}>Supramax Burn</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--sail-100)', marginTop: 2 }}>24.0 t/day</div>
                    <div style={{ fontSize: 11, color: 'var(--badge-assumed-text)', fontWeight: 600, marginTop: 4 }}>0.43 kg fuel / tonne cargo</div>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeChapter === 2 && (
            <>
              <div className="panel-hd">
                <span className="panel-title">Port Engineering & Bathymetry</span>
                <span className="panel-meta">National Hydrographic Office</span>
              </div>
              <div className="panel-body">
                <h2 style={{ fontSize: 18, color: 'var(--sail-100)', fontWeight: 700, margin: '0 0 14px' }}>
                  Why Indian East-Coast Ports Have Radically Different Physical Constraints
                </h2>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)', marginBottom: 16 }}>
                  The Indian eastern seaboard features diverse geological and marine environments, ranging from protected deep-water rocky headlands to silt-laden estuarine river mouths. 
                  Every vessel calling at an Indian port must maintain a mandatory safety cushion known as{' '}
                  <CitationToken citation={citations.ukc_policy}>Under-Keel Clearance (UKC)</CitationToken>.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 18 }}>
                  <div style={{ backgroundColor: 'var(--sail-900)', padding: 16, borderRadius: 'var(--r)', border: '1px solid var(--sail-800)', boxShadow: 'var(--shadow-panel)' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--badge-modeled-text)', marginBottom: 6 }}>Gangavaram Port (Deep Basin)</div>
                    <div style={{ fontSize: 13, color: 'var(--sail-200)', lineHeight: 1.6 }}>
                      Constructed with deep-water breakwaters on a rocky coast. Permissible draft of <strong>19.5 meters</strong> allows full Capesize vessels (180,000 MT) to berth without tidal restriction or lightening.
                    </div>
                  </div>
                  <div style={{ backgroundColor: 'var(--sail-900)', padding: 16, borderRadius: 'var(--r)', border: '1px solid var(--sail-800)', boxShadow: 'var(--shadow-panel)' }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--badge-assumed-text)', marginBottom: 6 }}>Dhamra Port (Estuarine Tides)</div>
                    <div style={{ fontSize: 13, color: 'var(--sail-200)', lineHeight: 1.6 }}>
                      Located at the mouth of the Dhamra River. Permissible draft is <strong>14.0 meters</strong>, meaning Capesize vessels cannot physically enter and cargo must be split across Panamax vessels.
                    </div>
                  </div>
                </div>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)' }}>
                  Paradip Port offers an intermediate draft of 14.5m, accommodating partially laden Capesize or geared Panamax vessels, but is susceptible to high swell during the South-West monsoon.
                </p>
              </div>
            </>
          )}

          {activeChapter === 3 && (
            <>
              <div className="panel-hd">
                <span className="panel-title">Econometric Forecasting & Machine Learning</span>
                <span className="panel-meta">Walk-Forward Cross-Validation</span>
              </div>
              <div className="panel-body">
                <h2 style={{ fontSize: 18, color: 'var(--sail-100)', fontWeight: 700, margin: '0 0 14px' }}>
                  How Machine Learning Models Forecast Freight Without Human Bias
                </h2>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)', marginBottom: 16 }}>
                  Freight rates in bulk chartering fluctuate according to global vessel supply, Chinese steel production cycles, and fuel spreads. 
                  Rather than relying on human gut feel, the system uses a trained{' '}
                  <CitationToken citation={citations.prophet_additive}>Prophet Additive Model</CitationToken>{' '}
                  calibrated with walk-forward cross-validation.
                </p>

                <div
                  style={{
                    backgroundColor: 'var(--sail-800)',
                    borderRadius: 'var(--r)',
                    padding: '12px 16px',
                    border: '1px solid var(--sail-700)',
                    fontFamily: 'var(--f-mono)',
                    fontSize: 12,
                    color: 'var(--sail-100)',
                    fontWeight: 600,
                    marginBottom: 18,
                  }}
                >
                  <div style={{ color: 'var(--sail-500)', fontSize: 10, marginBottom: 4 }}>TIME-SERIES DECOMPOSITION:</div>
                  Freight_Rate(t) = Macro_Trend(t) + Weekly_Seasonality(t) + Regressors(BDI, Bunker, IronOre) + Residual_Noise
                </div>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)' }}>
                  By isolating deterministic weekly fixtures from macro trend shifts, the model predicts rate dips across 7, 14, and 30-day horizons, allowing the MILP optimizer to schedule laycans at the cheapest point in the cycle.
                </p>
              </div>
            </>
          )}

          {activeChapter === 4 && (
            <>
              <div className="panel-hd">
                <span className="panel-title">Maritime Law & Commercial Policy</span>
                <span className="panel-meta">GST & BIMCO Standards</span>
              </div>
              <div className="panel-body">
                <h2 style={{ fontSize: 18, color: 'var(--sail-100)', fontWeight: 700, margin: '0 0 14px' }}>
                  Statutory Tax Obligations, Laytime Mechanics & Demurrage Liquidated Damages
                </h2>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)', marginBottom: 16 }}>
                  Freight accounting requires adhering to statutory tax frameworks and standard maritime charterparty clauses. 
                  Under Indian fiscal law, international freight paid to foreign shipowners is subject to the{' '}
                  <CitationToken citation={citations.gst_rcm}>GST Reverse Charge Mechanism (5%)</CitationToken>.
                </p>

                <div
                  style={{
                    backgroundColor: 'var(--sail-800)',
                    borderRadius: 'var(--r)',
                    padding: '12px 16px',
                    border: '1px solid var(--sail-700)',
                    fontFamily: 'var(--f-mono)',
                    fontSize: 12,
                    color: 'var(--sail-100)',
                    fontWeight: 600,
                    marginBottom: 18,
                  }}
                >
                  <div style={{ color: 'var(--sail-500)', fontSize: 10, marginBottom: 4 }}>STATUTORY TAX BASIS:</div>
                  Net Tax = 0.050 * (Base_Ocean_Freight - Forward_Commitment_Discount)
                </div>

                <p style={{ fontSize: 13.5, lineHeight: 1.8, color: 'var(--sail-200)' }}>
                  Furthermore, port laytime is governed by standard{' '}
                  <CitationToken citation={citations.laytime_clause}>Reversible Laytime Clauses</CitationToken>. 
                  If the port takes longer than the agreed laytime to discharge the cargo, the charterer pays daily demurrage ($24,000/day for Capesize, $16,000/day for Panamax). 
                  If discharge finishes ahead of laytime, despatch is earned at half the demurrage rate.
                </p>
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
};

export default EvidencePrimer;
