import { ArrowDownRight, ArrowUpRight, Camera, FileText, Gauge, MessageSquare, Ruler, Send } from "lucide-react";
import type { ReactNode } from "react";
import { TIER_COLOR, TIER_NAME, cx, fmtScore, scoreColor } from "../lib/format";

export function TierBadge({ tier, size = "md", title }: { tier: string | null | undefined; size?: "sm" | "md" | "lg" | "xl"; title?: boolean }) {
  if (!tier) return <span className="text-faint">—</span>;
  const dims = { sm: "h-5 w-5 text-[13px]", md: "h-7 w-7 text-[17px]", lg: "h-11 w-11 text-[28px]", xl: "h-16 w-16 text-[42px]" }[size];
  return (
    <span className="inline-flex items-center gap-2" title={TIER_NAME[tier]}>
      <span
        className={cx("inline-grid place-items-center rounded-full font-display leading-none", dims)}
        style={{ color: TIER_COLOR[tier], boxShadow: `inset 0 0 0 1px ${TIER_COLOR[tier]}`, background: `color-mix(in srgb, ${TIER_COLOR[tier]} 10%, transparent)` }}
      >
        <span className="translate-y-[1px]">{tier}</span>
      </span>
      {title && <span className="text-sm text-muted">{TIER_NAME[tier]}</span>}
    </span>
  );
}

export function ScoreBar({ score, lower, prev, compact }: { score: number | null | undefined; lower?: number | null; prev?: number | null; compact?: boolean }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, ((v - 3) / 7) * 100))}%`;
  return (
    <div className={cx("relative w-full rounded-full bg-white/[0.06]", compact ? "h-1" : "h-1.5")}>
      {score != null && (
        <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ease-out-expo" style={{ width: pct(score), background: scoreColor(score) }} />
      )}
      {lower != null && <div className="absolute -top-[3px] h-[calc(100%+6px)] w-px bg-paper/60" style={{ left: pct(lower) }} title={`Lower bound ${fmtScore(lower)}`} />}
      {prev != null && <div className="absolute -bottom-[5px] h-1 w-1 -translate-x-1/2 rounded-full bg-muted" style={{ left: pct(prev) }} title={`90 days ago ${fmtScore(prev)}`} />}
    </div>
  );
}

export function Delta({ now, prev, digits = 1 }: { now: number | null | undefined; prev: number | null | undefined; digits?: number }) {
  if (now == null || prev == null) return null;
  const d = now - prev;
  if (Math.abs(d) < 0.05) return <span className="tnum text-xs text-faint">±0</span>;
  const up = d > 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cx("tnum inline-flex items-center text-xs", up ? "text-good" : "text-bad")}>
      <Icon size={13} strokeWidth={2} />
      {Math.abs(d).toFixed(digits)}
    </span>
  );
}

export function TierMove({ from, to }: { from: string | null; to: string | null }) {
  if (!from || !to || from === to) return null;
  const up = "SABC".indexOf(to) < "SABC".indexOf(from);
  return (
    <span className={cx("inline-flex items-center gap-1 font-mono text-[11px]", up ? "text-good" : "text-bad")}>
      {from}
      <span className="opacity-60">→</span>
      {to}
    </span>
  );
}

export function Chip({ active, onClick, children, className }: { active?: boolean; onClick?: () => void; children: ReactNode; className?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "rounded-full border px-3 py-1 text-[12.5px] transition-colors duration-200",
        active ? "border-gold/60 bg-gold-soft text-paper" : "border-line text-muted hover:border-line-strong hover:text-paper",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function SectionHead({ eyebrow, title, action, className }: { eyebrow?: string; title: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cx("mb-6 flex items-end justify-between gap-6 border-b border-line pb-3", className)}>
      <div>
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h2 className="font-display text-[28px] leading-none tracking-tight md:text-[34px]">{title}</h2>
      </div>
      {action}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <div className="eyebrow mb-2">{label}</div>
      <div className="tnum font-display text-4xl leading-none">{value}</div>
      {sub && <div className="mt-2 text-xs text-muted">{sub}</div>}
    </div>
  );
}

const SOURCE_ICON: Record<string, typeof MessageSquare> = { forum: MessageSquare, reddit: MessageSquare, blog: FileText, telegram: Send };
export function SourceTag({ kind, name }: { kind: string | null; name: string | null }) {
  const Icon = SOURCE_ICON[kind ?? ""] ?? MessageSquare;
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] text-muted">
      <Icon size={12} strokeWidth={1.8} />
      {name}
    </span>
  );
}

const EVIDENCE_ICON: Record<string, typeof Camera> = { photo: Camera, measurement: Ruler, timegrapher: Gauge };
export function EvidenceTag({ evidence }: { evidence: string }) {
  const Icon = EVIDENCE_ICON[evidence];
  if (!Icon) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[10.5px] text-muted" title={`Backed by ${evidence}`}>
      <Icon size={11} strokeWidth={1.8} />
      {evidence}
    </span>
  );
}

export function Severity({ level }: { level: number }) {
  return (
    <span className="inline-flex gap-0.5" title={`Severity ${level}/3`}>
      {[1, 2, 3].map((i) => (
        <span key={i} className={cx("h-2.5 w-1 rounded-sm", i <= level ? (level === 3 ? "bg-bad" : level === 2 ? "bg-warn" : "bg-muted") : "bg-white/10")} />
      ))}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const tone: Record<string, string> = {
    current: "text-good border-good/30",
    superseded: "text-muted border-line",
    discontinued: "text-bad border-bad/30",
    open: "text-bad border-bad/30",
    fixed: "text-good border-good/30",
    disputed: "text-warn border-warn/30",
    active: "text-good border-good/30",
    closed: "text-bad border-bad/30",
  };
  return <span className={cx("rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider", tone[status] ?? "border-line text-muted")}>{status}</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-xl bg-white/[0.04]", className)} />;
}

export function PageLoading() {
  return (
    <div className="mx-auto max-w-[1360px] px-4 py-16 md:px-10">
      <Skeleton className="mb-6 h-12 w-2/5" />
      <Skeleton className="mb-10 h-5 w-1/4" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="aspect-[4/5]" />
        ))}
      </div>
    </div>
  );
}

export function ErrorNote({ error }: { error: Error }) {
  return <div className="mx-auto max-w-xl px-6 py-24 text-center text-muted">Couldn’t load this page — {error.message}</div>;
}
