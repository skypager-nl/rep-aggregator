import { ChevronDown } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Link } from "react-router";
import { useApi, type FactoryListItem, type Meta } from "../api";
import { TierStack } from "../components/Charts";
import { ErrorNote, PageLoading, StatusPill } from "../components/ui";
import { fmtScore, scoreColor } from "../lib/format";

export default function Factories() {
  const { data, error } = useApi<FactoryListItem[]>("factories");
  const { data: meta } = useApi<Meta>("meta");
  const [showNiche, setShowNiche] = useState(false);
  const [q, setQ] = useState("");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <PageLoading />;
  const main = data.filter((f) => !f.niche);
  const niche = data.filter((f) => f.niche && (!q || f.name.toLowerCase().includes(q.toLowerCase())));

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="pb-12 pt-14">
        <div className="eyebrow mb-4">Factories</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">The makers</h1>
        <Link
          to="/factories/review"
          className="mt-6 inline-flex items-center gap-2 rounded-full border border-line-strong px-4 py-1.5 text-sm transition-colors hover:bg-white/5"
        >
          Review factories & references
          {meta && meta.factories_to_review + meta.references_to_review > 0 && (
            <span className="rounded-full bg-warn/20 px-2 font-mono text-[11px] text-warn">{meta.factories_to_review + meta.references_to_review} new</span>
          )}
        </Link>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
          Ranked by the average score of their current builds. Aliases are resolved deterministically, so “CF”, “Clean” and “C Factory” all count once.
        </p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {main.map((f, i) => (
          <motion.div key={f.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04, duration: 0.5 }}>
            <Link to={`/factory/${f.id}`} className="group flex h-full flex-col rounded-2xl border border-line bg-panel p-6 transition-colors hover:border-line-strong">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-mono text-[11px] text-faint">#{i + 1}</div>
                  <div className="mt-1 font-display text-[40px] leading-none transition-colors group-hover:text-gold">{f.name}</div>
                </div>
                <div className="text-right">
                  <div className="tnum font-display text-[40px] leading-none" style={{ color: scoreColor(f.avg_score) }}>
                    {fmtScore(f.avg_score)}
                  </div>
                  <div className="eyebrow mt-1">avg current</div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <StatusPill status={f.status} />
                {f.founded && <span className="text-xs text-faint">since {f.founded}</span>}
                {f.aliases.length > 0 && <span className="truncate text-xs text-muted">aka {f.aliases.join(", ")}</span>}
              </div>
              <div className="mt-auto pt-8">
                <TierStack counts={f.tier_counts} />
                <div className="mt-3 flex justify-between text-xs text-muted">
                  <span>
                    {f.builds.filter((b) => b.status === "current").length} current · {f.builds.length} total versions
                  </span>
                  <span>{f.references.length} references</span>
                </div>
              </div>
            </Link>
          </motion.div>
        ))}
      </div>

      <section className="mt-16">
        <button onClick={() => setShowNiche((v) => !v)} className="flex w-full items-center justify-between border-b border-line pb-3 text-left">
          <span>
            <span className="eyebrow block">One model each, no findings yet</span>
            <span className="font-display text-[28px] leading-none">Niche factories ({data.filter((f) => f.niche).length})</span>
          </span>
          <ChevronDown size={18} className={showNiche ? "rotate-180 transition-transform" : "transition-transform"} />
        </button>
        {showNiche && (
          <div className="mt-4">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search niche factories…" className="mb-4 w-64 rounded-full border border-line bg-panel px-3 py-1.5 text-[13px] outline-none" />
            <ul className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
              {niche.map((f) => (
                <li key={f.id} className="border-b border-line py-2.5 text-[14px]">
                  <Link to={`/factory/${f.id}`} className="hover:text-gold">
                    {f.name}
                  </Link>
                  {f.builds[0] && (
                    <Link to={`/build/${f.builds[0].id}`} className="ml-2 font-mono text-[11.5px] text-muted hover:text-paper">
                      {f.builds[0].reference_id}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-faint">Named by the community guide for a single model. They move up to the main list once real findings arrive.</p>
          </div>
        )}
      </section>
    </div>
  );
}
