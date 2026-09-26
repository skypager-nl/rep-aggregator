import { Check, Columns3, ExternalLink, Maximize2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { useApi, type BuildDetail, type Meta } from "../api";
import { TimeChart } from "../components/Charts";
import {
  Delta,
  ErrorNote,
  PageLoading,
  ScoreBar,
  SectionHead,
  Severity,
  StatusPill,
  TierBadge,
  TierMove,
} from "../components/ui";
import WatchImage from "../components/WatchImage";
import { compare, useCompare } from "../lib/compare";
import { cx, fmtDate, fmtPrice, fmtScore, scoreColor } from "../lib/format";

const DEALER_COLORS = ["#c9a46a", "#7fb89a", "#8fa8d9", "#d9826f"];

export default function Build() {
  const { id } = useParams();
  const { data: meta } = useApi<Meta>("meta");
  const { data: b, error } = useApi<BuildDetail>(`builds/${id}`);
  const compared = useCompare();
  const [photoKey, setPhotoKey] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState(false);
  const [aspect, setAspect] = useState<string | null>(null);

  useEffect(() => {
    setPhotoKey(null);
    setAspect(null);
  }, [id]);

  const priceSeries = useMemo(() => {
    const byDealer = new Map<string, { x: string; y: number }[]>();
    for (const p of b?.prices ?? []) byDealer.set(p.dealer, [...(byDealer.get(p.dealer) ?? []), { x: p.observed_at, y: p.price }]);
    return [...byDealer].map(([name, points], i) => ({ name: `Dealer ${name.split("-").pop()?.toUpperCase()}`, color: DEALER_COLORS[i % 4], points }));
  }, [b]);

  if (error) return <ErrorNote error={error} />;
  if (!b || !meta) return <PageLoading />;

  // Genuine reference photos first (the benchmark), then rep QC photos from posts.
  const gallery = [
    ...b.ref_photos.map((p) => ({ key: `g${p.id}`, path: p.path, label: `Genuine · ${p.view}`, genuine: true, aspect: p.view, credit: p.credit })),
    ...b.photo_list.map((p) => ({ key: `q${p.id}`, path: p.path, label: `Rep QC · ${p.aspect}`, genuine: false, aspect: p.aspect, credit: null as string | null })),
  ];
  const shown = gallery.find((g) => g.key === photoKey) ?? gallery[0];
  const qcTotal = b.qc_gl + b.qc_rl + b.qc_mixed;
  const inCompare = compared.includes(b.id);
  const pickAspect = (a: string | null) => {
    setAspect(a);
    const match = a && gallery.find((g) => !g.genuine && g.aspect === a);
    if (match) setPhotoKey(match.key);
  };

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      {/* hero */}
      <section className="grid gap-10 pb-14 pt-8 lg:grid-cols-[1.15fr_1fr] lg:gap-16">
        <div>
          <button
            onClick={() => shown && setLightbox(true)}
            className="group relative block aspect-square w-full overflow-hidden rounded-3xl border border-line bg-[radial-gradient(circle_at_50%_40%,#1d1d21,#0a0a0b_75%)]"
          >
            <AnimatePresence mode="wait">
              <motion.div key={shown?.key ?? "none"} initial={{ opacity: 0, scale: 1.02 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }} className="h-full w-full">
                <WatchImage photo={shown?.path} refId={b.reference_id} label={shown?.label} className="p-2" />
              </motion.div>
            </AnimatePresence>
            {shown && (
              <span className={cx("absolute bottom-4 left-4 rounded-full border bg-ink/70 px-3 py-1 text-xs capitalize backdrop-blur", shown.genuine ? "border-gold/40 text-gold" : "border-line text-muted")}>
                {shown.label}
              </span>
            )}
            {shown?.credit && <span className="absolute bottom-4 right-4 text-[10.5px] text-faint">{shown.credit}</span>}
            {shown && <Maximize2 size={16} className="absolute right-4 top-4 text-muted opacity-0 transition-opacity group-hover:opacity-100" />}
          </button>
          {gallery.length > 1 && (
            <div className="mt-3 grid grid-cols-6 gap-2">
              {gallery.map((g) => (
                <button
                  key={g.key}
                  onClick={() => setPhotoKey(g.key)}
                  title={g.label}
                  className={cx(
                    "aspect-square overflow-hidden rounded-xl border bg-panel transition-all",
                    shown?.key === g.key ? "border-gold/70" : "border-line opacity-60 hover:opacity-100",
                  )}
                >
                  <WatchImage photo={g.path} refId={b.reference_id} compact className="object-cover" />
                </button>
              ))}
            </div>
          )}
          <p className="mt-2 text-[11px] text-faint">
            {b.photo_list.length ? "Genuine photos are the benchmark; QC photos come from forum and Reddit posts." : "QC photos from posts appear here once the collectors run."}
          </p>
        </div>

        <div className="lg:pt-6">
          <Link to={`/ref/${encodeURIComponent(b.reference_id)}`} className="eyebrow transition-colors hover:text-paper">
            {b.reference_name} · <span className="text-gold">{b.reference_id}</span>
          </Link>
          <h1 className="mt-4 font-display text-[56px] leading-[0.92] tracking-tight md:text-[84px]">
            {b.factory} <span className="italic text-muted">{b.version}</span>
          </h1>
          <div className="mt-3 flex items-center gap-3">
            <StatusPill status={b.status} />
            <span className="font-mono text-xs text-muted">{b.movement}</span>
            <span className="text-xs text-faint">released {fmtDate(b.released, "month")}</span>
          </div>

          <div className="mt-10 flex items-end gap-8 border-t border-line pt-8">
            <TierBadge tier={b.tier} size="xl" />
            <div>
              <div className="eyebrow mb-2">Overall</div>
              <div className="flex items-baseline gap-3">
                <span className="tnum font-display text-[64px] leading-none">{fmtScore(b.score, 2)}</span>
                <Delta now={b.score} prev={b.prev_score} digits={2} />
              </div>
              <div className="mt-2 text-xs text-muted">
                lower bound {fmtScore(b.lower, 2)} · rank #{b.rank} of {b.siblings.length + 1} · <TierMove from={b.prev_tier} to={b.tier} />
              </div>
            </div>
          </div>

          <dl className="mt-8 grid grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-4">
            <Fact label="Claims" value={String(b.claims)} />
            <Fact label="Dealer price" value={fmtPrice(b.price)} />
            <Fact label="QC green-light" value={qcTotal ? `${Math.round((100 * b.qc_gl) / qcTotal)}%` : "—"} sub={`${qcTotal} QC threads`} />
            <Fact label="Consensus" value={b.controversy == null ? "—" : b.controversy < 0.25 ? "Strong" : b.controversy < 0.35 ? "Mixed" : "Split"} sub={`spread ${fmtScore(b.controversy, 2)}`} />
          </dl>

          <div className="mt-8 flex flex-wrap gap-2">
            <button
              onClick={() => compare.toggle(b.id)}
              className={cx(
                "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm transition-colors",
                inCompare ? "bg-gold text-ink" : "border border-line-strong hover:bg-white/5",
              )}
            >
              {inCompare ? <Check size={15} /> : <Columns3 size={15} />}
              {inCompare ? "In compare" : "Add to compare"}
            </button>
            {inCompare && compared.length > 1 && (
              <Link to="/compare" className="inline-flex items-center rounded-full border border-line-strong px-4 py-2 text-sm hover:bg-white/5">
                Compare {compared.length} →
              </Link>
            )}
          </div>

          <div className="mt-8">
            <div className="eyebrow mb-3">Other versions of this reference</div>
            <div className="flex flex-wrap gap-1.5">
              {b.siblings.map((s) => (
                <Link key={s.id} to={`/build/${s.id}`} className={cx("inline-flex items-center gap-2 rounded-full border border-line py-1 pl-1 pr-3 text-[13px] transition-colors hover:border-line-strong", s.status !== "current" && "opacity-55")}>
                  <TierBadge tier={s.tier} size="sm" />
                  {s.factory} {s.version}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* aspects */}
      <section className="mt-8">
        <SectionHead eyebrow="Weighted by source, reputation, evidence and recency" title="Scorecard" />
        <div className="grid gap-x-12 gap-y-1 md:grid-cols-2">
          {meta.aspects.map((a) => {
            const s = b.aspects[a.id];
            const active = aspect === a.id;
            return (
              <button
                key={a.id}
                onClick={() => pickAspect(active ? null : a.id)}
                className={cx("group grid grid-cols-[130px_1fr_70px] items-center gap-4 rounded-xl px-3 py-3.5 text-left transition-colors", active ? "bg-white/[0.05]" : "hover:bg-white/[0.025]")}
              >
                <span>
                  <span className="block text-[14.5px]">{a.label}</span>
                  <span className="font-mono text-[10.5px] text-faint">
                    {s?.n ?? 0} claims · w{Math.round(a.weight * 100)}
                  </span>
                </span>
                <ScoreBar score={s?.score} lower={s?.lower} prev={s?.prev} />
                <span className="flex flex-col items-end">
                  <span className="tnum text-[17px]" style={{ color: scoreColor(s?.score) }}>
                    {fmtScore(s?.score)}
                  </span>
                  <Delta now={s?.score} prev={s?.prev} />
                </span>
              </button>
            );
          })}
        </div>
        <p className="mt-3 px-3 text-[11.5px] text-faint">Bar = score · tick = lower bound · dot = 90 days ago. Click an aspect to jump to a matching photo.</p>
      </section>

      {/* defects + QC */}
      <section className="mt-20 grid gap-14 lg:grid-cols-[1.3fr_1fr]">
        <div>
          <SectionHead eyebrow="Tracked across versions" title="Known defects" />
          {b.defects.length === 0 && <p className="text-sm text-muted">No recurring defects reported.</p>}
          <ul>
            {b.defects.map((d) => (
              <li key={d.id} className={cx("grid grid-cols-[28px_1fr_auto] items-start gap-3 border-b border-line py-4", d.status === "fixed" && "opacity-55")}>
                <span className="pt-1.5">
                  <Severity level={d.severity} />
                </span>
                <div>
                  <div className={cx("text-[15px] leading-snug", d.status === "fixed" && "line-through decoration-faint")}>{d.title}</div>
                  <div className="mt-1 text-xs text-muted">
                    <span className="capitalize">{d.aspect}</span> · {d.reports} reports · seen {fmtDate(d.first_seen)} – {fmtDate(d.last_seen)}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <StatusPill status={d.status} />
                  {d.fixed_in_version && <span className="text-[11px] text-good">fixed in {d.fixed_in_version}</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <SectionHead eyebrow="r/RepTimeQC" title="GL / RL" />
          {qcTotal ? (
            <>
              <div className="flex h-3 overflow-hidden rounded-full">
                <div className="bg-good" style={{ width: `${(100 * b.qc_gl) / qcTotal}%` }} />
                <div className="bg-warn/70" style={{ width: `${(100 * b.qc_mixed) / qcTotal}%` }} />
                <div className="bg-bad" style={{ width: `${(100 * b.qc_rl) / qcTotal}%` }} />
              </div>
              <div className="mt-3 flex justify-between text-xs">
                <span className="text-good">{b.qc_gl} green light</span>
                <span className="text-warn">{b.qc_mixed} mixed</span>
                <span className="text-bad">{b.qc_rl} red light</span>
              </div>
              {b.qc_trend.length > 1 && (
                <div className="mt-6">
                  <div className="eyebrow mb-2">GL rate by quarter</div>
                  <TimeChart
                    categorical
                    height={150}
                    yDomain={[0, 100]}
                    yFormat={(v) => `${Math.round(v)}%`}
                    series={[{ name: "GL rate", color: "var(--color-good)", points: b.qc_trend.map((q) => ({ x: q.period, y: q.gl_rate })) }]}
                    bars={b.qc_trend.map((q) => ({ x: q.period, y: q.n }))}
                  />
                </div>
              )}
              <ul className="mt-5">
                {b.qc.slice(0, 5).map((q, i) => (
                  <li key={i} className="flex items-center gap-3 border-b border-line py-2.5 text-[13px] last:border-0">
                    <span className={cx("w-12 font-mono text-[11px]", q.verdict === "GL" ? "text-good" : q.verdict === "RL" ? "text-bad" : "text-warn")}>{q.verdict}</span>
                    <span className="flex-1 truncate text-muted">{(JSON.parse(q.flaws) as string[]).join(", ") || "no flaws called out"}</span>
                    <span className="tnum font-mono text-[11px] text-faint">
                      {q.gl_votes}/{q.rl_votes}
                    </span>
                    <span className="text-[11px] text-faint">{fmtDate(q.decided_at)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-muted">No QC threads yet.</p>
          )}
        </div>
      </section>

      {/* prices */}
      {priceSeries.length > 0 && (
        <section className="mt-20">
          <SectionHead
            eyebrow="Telegram dealer lists"
            title="Price history"
            action={
              <div className="flex gap-4 text-xs text-muted">
                {priceSeries.map((s) => (
                  <span key={s.name} className="flex items-center gap-1.5">
                    <span className="h-1.5 w-3 rounded-full" style={{ background: s.color }} />
                    {s.name}
                  </span>
                ))}
              </div>
            }
          />
          <TimeChart series={priceSeries} yFormat={(v) => `$${Math.round(v)}`} height={240} />
        </section>
      )}

      {/* sources: links only — no posts, usernames or quotes */}
      <section className="mt-20">
        <SectionHead eyebrow={`${b.sources.length} thread${b.sources.length === 1 ? "" : "s"} analysed`} title="Sources" />
        {!b.sources.length && <p className="text-sm text-muted">No analysed threads for this version yet.</p>}
        <ul>
          {b.sources.map((src) => (
            <li key={src.url} className="border-b border-line py-4 last:border-0">
              <a href={src.url} target="_blank" rel="noreferrer noopener" className="group inline-flex items-baseline gap-2">
                <span className="text-[15.5px] transition-colors group-hover:text-gold">{src.title}</span>
                <ExternalLink size={12} className="text-muted" />
              </a>
              <div className="mt-1 text-xs text-muted">
                {src.source} · {src.forum} · {src.findings} findings · {fmtDate(src.first_post, "month")}
                {src.last_post.slice(0, 7) !== src.first_post.slice(0, 7) && ` – ${fmtDate(src.last_post, "month")}`}
              </div>
              {src.summary && <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-paper/80">{src.summary}</p>}
            </li>
          ))}
        </ul>
      </section>

      <AnimatePresence>
        {lightbox && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setLightbox(false)}
            className="fixed inset-0 z-50 grid place-items-center bg-black/90 p-4 backdrop-blur-sm"
          >
            <button className="absolute right-5 top-5 text-muted hover:text-paper" aria-label="Close">
              <X size={22} />
            </button>
            <motion.div initial={{ scale: 0.96 }} animate={{ scale: 1 }} className="aspect-square h-[min(88vh,92vw)]" onClick={(e) => e.stopPropagation()}>
              {shown && <WatchImage photo={shown.path} refId={b.reference_id} label={shown.label} />}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Fact({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <dt className="eyebrow mb-1.5">{label}</dt>
      <dd className="tnum text-[22px] leading-none">{value}</dd>
      {sub && <dd className="mt-1 text-[11px] text-faint">{sub}</dd>}
    </div>
  );
}
