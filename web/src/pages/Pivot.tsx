import { ArrowLeftRight, Download } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { useApi, type Meta, type Pivot as PivotData } from "../api";
import { Chip, ErrorNote, PageLoading } from "../components/ui";
import { cx, scoreColor } from "../lib/format";

const DIM_LABEL: Record<string, string> = {
  factory: "Factory",
  reference: "Reference",
  family: "Family",
  aspect: "Aspect",
  version: "Version",
  status: "Build status",
  source: "Source",
  source_kind: "Source type",
  evidence: "Evidence",
  kind: "Claim kind",
  year: "Year",
  quarter: "Quarter",
};
const MEASURES: Record<string, { label: string; fmt: (v: number) => string; color: (v: number, max: number) => string }> = {
  score: { label: "Avg score", fmt: (v) => v.toFixed(2), color: (v) => scoreColor(v, 0.22) },
  claims: { label: "Claims", fmt: (v) => v.toLocaleString(), color: (v, max) => `rgb(201 164 106 / ${0.05 + 0.4 * (v / max)})` },
  defect_rate: { label: "Defect rate %", fmt: (v) => v.toFixed(1), color: (v) => scoreColor(10 - v / 5, 0.22) },
  praise_rate: { label: "Praise rate %", fmt: (v) => v.toFixed(1), color: (v) => scoreColor(3 + v / 14, 0.22) },
};
const PRESETS = [
  { label: "Factory × aspect", rows: "factory", cols: "aspect", measure: "score" },
  { label: "Factory reputation by quarter", rows: "factory", cols: "quarter", measure: "score" },
  { label: "Defect rate by family", rows: "family", cols: "factory", measure: "defect_rate" },
  { label: "Where the talk happens", rows: "source", cols: "family", measure: "claims" },
  { label: "Version progress", rows: "reference", cols: "version", measure: "score" },
];

export default function Pivot() {
  const { data: meta } = useApi<Meta>("meta");
  const [params, setParams] = useSearchParams();
  const rows = params.get("rows") ?? "factory";
  const cols = params.get("cols") ?? "aspect";
  const measure = params.get("measure") ?? "score";
  const family = params.getAll("family");
  const status = params.get("status") ?? "current";

  const query = useMemo(() => {
    const q = new URLSearchParams({ rows, measure });
    if (cols !== "none") q.set("cols", cols);
    family.forEach((f) => q.append("family", f));
    if (status !== "all") q.append("status", status);
    return `pivot?${q}`;
  }, [rows, cols, measure, family, status]);
  const { data, error } = useApi<PivotData>(query);

  const update = (patch: Record<string, string | string[] | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      next.delete(k);
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
      else if (v != null) next.set(k, v);
    }
    setParams(next, { replace: true });
  };

  const grid = useMemo(() => {
    const m = new Map<string, { v: number; n: number }>();
    data?.cells.forEach((c) => m.set(`${c.r}\u0000${c.c}`, { v: c.v, n: c.n }));
    return m;
  }, [data]);

  if (error) return <ErrorNote error={error} />;
  if (!meta) return <PageLoading />;
  const M = MEASURES[measure];
  const max = Math.max(1, ...(data?.cells.map((c) => c.v) ?? [1]));
  const aspectLabel = Object.fromEntries(meta.aspects.map((a) => [a.id, a.label]));
  const label = (dim: string, v: string) => (dim === "aspect" ? aspectLabel[v] ?? v : v);

  const exportCsv = () => {
    if (!data) return;
    const lines = [[DIM_LABEL[rows], ...data.cols.map((c) => label(cols, c)), "Total"].join(",")];
    for (const r of data.rows) {
      lines.push([JSON.stringify(label(rows, r)), ...data.cols.map((c) => grid.get(`${r}\u0000${c}`)?.v ?? ""), data.row_totals[r]?.v ?? ""].join(","));
    }
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `pivot-${rows}-${cols}-${measure}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="pb-8 pt-14">
        <div className="eyebrow mb-4">Pivot</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Slice the evidence</h1>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">Every extracted claim, grouped any way you like. Unweighted — this is the raw signal the scores are built from.</p>
        <div className="mt-8 flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <Chip key={p.label} active={rows === p.rows && cols === p.cols && measure === p.measure} onClick={() => update({ rows: p.rows, cols: p.cols, measure: p.measure })}>
              {p.label}
            </Chip>
          ))}
        </div>
      </header>

      <div className="mb-6 flex flex-wrap items-end gap-4 rounded-2xl border border-line bg-panel p-4">
        <Select label="Rows" value={rows} onChange={(v) => update({ rows: v })} options={Object.keys(DIM_LABEL).filter((d) => d !== cols)} />
        <button onClick={() => update({ rows: cols === "none" ? rows : cols, cols: rows })} className="mb-1 rounded-full border border-line p-2 text-muted hover:text-paper" title="Swap rows and columns">
          <ArrowLeftRight size={15} />
        </button>
        <Select label="Columns" value={cols} onChange={(v) => update({ cols: v })} options={["none", ...Object.keys(DIM_LABEL).filter((d) => d !== rows)]} />
        <Select label="Measure" value={measure} onChange={(v) => update({ measure: v })} options={Object.keys(MEASURES)} labels={Object.fromEntries(Object.entries(MEASURES).map(([k, m]) => [k, m.label]))} />
        <Select label="Builds" value={status} onChange={(v) => update({ status: v === "current" ? null : v })} options={["current", "superseded", "discontinued", "all"]} />
        <div className="flex-1" />
        <button onClick={exportCsv} className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm text-muted hover:text-paper">
          <Download size={14} /> CSV
        </button>
      </div>
      <div className="mb-8 flex flex-wrap gap-1.5">
        {meta.families.map((f) => (
          <Chip key={f} active={family.includes(f)} onClick={() => update({ family: family.includes(f) ? family.filter((x) => x !== f) : [...family, f] })}>
            {f}
          </Chip>
        ))}
      </div>

      {!data ? (
        <div className="h-96 animate-pulse rounded-2xl bg-white/[0.03]" />
      ) : (
        <div className="-mx-4 overflow-x-auto px-4 pb-4">
          <table className="border-separate border-spacing-[3px] text-[13px]">
            <thead>
              <tr>
                <th className="eyebrow sticky left-0 z-10 bg-ink px-3 py-2 text-left font-normal">{DIM_LABEL[rows]}</th>
                {data.cols.map((c) => (
                  <th key={c} className="eyebrow min-w-[76px] px-2 py-2 text-center font-normal">
                    {label(cols, c)}
                  </th>
                ))}
                <th className="eyebrow min-w-[76px] px-2 py-2 text-center font-normal text-paper">Total</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r}>
                  <td className="sticky left-0 z-10 whitespace-nowrap bg-ink px-3 py-2 pr-6">{label(rows, r)}</td>
                  {data.cols.map((c) => {
                    const cell = grid.get(`${r}\u0000${c}`);
                    return (
                      <td
                        key={c}
                        className={cx("tnum h-10 rounded-md px-2 text-center transition-transform hover:scale-105", !cell && "text-faint")}
                        style={{ background: cell ? M.color(cell.v, max) : "rgb(255 255 255 / 0.02)", opacity: cell && cell.n < 5 ? 0.45 : 1 }}
                        title={cell ? `${cell.n} claims${cell.n < 5 ? " — low sample" : ""}` : "no data"}
                      >
                        {cell ? M.fmt(cell.v) : "·"}
                      </td>
                    );
                  })}
                  <td className="tnum rounded-md bg-white/[0.05] px-2 text-center font-medium">{data.row_totals[r] ? M.fmt(data.row_totals[r].v) : "—"}</td>
                </tr>
              ))}
              <tr>
                <td className="sticky left-0 z-10 bg-ink px-3 py-2 font-medium">Total</td>
                {data.cols.map((c) => (
                  <td key={c} className="tnum rounded-md bg-white/[0.05] px-2 py-2 text-center font-medium">
                    {data.col_totals[c] ? M.fmt(data.col_totals[c].v) : "—"}
                  </td>
                ))}
                <td className="tnum rounded-md bg-gold-soft px-2 text-center font-medium text-gold">{data.grand.v != null ? M.fmt(data.grand.v) : "—"}</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-4 text-[11.5px] text-faint">Faded cells have fewer than 5 claims. {data.grand.n.toLocaleString()} claims in view.</p>
        </div>
      )}
    </div>
  );
}

function Select({ label, value, onChange, options, labels }: { label: string; value: string; onChange: (v: string) => void; options: string[]; labels?: Record<string, string> }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="eyebrow">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="rounded-lg border border-line bg-ink px-3 py-2 text-sm capitalize outline-none focus:border-line-strong">
        {options.map((o) => (
          <option key={o} value={o}>
            {labels?.[o] ?? DIM_LABEL[o] ?? o}
          </option>
        ))}
      </select>
    </label>
  );
}
