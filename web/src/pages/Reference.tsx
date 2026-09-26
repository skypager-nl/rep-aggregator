import { Columns3 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useApi, type Meta, type ReferenceDetail } from "../api";
import { Chip, ErrorNote, PageLoading, ScoreBar, SectionHead, StatusPill, TierBadge, TierMove } from "../components/ui";
import WatchImage from "../components/WatchImage";
import { compare } from "../lib/compare";
import { cx, fmtDate, fmtPrice, fmtScore, scoreColor } from "../lib/format";

export default function Reference() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: meta } = useApi<Meta>("meta");
  const { data: ref, error } = useApi<ReferenceDetail>(`references/${id}`);
  const [currentOnly, setCurrentOnly] = useState(false);
  if (error) return <ErrorNote error={error} />;
  if (!ref || !meta) return <PageLoading />;

  const builds = ref.builds.filter((b) => !currentOnly || b.status === "current");
  const specs = [
    ["Case", `${ref.size_mm} mm`],
    ["Material", ref.material],
    ["Calibre", ref.movement],
    ["Introduced", String(ref.year_intro)],
  ];

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <section className="grid items-center gap-10 pb-14 pt-10 md:grid-cols-[1fr_1.1fr]">
        <div className="relative mx-auto aspect-square w-full max-w-[480px]">
          <div className="absolute inset-[10%] rounded-full bg-gold/10 blur-3xl" />
          <WatchImage photo={ref.photos[0]?.path} refId={ref.id} className="relative" />
        </div>
        <div>
          <Link to="/tiers" className="eyebrow transition-colors hover:text-paper">
            {ref.brand} · {ref.family}
          </Link>
          <h1 className="mt-4 font-display text-[48px] leading-[0.95] tracking-tight md:text-[72px]">{ref.name}</h1>
          <div className="mt-3 font-mono text-lg text-gold">{ref.id}</div>
          <dl className="mt-8 grid grid-cols-2 gap-x-8 gap-y-5 border-t border-line pt-6 sm:grid-cols-4">
            {specs.map(([k, v]) => (
              <div key={k}>
                <dt className="eyebrow mb-1.5">{k}</dt>
                <dd className="text-[15px]">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-6">
            <div className="eyebrow mb-2">Also known as</div>
            <div className="flex flex-wrap gap-1.5">
              {ref.aliases.map((a) => (
                <span key={a} className="rounded-full border border-line px-2.5 py-0.5 text-[12.5px] text-muted">
                  {a}
                </span>
              ))}
            </div>
          </div>
          <button
            onClick={() => {
              compare.set(ref.builds.filter((b) => b.status === "current").slice(0, 3).map((b) => b.id));
              nav("/compare");
            }}
            className="mt-8 inline-flex items-center gap-2 rounded-full border border-line-strong px-4 py-2 text-sm transition-colors hover:bg-white/5"
          >
            <Columns3 size={15} /> Compare top current builds
          </button>
        </div>
      </section>

      <section>
        <SectionHead
          eyebrow={`${ref.builds.length} builds tracked`}
          title="The ranking"
          action={
            <Chip active={currentOnly} onClick={() => setCurrentOnly((v) => !v)}>
              Current only
            </Chip>
          }
        />
        <div className="-mx-4 overflow-x-auto px-4">
          <table className="w-full min-w-[860px] text-left">
            <thead>
              <tr className="eyebrow border-b border-line">
                <th className="w-12 py-3 font-normal">#</th>
                <th className="py-3 font-normal">Build</th>
                <th className="py-3 font-normal">Tier</th>
                <th className="w-[26%] py-3 font-normal">Score · lower bound</th>
                <th className="py-3 text-right font-normal">GL rate</th>
                <th className="py-3 text-right font-normal">Defects</th>
                <th className="py-3 text-right font-normal">Price</th>
                <th className="py-3 text-right font-normal">Released</th>
              </tr>
            </thead>
            <tbody>
              {builds.map((b) => {
                const qc = b.qc_gl + b.qc_rl + b.qc_mixed;
                return (
                  <tr key={b.id} onClick={() => nav(`/build/${b.id}`)} className={cx("cursor-pointer border-b border-line transition-colors hover:bg-white/[0.025]", b.status !== "current" && "opacity-60")}>
                    <td className="py-4 font-mono text-sm text-faint">{b.rank}</td>
                    <td className="py-4">
                      <div className="font-display text-[21px] leading-tight">
                        {b.factory} <span className="text-muted">{b.version}</span>
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                        <span className="font-mono">{b.movement}</span>
                        {b.status !== "current" && <StatusPill status={b.status} />}
                      </div>
                    </td>
                    <td className="py-4">
                      <span className="flex items-center gap-2">
                        <TierBadge tier={b.tier} />
                        <TierMove from={b.prev_tier} to={b.tier} />
                      </span>
                    </td>
                    <td className="py-4 pr-8">
                      <div className="mb-2 flex items-baseline gap-2">
                        <span className="tnum text-[17px]">{fmtScore(b.score, 2)}</span>
                        <span className="tnum text-xs text-muted">≥ {fmtScore(b.lower, 2)}</span>
                        <span className="text-xs text-faint">· {b.claims} claims</span>
                      </div>
                      <ScoreBar score={b.score} lower={b.lower} />
                    </td>
                    <td className="tnum py-4 text-right text-sm">{qc ? `${Math.round((100 * b.qc_gl) / qc)}%` : "—"}<div className="text-[11px] text-faint">{qc} QCs</div></td>
                    <td className={cx("tnum py-4 text-right text-sm", b.open_defects ? "text-warn" : "text-muted")}>{b.open_defects || "—"}</td>
                    <td className="tnum py-4 text-right text-sm">{fmtPrice(b.price)}</td>
                    <td className="py-4 text-right text-sm text-muted">{fmtDate(b.released, "month")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-20">
        <SectionHead eyebrow="Per-aspect score, 0–10" title="Where each build wins and loses" />
        <div className="-mx-4 overflow-x-auto px-4">
          <table className="w-full min-w-[860px] border-separate border-spacing-1 text-center">
            <thead>
              <tr>
                <th className="w-48" />
                {meta.aspects.map((a) => (
                  <th key={a.id} className="eyebrow pb-2 font-normal">
                    {a.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {builds.map((b) => (
                <tr key={b.id}>
                  <td className="pr-3 text-left">
                    <Link to={`/build/${b.id}`} className="flex items-center gap-2 text-sm hover:text-gold">
                      <TierBadge tier={b.tier} size="sm" />
                      {b.factory} <span className="text-muted">{b.version}</span>
                    </Link>
                  </td>
                  {meta.aspects.map((a) => {
                    const s = b.aspects[a.id];
                    return (
                      <td key={a.id} className="tnum h-11 rounded-md text-[13px]" style={{ background: scoreColor(s?.score, 0.2), color: scoreColor(s?.score) }} title={`${s?.n ?? 0} claims`}>
                        {fmtScore(s?.score)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
