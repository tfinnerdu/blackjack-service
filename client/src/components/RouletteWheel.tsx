// SVG roulette wheel that spins to a target pocket. Construction:
//   - The wheel is a stack of 37 (European) or 38 (American) wedge
//     segments around a circle, each tagged with its number + color.
//   - The ball is a small circle on the rim that rotates the OPPOSITE
//     direction during the spin, then the whole wheel snaps so the
//     winning pocket sits at 12 o'clock (under the ball indicator).
// Numbers are drawn radially so they read the right-way-up in their
// pocket. The pocket order is the canonical casino sequence — not
// numerical — which makes the spin feel real instead of arbitrary.

import { useEffect, useRef, useState } from "react";

const AMERICAN_ORDER: string[] = [
  "0", "28", "9", "26", "30", "11", "7", "20", "32", "17",
  "5", "22", "34", "15", "3", "24", "36", "13", "1", "00",
  "27", "10", "25", "29", "12", "8", "19", "31", "18", "6",
  "21", "33", "16", "4", "23", "35", "14", "2",
];

const EUROPEAN_ORDER: string[] = [
  "0", "32", "15", "19", "4", "21", "2", "25", "17", "34",
  "6", "27", "13", "36", "11", "30", "8", "23", "10", "5",
  "24", "16", "33", "1", "20", "14", "31", "9", "22", "18",
  "29", "7", "28", "12", "35", "3", "26",
];

const RED_NUMBERS = new Set([
  1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36,
]);

function pocketColor(label: string): string {
  if (label === "0" || label === "00") return "#0f7a45";    // green
  if (RED_NUMBERS.has(parseInt(label, 10))) return "#b91c1c"; // red
  return "#1f2937";                                          // near-black
}

export function RouletteWheel({
  kind,
  pocket,
  spinning,
}: {
  kind: "american" | "european";
  /** The pocket label that will be (or just was) landed on. Pass null
   *  to render the wheel at rest with no winner highlight. */
  pocket: string | null;
  /** True while the spin is in flight; flips to false after ~3.5s. */
  spinning: boolean;
}) {
  const order = kind === "american" ? AMERICAN_ORDER : EUROPEAN_ORDER;
  const segCount = order.length;
  const segAngle = 360 / segCount;

  // Track the wheel + ball end-rotation across spins so each new spin
  // adds full turns to the previous angle (spin keeps moving forward
  // visually instead of resetting every time).
  const wheelAngleRef = useRef<number>(0);
  const ballAngleRef = useRef<number>(0);
  const [wheelAngle, setWheelAngle] = useState(0);
  const [ballAngle, setBallAngle] = useState(0);

  useEffect(() => {
    if (pocket == null || !spinning) return;
    const targetIdx = order.indexOf(pocket);
    if (targetIdx < 0) return;

    // We want segment `targetIdx` to land at 12 o'clock (top, angle 0
    // when the wheel is rotated by -targetIdx*segAngle). Add 5 full
    // turns of motion plus a small random offset so each spin feels
    // distinct.
    const targetWheel =
      Math.ceil(wheelAngleRef.current / 360) * 360
      + 360 * 5
      + (-targetIdx * segAngle);
    // Ball rotates the opposite direction; same number of turns.
    const targetBall =
      Math.floor(ballAngleRef.current / 360) * 360
      - 360 * 4;

    // Set the new transforms — CSS transition on the wrapper does
    // the actual animation.
    wheelAngleRef.current = targetWheel;
    ballAngleRef.current = targetBall;
    setWheelAngle(targetWheel);
    setBallAngle(targetBall);
  }, [pocket, spinning, order, segAngle]);

  // Geometry constants for the SVG.
  const cx = 100;
  const cy = 100;
  const rOuter = 96;
  const rInner = 28;
  const rText = (rOuter + rInner) / 2 + 4;
  const rBall = 88;

  // Pre-compute each pocket's wedge path.
  const wedges = order.map((label, i) => {
    const startA = (i * segAngle - segAngle / 2 - 90) * Math.PI / 180;
    const endA = (i * segAngle + segAngle / 2 - 90) * Math.PI / 180;
    const x1 = cx + rOuter * Math.cos(startA);
    const y1 = cy + rOuter * Math.sin(startA);
    const x2 = cx + rOuter * Math.cos(endA);
    const y2 = cy + rOuter * Math.sin(endA);
    const x3 = cx + rInner * Math.cos(endA);
    const y3 = cy + rInner * Math.sin(endA);
    const x4 = cx + rInner * Math.cos(startA);
    const y4 = cy + rInner * Math.sin(startA);
    const path = [
      `M ${x1} ${y1}`,
      `A ${rOuter} ${rOuter} 0 0 1 ${x2} ${y2}`,
      `L ${x3} ${y3}`,
      `A ${rInner} ${rInner} 0 0 0 ${x4} ${y4}`,
      "Z",
    ].join(" ");
    const labelAngle = i * segAngle;
    const labelRad = (labelAngle - 90) * Math.PI / 180;
    const labelX = cx + rText * Math.cos(labelRad);
    const labelY = cy + rText * Math.sin(labelRad);
    return {
      label,
      path,
      color: pocketColor(label),
      labelAngle,
      labelX,
      labelY,
      isWinner: pocket === label,
    };
  });

  // Highlight pulse on the winner once the wheel stops.
  const highlight = pocket && !spinning;

  return (
    <div className="relative w-full max-w-[280px] aspect-square mx-auto">
      <svg
        viewBox="0 0 200 200"
        className="absolute inset-0 w-full h-full"
      >
        {/* Outer rim */}
        <circle cx={cx} cy={cy} r={rOuter + 2} fill="#3a2412" />
        {/* Pointer at 12 o'clock — stays fixed; the wheel spins
            underneath it. */}
        <polygon
          points={`${cx - 5},2 ${cx + 5},2 ${cx},14`}
          fill="#fef3c7"
          stroke="#92400e"
          strokeWidth="1"
        />

        {/* The wheel itself rotates as a whole. */}
        <g
          className="animate-wheel-spin"
          style={{ transform: `rotate(${wheelAngle}deg)`, transformOrigin: `${cx}px ${cy}px` }}
        >
          {wedges.map((w, i) => (
            <g key={i}>
              <path d={w.path} fill={w.color} stroke="#0c2a1d" strokeWidth="0.6" />
              <text
                x={w.labelX}
                y={w.labelY}
                fill="#f5f5f1"
                fontSize="6"
                fontWeight="700"
                textAnchor="middle"
                alignmentBaseline="middle"
                transform={`rotate(${w.labelAngle} ${w.labelX} ${w.labelY})`}
              >
                {w.label}
              </text>
            </g>
          ))}
          {/* Inner hub */}
          <circle cx={cx} cy={cy} r={rInner - 2} fill="#3a2412" />
          <circle cx={cx} cy={cy} r={rInner - 8} fill="#1f1108" />
        </g>

        {/* Ball — outside the wheel <g> so it rotates on its own
            track. We translate to the wheel center, rotate, then move
            outward to the ball radius. */}
        <g
          className="animate-ball-spin"
          style={{ transform: `rotate(${ballAngle}deg)`, transformOrigin: `${cx}px ${cy}px` }}
        >
          <circle cx={cx} cy={cy - rBall} r="3.5" fill="#f5f5f1" stroke="#0c2a1d" strokeWidth="0.5" />
        </g>
      </svg>

      {/* Winner badge under the wheel once it stops. */}
      {highlight && (
        <div className="absolute inset-x-0 -bottom-2 flex justify-center pointer-events-none">
          <div
            className="rounded-full px-3 py-1 text-sm font-mono shadow-md"
            style={{
              backgroundColor: pocketColor(pocket),
              color: "white",
              border: "2px solid #fef3c7",
            }}
          >
            {pocket}
          </div>
        </div>
      )}
    </div>
  );
}
