import { Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { fetchJson, useApi, type BuildDetail, type BuildSummary, type Meta } from "../api";
import { PageLoading, ScoreBar, StatusPill, TierBadge } from "../components/ui";
import WatchImage from "../components/WatchImage";
import { compare, useCompare } from "../lib/compare";
import { cx, fmtDate, fmtPrice, fmtScore, scoreColor } from "../lib/format";

export default function Compare() {
  const ids = useCompare();
  const { data: meta } = useApi<Meta>("meta");
  const { data: all } = useApi<BuildSummary[]>("builds");
  const [builds, setBuilds] = useState<BuildDetail[]>([]);
  const [picking, setPicking] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    let live = true;
    Promise.all(ids.map((id) => fetchJson<BuildDetail>(`builds/${id}`))).then((bs) => live && setBuilds(bs));
    return () => {
      live = false;
    };
  }, [ids]);

  const options = useMemo(() => {
    const needle = q.toLowerCase();
    return (all ?? [])
      .filter((b) => !ids.includes(b.id))
      .filter((b) => !needle || `${b.reference_id} ${b.reference_name} ${b.factory} ${b.version}`.toLowerCase().includes(needle))
      .slice(0, 12);
  }, [all, ids, q]);

  if (!meta) return <PageLoading />;
  const shown = builds.filter((b) => ids.includes(b.id));
  const best = (f: (b: BuildDetail) => number | null | undefined, low = false) => {
    const vals = shown.map(f).filter((v): v is number => v != null);
    if (vals.length < 2) return null;
    return low ? Math.min(...vals) : Math.max(...vals);
  };
  const glRate = (b: BuildDetail) => {
    const n = b.qc_gl + b.qc_rl + b.qc_mixed;
    return n ? (100 * b.qc_gl) / n : null;
  };
  const cols = `180px repeat(${Math.max(shown.length, 1)}, minmax(210px, 1fr))${shown.length < 4 ? " 150px" : ""}`;

  const Row = ({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) => (
    <div className={cx("grid items-center gap-4 border-b border-line py-3.5", className)} style={{ gridTemplateColumns: cols }}>
      <div className="eyebrow">{label}</div>
      {children}
      {shown.length < 4 && <div />}
    </div>
  );
  const Val = ({ v, isBest, children }: { v: number | null | undefined; isBest: number | null; children: React.ReactNode }) => (
    <div className={cx("tnum text-[15px]", v != null && isBest != null && v === isBest && "text-gold")}>{children}</div>
  );

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="flex flex-wrap items-end justify-between gap-6 pb-10 pt-14">
        <div>
          <div className="eyebrow mb-4">Compare</div>
          <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Side by side</h1>
        </div>
        {ids.length > 0 && (
          <button onClick={compare.clear} className="text-sm text-muted hover:text-paper">
            Clear all
          </button>
        )}
      </header>

      {picking && (
        <div className="mb-8 rounded-2xl border border-line bg-panel p-4">
          <label className="flex items-center gap-2 rounded-full border border-line bg-ink px-4 py-2">
            <Search size={15} className="text-muted" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a version…" className="w-full bg-transparent text-sm outline-none" />
            <button onClick={() => setPicking(false)} className="text-muted">
              <X size={15} />
            </button>
          </label>
          <div className="mt-3 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {options.map((b) => (
              <button key={b.id} onClick={() => { compare.toggle(b.id); setPicking(false); setQ(""); }} className="flex items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5">
                <TierBadge tier={b.tier} size="sm" />
                <span className="font-mono text-xs text-muted">{b.reference_id}</span>
                <span className="truncate">
                  {b.factory} {b.version}
                </span>
                {b.status !== "current" && <span className="ml-auto"><StatusPill status={b.status} /></span>}
              </button>
            ))}
          </div>
        </div>
      )}

      {!ids.length ? (
        <div className="rounded-3xl border border-dashed border-line-strong py-24 text-center">
          <p className="font-display text-3xl">Nothing to compare yet</p>
          <p className="mt-3 text-sm text-muted">Add versions from their pages, or pick some here.</p>
          <button onClick={() => setPicking(true)} className="mt-6 inline-flex items-center gap-2 rounded-full bg-paper px-5 py-2.5 text-sm text-ink">
            <Plus size={15} /> Add a version
          </button>
        </div>
      ) : (
        <div className="-mx-4 overflow-x-auto px-4">
          <div className="min-w-[760px]">
            <div className="grid gap-4 pb-6" style={{ gridTemplateColumns: cols }}>
              <div />
              {shown.map((b) => (
                <div key={b.id} className="relative">
                  <button onClick={() => compare.toggle(b.id)} className="absolute right-2 top-2 z-10 rounded-full bg-ink/70 p-1.5 text-muted backdrop-blur hover:text-paper" aria-label="Remove">
                    <X size={13} />
                  </button>
                  <Link to={`/build/${b.id}`} className="group block">
                    <div className="aspect-square overflow-hidden rounded-2xl border border-line bg-[radial-gradient(circle_at_50%_40%,#1d1d21,#0a0a0b_75%)]">
                      <WatchImage photo={b.ref_photo} refId={b.reference_id} className="p-3 transition-transform duration-700 group-hover:scale-105" />
                    </div>
                    <div className="mt-3 font-display text-[26px] leading-tight group-hover:text-gold">
                      {b.factory} <span className="text-muted">{b.version}</span>
                    </div>
                    <div className="font-mono text-xs text-muted">{b.reference_id}</div>
                  </Link>
                </div>
              ))}
              {shown.length < 4 && (
                <button onClick={() => setPicking(true)} className="flex aspect-square flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line-strong text-sm text-muted hover:text-paper">
                  <Plus size={18} /> Add
                </button>
              )}
            </div>

            <Row label="Tier">
              {shown.map((b) => (
                <TierBadge key={b.id} tier={b.tier} title />
              ))}
            </Row>
            <Row label="Overall">
              {shown.map((b) => (
                <Val key={b.id} v={b.score} isBest={best((x) => x.score)}>
                  <span className="font-display text-[30px] leading-none">{fmtScore(b.score, 2)}</span>
                  <span className="ml-2 text-xs text-muted">≥ {fmtScore(b.lower, 2)}</span>
                </Val>
              ))}
            </Row>
            {meta.aspects.map((a) => {
              const top = best((b) => b.aspects[a.id]?.score);
              return (
                <Row key={a.id} label={a.label}>
                  {shown.map((b) => {
                    const s = b.aspects[a.id];
                    return (
                      <div key={b.id} className="flex items-center gap-3">
                        <span className={cx("tnum w-9 text-[14px]", s && top === s.score && "text-gold")} style={s && top !== s.score ? { color: scoreColor(s.score) } : undefined}>
                          {fmtScore(s?.score)}
                        </span>
                        <ScoreBar score={s?.score} lower={s?.lower} compact />
                      </div>
                    );
                  })}
                </Row>
              );
            })}
            <Row label="QC green-light">
              {shown.map((b) => (
                <Val key={b.id} v={glRate(b)} isBest={best(glRate)}>
                  {glRate(b) == null ? "—" : `${Math.round(glRate(b)!)}%`}
                  <span className="ml-2 text-xs text-faint">{b.qc_gl + b.qc_rl + b.qc_mixed} QCs</span>
                </Val>
              ))}
            </Row>
            <Row label="Open defects">
              {shown.map((b) => (
                <Val key={b.id} v={b.open_defects} isBest={best((x) => x.open_defects, true)}>
                  {b.open_defects}
                  <div className="mt-1 space-y-0.5">
                    {b.defects
                      .filter((d) => d.status !== "fixed")
                      .slice(0, 3)
                      .map((d) => (
                        <div key={d.id} className="truncate text-xs text-muted">
                          {d.title}
                        </div>
                      ))}
                  </div>
                </Val>
              ))}
            </Row>
            <Row label="Dealer price">
              {shown.map((b) => (
                <Val key={b.id} v={b.price} isBest={best((x) => x.price, true)}>
                  {fmtPrice(b.price)}
                </Val>
              ))}
            </Row>
            <Row label="Movement">
              {shown.map((b) => (
                <div key={b.id} className="font-mono text-sm">
                  {b.movement}
                </div>
              ))}
            </Row>
            <Row label="Released">
              {shown.map((b) => (
                <div key={b.id} className="text-sm text-muted">
                  {fmtDate(b.released, "month")} · <StatusPill status={b.status} />
                </div>
              ))}
            </Row>
            <Row label="Claims">
              {shown.map((b) => (
                <Val key={b.id} v={b.claims} isBest={best((x) => x.claims)}>
                  {b.claims}
                </Val>
              ))}
            </Row>
          </div>
        </div>
      )}
    </div>
  );
}
