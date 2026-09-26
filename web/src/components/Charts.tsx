import { useLayoutEffect, useRef, useState } from "react";

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export type Series = { name: string; color: string; points: { x: string; y: number }[] };

/** Time series with shared x (ISO dates or 'YYYY-Qn' labels), hover crosshair. */
export function TimeChart({
  series,
  bars,
  height = 220,
  yFormat = (v: number) => v.toFixed(0),
  yDomain,
  categorical,
}: {
  series: Series[];
  bars?: { x: string; y: number }[];
  height?: number;
  yFormat?: (v: number) => string;
  yDomain?: [number, number];
  categorical?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<string | null>(null);
  const pad = { l: 44, r: 12, t: 12, b: 26 };
  const xs = [...new Set([...series.flatMap((s) => s.points.map((p) => p.x)), ...(bars ?? []).map((b) => b.x)])].sort();
  const ys = series.flatMap((s) => s.points.map((p) => p.y));
  if (!xs.length || !ys.length) return <div ref={ref} style={{ height }} />;
  let [y0, y1] = yDomain ?? [Math.min(...ys), Math.max(...ys)];
  if (!yDomain) {
    const span = y1 - y0 || 1;
    y0 -= span * 0.12;
    y1 += span * 0.12;
  }
  const iw = Math.max(width - pad.l - pad.r, 1);
  const ih = height - pad.t - pad.b;
  const xAt = categorical
    ? (x: string) => pad.l + (xs.length === 1 ? iw / 2 : (xs.indexOf(x) / (xs.length - 1)) * iw)
    : (() => {
        const t0 = Date.parse(xs[0]);
        const t1 = Date.parse(xs[xs.length - 1]);
        return (x: string) => pad.l + ((Date.parse(x) - t0) / (t1 - t0 || 1)) * iw;
      })();
  const yAt = (y: number) => pad.t + ih - ((y - y0) / (y1 - y0)) * ih;
  const ticks = Array.from({ length: 4 }, (_, i) => y0 + ((y1 - y0) * (i + 0.5)) / 4);
  const barMax = Math.max(1, ...(bars ?? []).map((b) => b.y));
  const labelEvery = Math.ceil(xs.length / Math.max(2, Math.floor(iw / 80)));

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - box.left;
    let best = xs[0];
    for (const x of xs) if (Math.abs(xAt(x) - px) < Math.abs(xAt(best) - px)) best = x;
    setHover(best);
  };

  return (
    <div ref={ref} className="relative w-full select-none">
      {width > 0 && (
        <svg width={width} height={height} onPointerMove={onMove} onPointerLeave={() => setHover(null)} className="block">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={yAt(t)} y2={yAt(t)} stroke="var(--color-line)" />
              <text x={pad.l - 10} y={yAt(t)} textAnchor="end" dominantBaseline="central" className="fill-faint font-mono text-[10px]">
                {yFormat(t)}
              </text>
            </g>
          ))}
          {bars?.map((b) => {
            const h = (b.y / barMax) * ih * 0.35;
            const bw = Math.max(3, Math.min(18, iw / xs.length - 6));
            return <rect key={b.x} x={xAt(b.x) - bw / 2} y={pad.t + ih - h} width={bw} height={h} rx="1.5" fill="var(--color-paper)" opacity={hover === b.x ? 0.22 : 0.08} />;
          })}
          {xs.map((x, i) =>
            i % labelEvery === 0 ? (
              <text key={x} x={xAt(x)} y={height - 8} textAnchor="middle" className="fill-faint font-mono text-[10px]">
                {categorical ? x : new Date(x).toLocaleDateString("en-GB", { month: "short", year: "2-digit" })}
              </text>
            ) : null,
          )}
          {series.map((s) => (
            <path
              key={s.name}
              d={s.points.map((p, i) => `${i ? "L" : "M"}${xAt(p.x).toFixed(1)} ${yAt(p.y).toFixed(1)}`).join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth="1.6"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {hover && (
            <g>
              <line x1={xAt(hover)} x2={xAt(hover)} y1={pad.t} y2={pad.t + ih} stroke="var(--color-line-strong)" />
              {series.map((s) => {
                const p = s.points.find((q) => q.x === hover);
                return p ? <circle key={s.name} cx={xAt(p.x)} cy={yAt(p.y)} r="3.5" fill="var(--color-ink)" stroke={s.color} strokeWidth="1.6" /> : null;
              })}
            </g>
          )}
        </svg>
      )}
      {hover && (
        <div
          className="pointer-events-none absolute top-2 z-10 min-w-36 rounded-lg border border-line bg-raise/95 px-3 py-2 text-xs shadow-2xl backdrop-blur"
          style={{ left: Math.min(Math.max(xAt(hover) + 12, 0), width - 170) }}
        >
          <div className="mb-1 font-mono text-[10px] text-faint">{categorical ? hover : new Date(hover).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</div>
          {series.map((s) => {
            const p = s.points.find((q) => q.x === hover);
            return p ? (
              <div key={s.name} className="flex items-center justify-between gap-4">
                <span className="flex items-center gap-1.5 text-muted">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
                  {s.name}
                </span>
                <span className="tnum">{yFormat(p.y)}</span>
              </div>
            ) : null;
          })}
          {bars?.find((b) => b.x === hover) && <div className="mt-1 text-faint">{bars.find((b) => b.x === hover)!.y} claims</div>}
        </div>
      )}
    </div>
  );
}

export function TierStack({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (!total) return <div className="h-1.5 rounded-full bg-white/5" />;
  return (
    <div className="flex h-1.5 overflow-hidden rounded-full bg-white/5">
      {(["S", "A", "B", "C"] as const).map((t) =>
        counts[t] ? <div key={t} style={{ width: `${(counts[t] / total) * 100}%`, background: `var(--color-tier-${t.toLowerCase()})` }} title={`${counts[t]} × ${t}`} /> : null,
      )}
    </div>
  );
}
