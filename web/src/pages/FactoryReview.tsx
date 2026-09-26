import { Check, GitMerge, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { postJson, useApi, type AdminFactory } from "../api";
import { ErrorNote, PageLoading, SectionHead, StatusPill } from "../components/ui";
import { cx } from "../lib/format";

type Data = { factories: AdminFactory[]; blocked: string[]; statuses: string[] };

export default function FactoryReview() {
  const [nonce, setNonce] = useState(0);
  const { data, error } = useApi<Data>(`admin/factories?n=${nonce}`);
  const [msg, setMsg] = useState<{ text: string; bad?: boolean } | null>(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <PageLoading />;

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      setMsg({ text: ok });
      setNonce((n) => n + 1);
    } catch (e) {
      setMsg({ text: (e as Error).message, bad: true });
    }
  };
  const flagged = data.factories.filter((f) => f.needs_review);
  const rest = data.factories.filter((f) => !f.needs_review);

  return (
    <div className="mx-auto max-w-[1100px] px-4 md:px-10">
      <header className="pb-8 pt-14">
        <Link to="/factories" className="eyebrow hover:text-paper">
          Factories
        </Link>
        <h1 className="mt-4 font-display text-[52px] leading-none tracking-tight md:text-[64px]">Factory review</h1>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
          New factory names found by the analysis land here. Confirm them, merge spelling variants into the right factory, or mark dealer names as “not a factory” so
          they’re skipped from now on. Aliases teach future analyses which name means which factory.
        </p>
      </header>

      {msg && (
        <div className={cx("mb-6 flex items-center justify-between rounded-xl border px-4 py-2.5 text-sm", msg.bad ? "border-bad/30 text-bad" : "border-good/30 text-good")}>
          {msg.text}
          <button onClick={() => setMsg(null)} aria-label="Dismiss">
            <X size={14} />
          </button>
        </div>
      )}

      <section>
        <SectionHead eyebrow={flagged.length ? `${flagged.length} to review` : "All clear"} title="Needs review" />
        {!flagged.length && <p className="mb-10 text-sm text-muted">Nothing waiting — new names from future analyses will appear here.</p>}
        <div className="space-y-4">
          {flagged.map((f) => (
            <FactoryCard key={f.id} f={f} all={data.factories} statuses={data.statuses} act={act} />
          ))}
        </div>
      </section>

      <section className="mt-16">
        <SectionHead eyebrow={`${rest.length} factories`} title="All factories" />
        <div className="space-y-3">
          {rest.map((f) => (
            <FactoryCard key={f.id} f={f} all={data.factories} statuses={data.statuses} act={act} compact />
          ))}
        </div>
      </section>

      {data.blocked.length > 0 && (
        <section className="mt-16">
          <SectionHead eyebrow="Skipped by the analysis" title="Not factories" />
          <div className="flex flex-wrap gap-2">
            {data.blocked.map((a) => (
              <span key={a} className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-[13px] text-muted">
                {a}
                <button
                  title="Unblock"
                  onClick={() => act(() => postJson(`admin/blocked/${encodeURIComponent(a)}`, undefined, "DELETE"), `“${a}” unblocked.`)}
                  className="hover:text-paper"
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function FactoryCard({
  f,
  all,
  statuses,
  act,
  compact,
}: {
  f: AdminFactory;
  all: AdminFactory[];
  statuses: string[];
  act: (fn: () => Promise<unknown>, ok: string) => void;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(!compact);
  const [name, setName] = useState(f.name);
  const [alias, setAlias] = useState("");
  const [into, setInto] = useState("");
  const base = `admin/factories/${encodeURIComponent(f.id)}`;

  return (
    <div className={cx("rounded-2xl border bg-panel", f.needs_review ? "border-warn/40" : "border-line")}>
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-4 px-5 py-4 text-left">
        <span className="font-display text-[26px] leading-none">{f.name}</span>
        <StatusPill status={f.status} />
        {f.needs_review ? <span className="rounded-full bg-warn/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warn">new</span> : null}
        <span className="ml-auto text-xs text-muted">
          {f.builds} builds · {f.claims} findings · {f.threads} threads
        </span>
      </button>

      {open && (
        <div className="grid gap-6 border-t border-line px-5 py-5 md:grid-cols-2">
          <div className="space-y-5">
            <Row label="Name">
              <input value={name} onChange={(e) => setName(e.target.value)} className="flex-1 rounded-lg border border-line bg-ink px-3 py-1.5 text-sm outline-none focus:border-line-strong" />
              {name !== f.name && (
                <button onClick={() => act(() => postJson(base, { name }), `Renamed to ${name}.`)} className="rounded-full border border-line-strong px-3 py-1 text-xs hover:bg-white/5">
                  Save
                </button>
              )}
            </Row>
            <Row label="Status">
              <select
                value={f.status}
                onChange={(e) => act(() => postJson(base, { status: e.target.value }), `Status set to ${e.target.value}.`)}
                className="rounded-lg border border-line bg-ink px-3 py-1.5 text-sm capitalize outline-none"
              >
                {statuses.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Row>
            <div>
              <div className="eyebrow mb-2">Aliases</div>
              <div className="flex flex-wrap items-center gap-1.5">
                {f.aliases.map((a) => (
                  <span key={a} className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-0.5 text-[12.5px] text-muted">
                    {a}
                    <button onClick={() => act(() => postJson(`${base}/aliases/${encodeURIComponent(a)}`, undefined, "DELETE"), `Removed alias “${a}”.`)} className="hover:text-paper">
                      <X size={11} />
                    </button>
                  </span>
                ))}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (alias.trim()) act(() => postJson(`${base}/aliases`, { alias }), `Added alias “${alias}”.`);
                    setAlias("");
                  }}
                  className="inline-flex items-center gap-1"
                >
                  <input value={alias} onChange={(e) => setAlias(e.target.value)} placeholder="add alias" className="w-28 rounded-full border border-line bg-ink px-2.5 py-0.5 text-[12.5px] outline-none" />
                  <button className="text-muted hover:text-paper" aria-label="Add alias">
                    <Plus size={14} />
                  </button>
                </form>
              </div>
            </div>
            {f.build_list.length > 0 && (
              <div>
                <div className="eyebrow mb-2">Builds</div>
                <div className="flex flex-wrap gap-1.5">
                  {f.build_list.map((b) => (
                    <Link key={b.id} to={`/build/${b.id}`} className="rounded-full border border-line px-2.5 py-0.5 font-mono text-[11px] text-muted hover:text-paper">
                      {b.reference_id} {b.version}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-4 md:border-l md:border-line md:pl-6">
            {f.needs_review ? (
              <button
                onClick={() => act(() => postJson(base, { reviewed: true }), `${f.name} confirmed.`)}
                className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-paper px-4 py-2 text-sm font-medium text-ink"
              >
                <Check size={15} /> Confirm as a factory
              </button>
            ) : null}
            <div>
              <div className="eyebrow mb-2">Same factory as…</div>
              <div className="flex gap-2">
                <select value={into} onChange={(e) => setInto(e.target.value)} className="flex-1 rounded-lg border border-line bg-ink px-3 py-1.5 text-sm outline-none">
                  <option value="">choose a factory</option>
                  {all
                    .filter((o) => o.id !== f.id)
                    .map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                </select>
                <button
                  disabled={!into}
                  onClick={() => {
                    const target = all.find((o) => o.id === into)!;
                    if (confirm(`Merge ${f.name} into ${target.name}? Its ${f.builds} build(s) and ${f.claims} finding(s) move over and “${f.name}” becomes an alias.`))
                      act(() => postJson(`${base}/merge`, { into }), `${f.name} merged into ${target.name}.`);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3 py-1.5 text-sm disabled:opacity-40"
                >
                  <GitMerge size={14} /> Merge
                </button>
              </div>
            </div>
            <button
              onClick={() => {
                if (confirm(`“${f.name}” is not a factory? Its ${f.builds} build(s) and ${f.claims} finding(s) are removed and the name is skipped in future analyses.`))
                  act(() => postJson(base, undefined, "DELETE"), `${f.name} removed and blocked.`);
              }}
              className="inline-flex items-center gap-1.5 text-sm text-bad/80 hover:text-bad"
            >
              <Trash2 size={14} /> Not a factory (e.g. a dealer)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="eyebrow mb-2">{label}</div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}
