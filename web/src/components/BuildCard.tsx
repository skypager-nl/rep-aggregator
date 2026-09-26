import { AlertTriangle } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router";
import type { BuildSummary } from "../api";
import { fmtPrice, fmtScore, guideLabel } from "../lib/format";
import { Delta, ScoreBar, StatusPill, TierBadge } from "./ui";
import WatchImage from "./WatchImage";

export default function BuildCard({ b, index = 0, showRef = true }: { b: BuildSummary; index?: number; showRef?: boolean }) {
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: Math.min(index, 12) * 0.035, ease: [0.16, 1, 0.3, 1] }}>
      <Link to={`/build/${b.id}`} className="group block overflow-hidden rounded-2xl border border-line bg-panel transition-colors duration-300 hover:border-line-strong">
        <div className="relative aspect-[5/4] overflow-hidden bg-[radial-gradient(circle_at_50%_40%,#1d1d21,#0c0c0e_70%)]">
          <WatchImage
            photo={b.ref_photo}
            refId={b.reference_id}
            className="p-4 transition-transform duration-700 ease-out-expo group-hover:scale-[1.04]"
          />
          <div className="absolute left-3 top-3">
            <TierBadge tier={b.tier} />
          </div>
          {b.status !== "current" && (
            <div className="absolute right-3 top-3">
              <StatusPill status={b.status} />
            </div>
          )}
        </div>
        <div className="p-4">
          <div className="flex items-baseline justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate font-display text-[22px] leading-tight">
                {b.factory} <span className="text-muted">{(b.label ?? '')}</span>
                {!(b.label ?? '') && b.movement && <span className="ml-1.5 font-mono text-[11px] text-faint">{b.movement}</span>}
              </div>
              {showRef && (
                <div className="mt-0.5 truncate text-[12.5px] text-muted">
                  {b.brand} · <span className="font-mono text-[11.5px] text-paper/80">{b.reference_id}</span> · {b.reference_name}
                </div>
              )}
            </div>
            <div className="text-right">
              <div className="tnum font-display text-[26px] leading-none">{fmtScore(b.score)}</div>
            </div>
          </div>
          <div className="mt-3">
            <ScoreBar score={b.score} lower={b.lower} compact />
          </div>
          <div className="mt-3 flex items-center justify-between text-[12px] text-muted">
            <span className="tnum">{fmtPrice(b.price)}</span>
            <span className="flex items-center gap-3">
              {b.open_defects > 0 && (
                <span className="inline-flex items-center gap-1 text-warn/90">
                  <AlertTriangle size={12} /> {b.open_defects}
                </span>
              )}
              <span className="tnum">{b.claims ? `${b.claims} findings` : guideLabel(b.guide_rank, b.guide_quality) ? `Guide: ${guideLabel(b.guide_rank, b.guide_quality)}` : "no findings"}</span>
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

export function BuildRowMini({ b }: { b: Pick<BuildSummary, "id" | "factory" | "version" | "label" | "tier" | "score" | "prev_tier" | "reference_id" | "lower"> & { prevScore?: number | null } }) {
  return (
    <Link to={`/build/${b.id}`} className="flex items-center gap-3 py-2.5 transition-colors hover:text-gold">
      <TierBadge tier={b.tier} size="sm" />
      <span className="font-mono text-[11.5px] text-muted">{b.reference_id}</span>
      <span className="flex-1 truncate">
        {b.factory} {(b.label ?? '')}
      </span>
      <span className="tnum text-sm">{fmtScore(b.score)}</span>
      {b.prevScore !== undefined && <Delta now={b.score} prev={b.prevScore} />}
    </Link>
  );
}
