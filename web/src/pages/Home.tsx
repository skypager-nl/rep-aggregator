import { ArrowRight, Factory as FactoryIcon, PackageOpen, Sparkles, Tag, TriangleAlert } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router";
import { useApi, type Feed, type Meta } from "../api";
import BuildCard from "../components/BuildCard";
import { ErrorNote, PageLoading, SectionHead, Severity, SourceTag, Stat, StatusPill, TierBadge, TierMove } from "../components/ui";
import WatchImage from "../components/WatchImage";
import { ago, fmtDate, fmtInt, fmtScore } from "../lib/format";

const EVENT_ICON: Record<string, typeof Sparkles> = { release: Sparkles, closure: FactoryIcon, rebrand: FactoryIcon, restock: PackageOpen, price: Tag, defect: TriangleAlert };

export default function Home() {
  const { data: meta } = useApi<Meta>("meta");
  const { data: feed, error } = useApi<Feed>("feed");
  if (error) return <ErrorNote error={error} />;
  if (!feed || !meta) return <PageLoading />;
  const hero = feed.top.find((b) => b.ref_photo) ?? feed.top[0];

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      {/* hero */}
      <section className="grid items-center gap-10 pb-16 pt-12 md:grid-cols-[1.1fr_1fr] md:pt-20">
        <div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7 }} className="eyebrow mb-6">
            Scores as of {fmtDate(meta.as_of, "long")}
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.05, ease: [0.16, 1, 0.3, 1] }}
            className="font-display text-[54px] leading-[0.95] tracking-[-0.02em] md:text-[88px]"
          >
            Every factory.
            <br />
            Every flaw. <em className="text-gold">Ranked.</em>
          </motion.h1>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3, duration: 0.8 }} className="mt-6 max-w-lg text-[15px] leading-relaxed text-muted">
            Forum QC threads, long-term reviews and dealer channels, distilled into per-aspect scores for every build. Tiers are set on the conservative bound, so a
            handful of hype posts can’t buy a place at the top.
          </motion.p>
          <div className="mt-10 grid max-w-lg grid-cols-3 gap-6 border-t border-line pt-6">
            <Stat label="Versions" value={fmtInt(meta.counts.build)} sub={`${meta.counts.reference} references`} />
            <Stat label="Claims" value={fmtInt(meta.counts.claim)} sub={`${fmtInt(meta.counts.post)} posts`} />
            <Stat label="Defects" value={fmtInt(meta.counts.defect)} sub="tracked by version" />
          </div>
          <div className="mt-10 flex gap-3">
            <Link to="/tiers" className="group inline-flex items-center gap-2 rounded-full bg-paper px-5 py-2.5 text-sm font-medium text-ink transition-transform hover:scale-[1.02]">
              Tier list <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link to="/explore" className="inline-flex items-center gap-2 rounded-full border border-line-strong px-5 py-2.5 text-sm text-paper transition-colors hover:bg-white/5">
              Explore versions
            </Link>
          </div>
        </div>

        {hero && (
          <Link to={`/build/${hero.id}`} className="group relative block">
            <motion.div
              initial={{ opacity: 0, scale: 0.94, rotate: -4 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
              className="relative mx-auto aspect-square max-w-[560px]"
            >
              <div className="absolute inset-[8%] rounded-full bg-gold/10 blur-3xl" />
              <WatchImage photo={hero.ref_photo} refId={hero.reference_id} className="relative" />
            </motion.div>
            <div className="absolute bottom-4 left-0 right-0 mx-auto flex w-fit items-center gap-4 rounded-full border border-line bg-ink/80 py-2 pl-2 pr-5 backdrop-blur-md transition-colors group-hover:border-gold/40">
              <TierBadge tier={hero.tier} />
              <div className="text-sm">
                <div className="leading-tight">
                  {hero.factory} {(hero.label ?? '')} <span className="font-mono text-xs text-muted">{hero.reference_id}</span>
                </div>
                <div className="text-xs text-muted">Highest-rated current version · {fmtScore(hero.score)}</div>
              </div>
            </div>
          </Link>
        )}
      </section>

      {/* top builds */}
      <section className="pt-8">
        <SectionHead
          eyebrow="Current versions"
          title="Reference grade"
          action={
            <Link to="/explore?sort=lower" className="text-sm text-muted transition-colors hover:text-paper">
              All versions →
            </Link>
          }
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {feed.top.map((b, i) => (
            <BuildCard key={b.id} b={b} index={i} />
          ))}
        </div>
      </section>

      <section className="mt-20 grid gap-12 lg:grid-cols-[1.35fr_1fr]">
        {/* wire */}
        <div>
          <SectionHead eyebrow="Dealers · forums" title="The wire" />
          <ol className="relative">
            {feed.events.slice(0, 12).map((e) => {
              const Icon = EVENT_ICON[e.kind] ?? Sparkles;
              const to = e.build_id ? `/build/${e.build_id}` : e.factory_id ? `/factory/${e.factory_id}` : "#";
              return (
                <li key={e.id} className="group grid grid-cols-[76px_24px_1fr] items-start gap-3 border-b border-line py-3.5 last:border-0">
                  <span className="pt-0.5 font-mono text-[11px] text-faint">{ago(e.occurred_at, meta.as_of)}</span>
                  <Icon size={15} className="mt-0.5 text-gold" strokeWidth={1.7} />
                  <Link to={to} className="min-w-0">
                    <div className="text-[14.5px] leading-snug transition-colors group-hover:text-gold">{e.title}</div>
                    <div className="mt-1 flex items-center gap-3">
                      <SourceTag kind={e.source_kind} name={e.source} />
                      <span className="font-mono text-[10px] uppercase tracking-wider text-faint">{e.kind}</span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ol>
        </div>

        <div className="space-y-14">
          {/* defect watch */}
          <div>
            <SectionHead eyebrow="Current versions · last 120 days" title="Defect watch" />
            <ul>
              {feed.defects.slice(0, 7).map((d) => (
                <li key={d.id} className="border-b border-line last:border-0">
                  <Link to={`/build/${d.build_id}`} className="group flex items-start gap-3 py-3">
                    <span className="pt-1.5">
                      <Severity level={d.severity} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[14.5px] leading-snug transition-colors group-hover:text-gold">{d.title}</span>
                      <span className="mt-1 block text-xs text-muted">
                        {d.factory} {(d.label ?? '')} · <span className="font-mono">{d.reference_id}</span> · {d.reports} reports
                      </span>
                    </span>
                    <StatusPill status={d.status} />
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* movers */}
          <div>
            <SectionHead eyebrow="Versus 90 days ago" title="Tier movers" />
            <ul>
              {feed.movers.map((b) => (
                <li key={b.id} className="border-b border-line last:border-0">
                  <Link to={`/build/${b.id}`} className="group flex items-center gap-3 py-3">
                    <TierBadge tier={b.tier} size="sm" />
                    <span className="flex-1 truncate text-[14.5px] transition-colors group-hover:text-gold">
                      {b.factory} {(b.label ?? '')} <span className="font-mono text-xs text-muted">{b.reference_id}</span>
                    </span>
                    <TierMove from={b.prev_tier} to={b.tier} />
                  </Link>
                </li>
              ))}
              {!feed.movers.length && <li className="py-3 text-sm text-muted">No tier changes.</li>}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
