import { motion } from "motion/react";
import { useState } from "react";
import { Link } from "react-router";
import { useApi, type ReferenceListItem } from "../api";
import { Chip, ErrorNote, PageLoading } from "../components/ui";
import WatchImage from "../components/WatchImage";
import { TIER_COLOR, TIER_NAME, TIER_ORDER, fmtScore } from "../lib/format";

export default function Tiers() {
  const { data, error } = useApi<ReferenceListItem[]>("references");
  const [currentOnly, setCurrentOnly] = useState(true);
  const [family, setFamily] = useState<string | null>(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <PageLoading />;

  const families = [...new Set(data.map((r) => r.family))];
  const refs = data.filter((r) => !family || r.family === family);

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="pb-10 pt-14">
        <div className="eyebrow mb-4">Tier list</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Who makes it best</h1>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
          Each reference, every factory’s build, placed by the lower bound of its weighted score. Superseded versions are hidden unless you ask for them.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-2">
          <Chip active={!family} onClick={() => setFamily(null)}>
            All families
          </Chip>
          {families.map((f) => (
            <Chip key={f} active={family === f} onClick={() => setFamily(f)}>
              {f}
            </Chip>
          ))}
          <span className="mx-2 h-5 w-px bg-line" />
          <Chip active={!currentOnly} onClick={() => setCurrentOnly((v) => !v)}>
            Show superseded
          </Chip>
        </div>
      </header>

      <div className="sticky top-16 z-30 hidden grid-cols-[300px_repeat(4,1fr)] gap-3 border-y border-line bg-ink/85 py-3 backdrop-blur-xl lg:grid">
        <div className="eyebrow">Reference</div>
        {TIER_ORDER.map((t) => (
          <div key={t} className="flex items-baseline gap-2">
            <span className="font-display text-xl leading-none" style={{ color: TIER_COLOR[t] }}>
              {t}
            </span>
            <span className="eyebrow">{TIER_NAME[t]}</span>
          </div>
        ))}
      </div>

      <div>
        {refs.map((r, i) => {
          const builds = r.builds.filter((b) => !currentOnly || b.status === "current");
          return (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.5, delay: (i % 4) * 0.04 }}
              className="grid gap-3 border-b border-line py-5 lg:grid-cols-[300px_repeat(4,1fr)]"
            >
              <Link to={`/ref/${r.id}`} className="group flex items-center gap-4">
                <div className="h-16 w-16 shrink-0 overflow-hidden rounded-full bg-panel">
                  <WatchImage photo={r.ref_photo} refId={r.id} compact className="object-cover" />
                </div>
                <div className="min-w-0">
                  <div className="truncate font-display text-[22px] leading-tight transition-colors group-hover:text-gold">{r.name}</div>
                  <div className="font-mono text-[11.5px] text-muted">
                    {r.id} · {r.claims.toLocaleString()} claims
                  </div>
                </div>
              </Link>
              {TIER_ORDER.map((t) => (
                <div key={t} className="flex flex-wrap content-start items-start gap-1.5 lg:min-h-10">
                  <span className="mr-1 font-display text-lg leading-7 lg:hidden" style={{ color: TIER_COLOR[t] }}>
                    {t}
                  </span>
                  {builds
                    .filter((b) => b.tier === t)
                    .map((b) => (
                      <Link
                        key={b.id}
                        to={`/build/${b.id}`}
                        className="group inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[13px] transition-all hover:-translate-y-px"
                        style={{
                          borderColor: `color-mix(in srgb, ${TIER_COLOR[t]} 30%, transparent)`,
                          background: `color-mix(in srgb, ${TIER_COLOR[t]} 6%, transparent)`,
                          opacity: b.status === "current" ? 1 : 0.55,
                        }}
                      >
                        <span>
                          {b.factory} <span className="text-muted">{b.version}</span>
                        </span>
                        <span className="tnum font-mono text-[11px] text-muted group-hover:text-paper">{fmtScore(b.score)}</span>
                      </Link>
                    ))}
                </div>
              ))}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
