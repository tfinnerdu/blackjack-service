// Two SVG dice that tumble for ~1s and settle on the rolled values.
// `rolling=true` runs the tumble animation; transition to false snaps
// each die to its final pip pattern.

import { useEffect, useState } from "react";

const PIP_LAYOUTS: Record<number, [number, number][]> = {
  // (col, row) on a 3x3 grid; cells 0..2 in each direction.
  1: [[1, 1]],
  2: [[0, 0], [2, 2]],
  3: [[0, 0], [1, 1], [2, 2]],
  4: [[0, 0], [2, 0], [0, 2], [2, 2]],
  5: [[0, 0], [2, 0], [1, 1], [0, 2], [2, 2]],
  6: [[0, 0], [2, 0], [0, 1], [2, 1], [0, 2], [2, 2]],
};

function Die({ value, rolling }: { value: number; rolling: boolean }) {
  // While rolling we cycle the displayed value rapidly so the dots
  // visibly change — the tumble animation alone looked static.
  const [displayValue, setDisplayValue] = useState(value);

  useEffect(() => {
    if (!rolling) {
      setDisplayValue(value);
      return;
    }
    const id = window.setInterval(() => {
      setDisplayValue((v) => ((v % 6) + 1));
    }, 100);
    return () => window.clearInterval(id);
  }, [rolling, value]);

  const pips = PIP_LAYOUTS[displayValue] ?? [];

  return (
    <svg
      viewBox="0 0 60 60"
      className={`w-16 h-16 inline-block ${rolling ? "animate-die-tumble" : ""}`}
      style={{
        filter: rolling ? "drop-shadow(0 4px 8px rgba(0,0,0,0.4))" : undefined,
      }}
    >
      <rect
        x="2" y="2" width="56" height="56" rx="8" ry="8"
        fill="#f5f5f1" stroke="#0c2a1d" strokeWidth="2"
      />
      {pips.map(([col, row], i) => (
        <circle
          key={i}
          cx={12 + col * 18}
          cy={12 + row * 18}
          r={4.5}
          fill="#0c2a1d"
        />
      ))}
    </svg>
  );
}

export function Dice({
  d1,
  d2,
  rolling,
}: {
  d1: number;
  d2: number;
  rolling: boolean;
}) {
  return (
    <div className="flex items-center justify-center gap-3">
      <Die value={d1} rolling={rolling} />
      <Die value={d2} rolling={rolling} />
    </div>
  );
}
