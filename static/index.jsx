import React, { useMemo, useState } from "react";
import {
  Wind,
  Thermometer,
  Waves,
  Activity,
  Skull,
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Leaf,
  Clock,
} from "lucide-react";

const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

const TIME_HORIZONS = [
  { years: 10, label: "10 yr", factor: 1 },
  { years: 50, label: "50 yr", factor: 1.35 },
  { years: 100, label: "100 yr", factor: 1.75 },
];

const STATUS_LEVELS = [
  {
    key: "stable",
    threshold: 0.25,
    label: "Stable",
    tagline: "Readings within tolerable bounds.",
    color: "#39FF88",
    glow: "rgba(57,255,136,0.35)",
    icon: ShieldCheck,
  },
  {
    key: "elevated",
    threshold: 0.5,
    label: "Elevated",
    tagline: "Degradation is measurable and accelerating.",
    color: "#FFB020",
    glow: "rgba(255,176,32,0.35)",
    icon: AlertTriangle,
  },
  {
    key: "hazardous",
    threshold: 0.75,
    label: "Hazardous",
    tagline: "Exposure carries immediate, compounding harm.",
    color: "#FF6A3D",
    glow: "rgba(255,106,61,0.4)",
    icon: ShieldAlert,
  },
  {
    key: "crisis",
    threshold: Infinity,
    label: "Irreversible crisis",
    tagline: "Beyond the threshold current models can recover from.",
    color: "#FF2B4A",
    glow: "rgba(255,43,74,0.5)",
    icon: Skull,
  },
];

function resolveStatus(score) {
  return STATUS_LEVELS.find((level) => score < level.threshold) ?? STATUS_LEVELS[STATUS_LEVELS.length - 1];
}

function computeMetrics({ aqi, co2, waste, years, remediation }) {
  const horizon = TIME_HORIZONS.find((h) => h.years === years) ?? TIME_HORIZONS[0];
  const remediationFactor = remediation ? 0.42 : 1;

  const aqiScore = clamp(aqi / 500, 0, 1);
  const co2Score = clamp((co2 - 280) / (1000 - 280), 0, 1);
  const wasteScore = clamp(waste / 100, 0, 1);

  const rawComposite =
    (aqiScore * 0.35 + co2Score * 0.4 + wasteScore * 0.25) * horizon.factor * remediationFactor;
  const composite = clamp(rawComposite, 0, 1);

  const respiratoryRisk = Math.round(clamp(aqiScore * 100 * horizon.factor * remediationFactor, 0, 100));
  const warmingAnomaly = clamp(1.1 + co2Score * 3.6 * horizon.factor * remediationFactor, 0.6, 8.5);
  const microplasticMultiplier = clamp(1 + wasteScore * 9 * horizon.factor * remediationFactor, 1, 20);

  return {
    composite,
    respiratoryRisk,
    warmingAnomaly: warmingAnomaly.toFixed(1),
    microplasticMultiplier: microplasticMultiplier.toFixed(1),
    status: resolveStatus(composite),
  };
}

function SliderField({ icon: Icon, label, value, unit, min, max, step, onChange, accent }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[13px] font-medium text-zinc-300">
          <Icon className="h-4 w-4" style={{ color: accent }} strokeWidth={1.75} />
          {label}
        </div>
        <span className="font-mono text-[13px] tabular-nums text-zinc-100">
          {value}
          <span className="ml-0.5 text-zinc-500">{unit}</span>
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ accentColor: accent }}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-zinc-800
          [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none
          [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2
          [&::-webkit-slider-thumb]:border-black [&::-webkit-slider-thumb]:shadow-[0_0_8px_var(--thumb-glow)]
          [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:appearance-none
          [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-black"
      />
    </div>
  );
}

function StatCard({ icon: Icon, label, value, unit, sub, accent }) {
  return (
    <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/60 p-4">
      <div className="mb-3 flex items-center gap-2 text-[12px] text-zinc-500">
        <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-[28px] font-medium leading-none tabular-nums" style={{ color: accent }}>
          {value}
        </span>
        <span className="text-[13px] text-zinc-500">{unit}</span>
      </div>
      <p className="mt-2 text-[12px] leading-snug text-zinc-500">{sub}</p>
    </div>
  );
}

export default function EnvironmentalHealthDashboard() {
  const [aqi, setAqi] = useState(180);
  const [co2, setCo2] = useState(520);
  const [waste, setWaste] = useState(45);
  const [years, setYears] = useState(10);
  const [remediation, setRemediation] = useState(false);

  const metrics = useMemo(
    () => computeMetrics({ aqi, co2, waste, years, remediation }),
    [aqi, co2, waste, years, remediation]
  );

  const StatusIcon = metrics.status.icon;
  const ringDeg = Math.round(metrics.composite * 360);

  return (
    <div
      className="min-h-screen w-full text-zinc-200"
      style={{
        background:
          "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(255,255,255,0.04), transparent 60%), #030303",
      }}
    >
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-10 flex items-center justify-between border-b border-zinc-900 pb-6">
          <div>
            <h1 className="text-[20px] font-semibold tracking-tight text-zinc-100">
              Environmental health monitor
            </h1>
            <p className="mt-1 text-[13px] text-zinc-500">
              Live composite reading across air, atmosphere, and ocean systems.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setRemediation((r) => !r)}
            className="flex items-center gap-2.5 rounded-full border px-4 py-2 transition-colors"
            style={{
              borderColor: remediation ? "rgba(57,255,136,0.5)" : "rgba(255,255,255,0.08)",
              background: remediation ? "rgba(57,255,136,0.08)" : "transparent",
            }}
          >
            <Leaf
              className="h-4 w-4"
              strokeWidth={1.75}
              style={{ color: remediation ? "#39FF88" : "#52525b" }}
            />
            <span className="text-[13px] font-medium" style={{ color: remediation ? "#39FF88" : "#a1a1aa" }}>
              Remediation {remediation ? "active" : "off"}
            </span>
            <span
              className="relative h-4 w-7 rounded-full transition-colors"
              style={{ background: remediation ? "#1a3d2c" : "#27272a" }}
            >
              <span
                className="absolute top-0.5 h-3 w-3 rounded-full transition-all"
                style={{
                  left: remediation ? "14px" : "2px",
                  background: remediation ? "#39FF88" : "#71717a",
                }}
              />
            </span>
          </button>
        </header>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="space-y-6">
            <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-5">
              <h2 className="mb-5 text-[12px] font-medium text-zinc-500">Input controls</h2>
              <div className="space-y-6">
                <SliderField
                  icon={Wind}
                  label="Air quality index"
                  value={aqi}
                  unit="AQI"
                  min={0}
                  max={500}
                  step={1}
                  onChange={setAqi}
                  accent="#FFB020"
                />
                <SliderField
                  icon={Thermometer}
                  label="Atmospheric CO2"
                  value={co2}
                  unit="ppm"
                  min={280}
                  max={1000}
                  step={1}
                  onChange={setCo2}
                  accent="#FF6A3D"
                />
                <SliderField
                  icon={Waves}
                  label="Ocean waste density"
                  value={waste}
                  unit="idx"
                  min={0}
                  max={100}
                  step={1}
                  onChange={setWaste}
                  accent="#4FD3E8"
                />
              </div>
            </div>

            <div className="rounded-xl border border-zinc-900 bg-zinc-950/40 p-5">
              <div className="mb-4 flex items-center gap-2 text-[12px] font-medium text-zinc-500">
                <Clock className="h-3.5 w-3.5" strokeWidth={1.75} />
                Projection horizon
              </div>
              <div className="grid grid-cols-3 gap-2">
                {TIME_HORIZONS.map((h) => (
                  <button
                    key={h.years}
                    type="button"
                    onClick={() => setYears(h.years)}
                    className="rounded-md border px-3 py-2 text-[13px] font-medium transition-colors"
                    style={{
                      borderColor: years === h.years ? metrics.status.color : "rgba(255,255,255,0.08)",
                      color: years === h.years ? metrics.status.color : "#71717a",
                      background: years === h.years ? metrics.status.glow : "transparent",
                    }}
                  >
                    {h.label}
                  </button>
                ))}
              </div>
            </div>
          </aside>

          <main className="space-y-6">
            <div className="relative overflow-hidden rounded-xl border border-zinc-900 bg-zinc-950/40 p-8">
              <div
                className="pointer-events-none absolute inset-0 opacity-40 transition-all duration-700"
                style={{
                  background: `radial-gradient(circle at 50% 40%, ${metrics.status.glow}, transparent 65%)`,
                }}
              />
              <div className="relative flex flex-col items-center text-center">
                <div
                  className="relative flex h-40 w-40 items-center justify-center rounded-full transition-all duration-700"
                  style={{
                    background: `conic-gradient(${metrics.status.color} ${ringDeg}deg, #18181b ${ringDeg}deg)`,
                  }}
                >
                  <div className="flex h-32 w-32 items-center justify-center rounded-full bg-[#050505]">
                    <StatusIcon
                      className="h-11 w-11 transition-colors duration-700"
                      strokeWidth={1.5}
                      style={{ color: metrics.status.color }}
                    />
                  </div>
                </div>
                <h2
                  className="mt-6 text-[26px] font-semibold tracking-tight transition-colors duration-700"
                  style={{ color: metrics.status.color }}
                >
                  {metrics.status.label}
                </h2>
                <p className="mt-1.5 max-w-sm text-[13px] text-zinc-500">{metrics.status.tagline}</p>
                <p className="mt-4 font-mono text-[12px] text-zinc-600">
                  composite severity {(metrics.composite * 100).toFixed(0)} / 100
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StatCard
                icon={Activity}
                label="Respiratory health risk"
                value={metrics.respiratoryRisk}
                unit="/ 100"
                sub={`Modeled exposure risk at the ${years}-year horizon.`}
                accent="#FFB020"
              />
              <StatCard
                icon={Thermometer}
                label="Projected warming anomaly"
                value={`+${metrics.warmingAnomaly}`}
                unit="C"
                sub="Deviation from pre-industrial baseline."
                accent="#FF6A3D"
              />
              <StatCard
                icon={Waves}
                label="Microplastic ingestion"
                value={`${metrics.microplasticMultiplier}x`}
                unit="baseline"
                sub="Multiplier over current average human intake."
                accent="#4FD3E8"
              />
            </div>

            {remediation && (
              <div className="rounded-xl border border-[#1a3d2c] bg-[#39FF88]/[0.04] p-5">
                <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-[#39FF88]">
                  <Leaf className="h-4 w-4" strokeWidth={1.75} />
                  Active mitigation measures
                </div>
                <ul className="grid grid-cols-1 gap-2 text-[13px] text-zinc-400 sm:grid-cols-2">
                  <li>Emissions capture and filtration &mdash; cuts particulate load at source.</li>
                  <li>Accelerated renewable transition &mdash; slows the CO2 accumulation rate.</li>
                  <li>Coastal cleanup and circular packaging &mdash; reduces waste density inflow.</li>
                  <li>Reforestation and soil carbon capture &mdash; pulls existing CO2 back down.</li>
                </ul>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
