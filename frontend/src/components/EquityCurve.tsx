"use client";

interface Props {
  data: number[];
  initial: number;
}

// Dependency-free SVG equity curve with a baseline at starting capital.
export function EquityCurve({ data, initial }: Props) {
  if (!data || data.length < 2) {
    return <div className="text-xs text-gray-500">Not enough data to plot.</div>;
  }

  const W = 800;
  const H = 240;
  const PAD = 10;
  const min = Math.min(...data, initial);
  const max = Math.max(...data, initial);
  const range = max - min || 1;

  const x = (i: number) => PAD + (i / (data.length - 1)) * (W - 2 * PAD);
  const y = (v: number) => H - PAD - ((v - min) / range) * (H - 2 * PAD);

  const line = data.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${PAD},${(H - PAD).toFixed(1)} ${line} ${(W - PAD).toFixed(1)},${(H - PAD).toFixed(1)}`;
  const baseY = y(initial).toFixed(1);
  const up = data[data.length - 1] >= initial;
  const stroke = up ? "#10b981" : "#f43f5e";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[240px]" preserveAspectRatio="none">
      <defs>
        <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.25" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* baseline = initial capital */}
      <line
        x1={PAD}
        x2={W - PAD}
        y1={baseY}
        y2={baseY}
        stroke="#6b7280"
        strokeWidth="1"
        strokeDasharray="4 4"
      />
      <polygon points={area} fill="url(#eq-fill)" />
      <polyline points={line} fill="none" stroke={stroke} strokeWidth="1.5" />
    </svg>
  );
}
