import { useParams } from "react-router";
import { useApi, type FactoryDetail, type Meta } from "../api";
import BuildCard from "../components/BuildCard";
import { TimeChart } from "../components/Charts";
import { ErrorNote, PageLoading, SectionHead, SourceTag, Stat, StatusPill } from "../components/ui";
import { fmtDate, fmtScore } from "../lib/format";

export default function Factory() {
  const { id } = useParams();
  const { data: meta } = useApi<Meta>("meta");
  const { data: f, error } = useApi<FactoryDetail>(`factories/${id}`);
  if (error) return <ErrorNote error={error} />;
  if (!f || !meta) return <PageLoading />;

  const current = f.builds.filter((b) => b.status === "current");
  const past = f.builds.filter((b) => b.status !== "current");
  const avg = current.length ? current.reduce((s, b) => s + (b.score ?? 0), 0) / current.length : null;
  const openDefects = current.reduce((s, b) => s + b.open_defects, 0);
  const rep = f.reputation.filter((r) => r.n >= 5);

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="grid gap-10 pb-12 pt-14 lg:grid-cols-[1fr_1fr]">
        <div>
          <div className="eyebrow mb-4">Factory</div>
          <h1 className="font-display text-[72px] leading-none tracking-tight md:text-[112px]">{f.name}</h1>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <StatusPill status={f.status} />
            {f.founded && <span className="text-sm text-muted">active since {f.founded}</span>}
            {f.aliases.length > 0 && <span className="text-sm text-muted">· aka {f.aliases.join(", ")}</span>}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-6 self-end border-t border-line pt-6">
          <Stat label="Avg current" value={fmtScore(avg)} />
          <Stat label="Current builds" value={current.length} sub={`${f.builds.length} all time`} />
          <Stat label="Open defects" value={openDefects} sub="on current builds" />
        </div>
      </header>

      {rep.length > 1 && (
        <section className="mt-6">
          <SectionHead eyebrow="Average claim score per quarter · bars = volume" title="Reputation over time" />
          <TimeChart
            categorical
            height={240}
            yFormat={(v) => v.toFixed(1)}
            series={[
              { name: "Score", color: "var(--color-gold)", points: rep.map((r) => ({ x: r.period, y: r.score })) },
            ]}
            bars={rep.map((r) => ({ x: r.period, y: r.n }))}
          />
        </section>
      )}

      <section className="mt-16">
        <SectionHead eyebrow={`${current.length} builds`} title="In production" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {current.map((b, i) => (
            <BuildCard key={b.id} b={b} index={i} />
          ))}
        </div>
      </section>

      {past.length > 0 && (
        <section className="mt-16">
          <SectionHead eyebrow={`${past.length} builds`} title="Superseded & discontinued" />
          <div className="grid grid-cols-2 gap-4 opacity-80 sm:grid-cols-3 lg:grid-cols-5">
            {past.map((b, i) => (
              <BuildCard key={b.id} b={b} index={i} />
            ))}
          </div>
        </section>
      )}

      <section className="mt-16 max-w-3xl">
        <SectionHead eyebrow="Releases, closures, restocks" title="Timeline" />
        <ol className="border-l border-line pl-6">
          {f.events.map((e) => (
            <li key={e.id} className="relative pb-6">
              <span className="absolute -left-[29px] top-1.5 h-2 w-2 rounded-full bg-gold" />
              <div className="font-mono text-[11px] text-faint">{fmtDate(e.occurred_at, "long")}</div>
              <div className="mt-1 text-[15px]">{e.title}</div>
              <div className="mt-1">
                <SourceTag kind={null} name={e.source} />
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
