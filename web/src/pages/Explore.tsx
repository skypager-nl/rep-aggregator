import { LayoutGrid, Rows3, Search, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useApi, type BuildSummary, type Meta } from "../api";
import BuildCard from "../components/BuildCard";
import { Chip, ErrorNote, PageLoading, ScoreBar, StatusPill, TierBadge } from "../components/ui";
import { TIER_ORDER, cx, fmtDate, fmtPrice, fmtScore, ver } from "../lib/format";

const SORTS: Record<string, { label: string; key: (b: BuildSummary) => number }> = {
  lower: { label: "Tier strength", key: (b) => b.lower ?? -1 },
  score: { label: "Score", key: (b) => b.score ?? -1 },
  gl: { label: "QC green-light rate", key: (b) => (b.qc_gl + b.qc_rl + b.qc_mixed ? b.qc_gl / (b.qc_gl + b.qc_rl + b.qc_mixed) : -1) },
  claims: { label: "Most discussed", key: (b) => b.claims ?? 0 },
  price_low: { label: "Price, low first", key: (b) => -(b.price ?? 9999) },
  released: { label: "Newest", key: (b) => Date.parse(b.released) },
  defects: { label: "Fewest open defects", key: (b) => -b.open_defects },
};

export default function Explore() {
  const { data: meta } = useApi<Meta>("meta");
  const { data, error } = useApi<BuildSummary[]>("builds");
  const [params, setParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);

  const list = (k: string) => params.getAll(k);
  const toggle = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    const cur = next.getAll(k);
    next.delete(k);
    (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]).forEach((x) => next.append(k, x));
    setParams(next, { replace: true });
  };
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v == null || v === "") next.delete(k);
    else next.set(k, v);
    setParams(next, { replace: true });
  };

  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "current";
  const sort = params.get("sort") ?? "lower";
  const view = params.get("view") ?? "grid";
  const minScore = Number(params.get("min") ?? 0);
  const maxPrice = Number(params.get("maxp") ?? 0);
  const brands = list("brand");
  const families = list("family");
  const factories = list("factory");
  const tiers = list("tier");

  const results = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data
      .filter((b) => status === "all" || b.status === status)
      .filter((b) => !brands.length || brands.includes(b.brand))
      .filter((b) => !families.length || families.includes(b.family))
      .filter((b) => !factories.length || factories.includes(b.factory_id))
      .filter((b) => !tiers.length || (b.tier && tiers.includes(b.tier)))
      .filter((b) => (b.score ?? 0) >= minScore)
      .filter((b) => !maxPrice || (b.price ?? 0) <= maxPrice)
      .filter((b) => !needle || `${b.brand} ${b.reference_id} ${b.reference_name} ${b.factory} ${ver(b.version)} ${b.movement} ${b.family}`.toLowerCase().includes(needle))
      .sort((a, b) => SORTS[sort].key(b) - SORTS[sort].key(a));
  }, [data, q, status, brands, families, factories, tiers, minScore, maxPrice, sort]);

  if (error) return <ErrorNote error={error} />;
  if (!data || !meta) return <PageLoading />;
  const activeCount = brands.length + families.length + factories.length + tiers.length + (minScore ? 1 : 0) + (maxPrice ? 1 : 0) + (status !== "current" ? 1 : 0);

  const filters = (
    <div className="space-y-8">
      <Group label="Brand">
        {meta.brands.filter((b) => b.builds > 0).map((b) => (
          <Chip key={b.brand} active={brands.includes(b.brand)} onClick={() => toggle("brand", b.brand)}>
            {b.brand}
          </Chip>
        ))}
      </Group>
      <Group label="Model">
        {[...new Set(data.filter((b) => !brands.length || brands.includes(b.brand)).map((b) => b.family))].sort().map((f) => (
          <Chip key={f} active={families.includes(f)} onClick={() => toggle("family", f)}>
            {f}
          </Chip>
        ))}
      </Group>
      <Group label="Factory">
        {meta.factories.map((f) => (
          <Chip key={f.id} active={factories.includes(f.id)} onClick={() => toggle("factory", f.id)}>
            {f.name}
          </Chip>
        ))}
      </Group>
      <Group label="Tier">
        {TIER_ORDER.map((t) => (
          <Chip key={t} active={tiers.includes(t)} onClick={() => toggle("tier", t)}>
            {t}
          </Chip>
        ))}
      </Group>
      <Group label="Status">
        {["current", "superseded", "discontinued", "all"].map((s) => (
          <Chip key={s} active={status === s} onClick={() => set("status", s === "current" ? null : s)} className="capitalize">
            {s}
          </Chip>
        ))}
      </Group>
      <Range label="Minimum score" value={minScore} min={0} max={9} step={0.1} display={minScore ? fmtScore(minScore) : "any"} onChange={(v) => set("min", v ? String(v) : null)} />
      <Range label="Max price" value={maxPrice || 700} min={350} max={700} step={10} display={maxPrice ? `$${maxPrice}` : "any"} onChange={(v) => set("maxp", v >= 700 ? null : String(v))} />
      {activeCount > 0 && (
        <button onClick={() => setParams(new URLSearchParams(), { replace: true })} className="text-sm text-muted underline-offset-4 hover:text-paper hover:underline">
          Reset filters
        </button>
      )}
    </div>
  );

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="pb-10 pt-14">
        <div className="eyebrow mb-4">Explore</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Every version</h1>
      </header>

      <div className="grid gap-10 lg:grid-cols-[260px_1fr]">
        <aside className="hidden lg:block">
          <div className="sticky top-24">{filters}</div>
        </aside>

        <div>
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <label className="flex min-w-60 flex-1 items-center gap-2 rounded-full border border-line bg-panel px-4 py-2 focus-within:border-line-strong">
              <Search size={15} className="text-muted" />
              <input
                value={q}
                onChange={(e) => set("q", e.target.value)}
                placeholder="Search brand, reference, model, factory, calibre…"
                className="w-full bg-transparent text-sm outline-none placeholder:text-faint"
              />
            </label>
            <button onClick={() => setFiltersOpen((o) => !o)} className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm lg:hidden">
              <SlidersHorizontal size={15} /> Filters {activeCount > 0 && <span className="text-gold">{activeCount}</span>}
            </button>
            <select value={sort} onChange={(e) => set("sort", e.target.value === "lower" ? null : e.target.value)} className="rounded-full border border-line bg-panel px-4 py-2 text-sm outline-none">
              {Object.entries(SORTS).map(([k, s]) => (
                <option key={k} value={k}>
                  {s.label}
                </option>
              ))}
            </select>
            <div className="flex rounded-full border border-line p-0.5">
              {[
                ["grid", LayoutGrid],
                ["table", Rows3],
              ].map(([v, Icon]) => {
                const I = Icon as typeof LayoutGrid;
                return (
                  <button key={v as string} onClick={() => set("view", v === "grid" ? null : (v as string))} className={cx("rounded-full p-1.5", view === v ? "bg-white/10 text-paper" : "text-muted")} aria-label={`${v} view`}>
                    <I size={15} />
                  </button>
                );
              })}
            </div>
          </div>
          {filtersOpen && <div className="mb-8 rounded-2xl border border-line bg-panel p-5 lg:hidden">{filters}</div>}

          <div className="eyebrow mb-4">
            {results.length} of {data.length} builds
          </div>

          {view === "grid" ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {results.map((b, i) => (
                <BuildCard key={b.id} b={b} index={i} />
              ))}
            </div>
          ) : (
            <div className="-mx-4 overflow-x-auto px-4">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead>
                  <tr className="eyebrow border-b border-line">
                    <th className="py-3 font-normal">Tier</th>
                    <th className="py-3 font-normal">Version</th>
                    <th className="py-3 font-normal">Reference</th>
                    <th className="w-44 py-3 font-normal">Score</th>
                    <th className="py-3 text-right font-normal">GL</th>
                    <th className="py-3 text-right font-normal">Defects</th>
                    <th className="py-3 text-right font-normal">Price</th>
                    <th className="py-3 text-right font-normal">Released</th>
                    <th className="py-3 text-right font-normal">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((b) => {
                    const qc = b.qc_gl + b.qc_rl + b.qc_mixed;
                    return (
                      <tr key={b.id} className="border-b border-line transition-colors hover:bg-white/[0.025]">
                        <td className="py-3">
                          <TierBadge tier={b.tier} size="sm" />
                        </td>
                        <td className="py-3">
                          <Link to={`/build/${b.id}`} className="hover:text-gold">
                            {b.factory} <span className="text-muted">{ver(b.version)}</span>
                          </Link>
                        </td>
                        <td className="py-3">
                          <Link to={`/ref/${encodeURIComponent(b.reference_id)}`} className="font-mono text-xs hover:text-gold">
                            {b.reference_id}
                          </Link>{" "}
                          <span className="text-xs text-muted">{b.reference_name}</span>
                        </td>
                        <td className="py-3 pr-6">
                          <div className="flex items-center gap-3">
                            <span className="tnum w-8">{fmtScore(b.score)}</span>
                            <ScoreBar score={b.score} lower={b.lower} compact />
                          </div>
                        </td>
                        <td className="tnum py-3 text-right">{qc ? `${Math.round((100 * b.qc_gl) / qc)}%` : "—"}</td>
                        <td className={cx("tnum py-3 text-right", b.open_defects ? "text-warn" : "text-faint")}>{b.open_defects || "—"}</td>
                        <td className="tnum py-3 text-right">{fmtPrice(b.price)}</td>
                        <td className="py-3 text-right text-muted">{fmtDate(b.released, "month")}</td>
                        <td className="py-3 text-right">
                          <StatusPill status={b.status} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {!results.length && <div className="py-24 text-center text-muted">Nothing matches — loosen a filter.</div>}
        </div>
      </div>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="eyebrow mb-3">{label}</div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function Range(props: { label: string; value: number; min: number; max: number; step: number; display: string; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="mb-3 flex justify-between">
        <span className="eyebrow">{props.label}</span>
        <span className="tnum text-xs text-paper">{props.display}</span>
      </div>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
        className="w-full accent-[var(--color-gold)]"
      />
    </div>
  );
}
