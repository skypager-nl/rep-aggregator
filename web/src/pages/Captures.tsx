import { AlertTriangle, Check, Copy, ExternalLink, Eye, EyeOff, Loader2, Puzzle, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { postJson, useApi, type CaptureLog, type CapturedThread, type Extraction, type RwgStatus } from "../api";
import { Chip, ErrorNote, PageLoading, SectionHead } from "../components/ui";
import { ago, cx, fmtDate } from "../lib/format";

const SOURCES = [
  ["all", "All"],
  ["capture", "My captures"],
  ["reddit", "Reddit"],
  ["rwg", "RWG"],
  ["telegram", "Telegram"],
] as const;
const STATUSES = [
  ["new", "Not analysed"],
  ["queued", "Queued"],
  ["analysed", "Analysed"],
  ["stale", "New pages since analysis"],
  ["failed", "Failed"],
  ["all", "Any status"],
] as const;
const key = (t: CapturedThread) => `${t.source_id}\u0000${t.thread_id}`;

export default function Captures() {
  const [nonce, setNonce] = useState(0);
  const [source, setSource] = useState("all");
  const [status, setStatus] = useState("new");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Record<string, CapturedThread>>({});
  const query = `captures?source=${source}&status=${status}&q=${encodeURIComponent(q)}&limit=100&n=${nonce}`;
  const { data, error } = useApi<{ threads: CapturedThread[]; total: number; log: CaptureLog[] }>(query);
  const { data: ex } = useApi<Extraction>(`extraction?n=${nonce}`);
  if (error) return <ErrorNote error={error} />;
  const now = new Date().toISOString();
  const refresh = () => setNonce((n) => n + 1);
  const selected = Object.values(picked);
  const total = selected.reduce((sum, t) => sum + t.estimate_usd, 0);
  const queue = (items: CapturedThread[]) =>
    postJson("analyse", { items: items.map((t) => [t.source_id, t.thread_id]) }).then(() => {
      setPicked({});
      refresh();
    });

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="pb-8 pt-14">
        <div className="eyebrow mb-4">RWI · Reddit · RWG · Telegram</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Captures</h1>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
          Everything collected, waiting for your decision. Nothing is sent to Claude until you pick it — only the conclusion and a link to the source end up on the site.
        </p>
        {ex && !ex.configured && (
          <div className="mt-6 flex max-w-2xl items-start gap-3 rounded-xl border border-warn/30 bg-warn/[0.06] px-4 py-3 text-sm text-warn">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            Add your Anthropic API key under Settings → Apps → Rep Index → Configuration to analyse anything.
          </div>
        )}
        {ex?.auto && <p className="mt-4 text-sm text-warn">Auto-analysis is on in the app options — new material is analysed without asking.</p>}
      </header>

      <div className="grid gap-12 lg:grid-cols-[1fr_380px]">
        <section>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {SOURCES.map(([k, label]) => (
              <Chip key={k} active={source === k} onClick={() => (setSource(k), setPicked({}))}>
                {label}
              </Chip>
            ))}
          </div>
          <div className="mb-4 flex flex-wrap items-center gap-1.5">
            {STATUSES.map(([k, label]) => (
              <Chip key={k} active={status === k} onClick={() => (setStatus(k), setPicked({}))}>
                {label}
              </Chip>
            ))}
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search titles…" className="ml-auto w-48 rounded-full border border-line bg-panel px-3 py-1 text-[13px] outline-none" />
          </div>

          <div className="sticky top-16 z-20 mb-2 flex items-center gap-3 border-y border-line bg-ink/90 py-2.5 text-sm backdrop-blur">
            <span className="text-muted">
              {data ? `${data.total.toLocaleString()} match${data.total === 1 ? "" : "es"}` : "…"}
              {selected.length > 0 && ` · ${selected.length} selected`}
            </span>
            {data && data.threads.some((t) => !t.analyse_requested) && (
              <button
                onClick={() => setPicked(Object.fromEntries(data.threads.filter((t) => !t.analyse_requested).map((t) => [key(t), t])))}
                className="text-xs text-muted hover:text-paper"
              >
                Select all shown
              </button>
            )}
            {selected.length > 0 && (
              <>
                <button onClick={() => setPicked({})} className="text-xs text-muted hover:text-paper">
                  Clear
                </button>
                <button onClick={() => queue(selected)} className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-paper px-4 py-1.5 text-sm font-medium text-ink">
                  <Sparkles size={13} /> Analyse {selected.length} · ~${total.toFixed(2)}
                </button>
              </>
            )}
          </div>

          {!data ? (
            <PageLoading />
          ) : !data.threads.length ? (
            <p className="py-10 text-sm text-muted">Nothing here.</p>
          ) : (
            <ul>
              {data.threads.map((t) => (
                <ThreadRow
                  key={key(t)}
                  t={t}
                  now={now}
                  busy={ex?.busy === t.thread_id}
                  picked={!!picked[key(t)]}
                  onPick={(on) => setPicked((p) => (on ? { ...p, [key(t)]: t } : Object.fromEntries(Object.entries(p).filter(([k]) => k !== key(t)))))}
                  onQueue={() => queue([t])}
                  onCancel={() => postJson("analyse/cancel", { items: [[t.source_id, t.thread_id]] }).then(refresh)}
                />
              ))}
            </ul>
          )}
          {data && data.total > data.threads.length && <p className="mt-4 text-xs text-faint">Showing the 100 most recent — narrow it down with the filters or search.</p>}
        </section>

        <aside className="space-y-10">
          {ex && <Budget ex={ex} />}
          <RwgCard nonce={nonce} onChange={refresh} />
          <Setup />
          {data && (
            <div>
              <SectionHead eyebrow="Last 50" title="Capture log" />
              <ul className="space-y-2 text-[12.5px]">
                {data.log.map((l) => (
                  <li key={l.id} className="flex justify-between gap-3 text-muted">
                    <span className="truncate">
                      #{l.thread_id} · p{l.page}
                    </span>
                    <span className="tnum shrink-0">
                      +{l.new_posts} posts · {fmtDate(l.captured_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function ThreadRow({
  t,
  now,
  busy,
  picked,
  onPick,
  onQueue,
  onCancel,
}: {
  t: CapturedThread;
  now: string;
  busy: boolean;
  picked: boolean;
  onPick: (on: boolean) => void;
  onQueue: () => void;
  onCancel: () => void;
}) {
  const builds: string[] = t.builds ? JSON.parse(t.builds) : [];
  const stale = !!t.extracted_at && t.extracted_at < t.last_captured;
  const status = busy
    ? { label: "Analysing…", tone: "text-gold border-gold/40", icon: <Loader2 size={11} className="animate-spin" /> }
    : t.analyse_requested
      ? { label: "Queued", tone: "text-gold border-gold/30", icon: null }
      : t.extract_error
        ? { label: "Failed", tone: "text-bad border-bad/30", icon: <AlertTriangle size={11} /> }
        : !t.extracted_at
          ? { label: "Not analysed", tone: "text-muted border-line", icon: null }
          : stale
            ? { label: "New pages", tone: "text-warn border-warn/30", icon: null }
            : { label: "Analysed", tone: "text-good border-good/30", icon: <Sparkles size={11} /> };
  const kind = t.source_kind === "telegram" ? "Telegram channel" : t.source_kind === "reddit" ? t.forum : `${t.source_id.toUpperCase()} · ${t.forum ?? ""}`;
  return (
    <li className="flex gap-3 border-b border-line py-4">
      <input
        type="checkbox"
        checked={picked}
        disabled={!!t.analyse_requested || busy}
        onChange={(e) => onPick(e.target.checked)}
        className="mt-1.5 h-4 w-4 shrink-0 accent-[var(--color-gold)]"
        aria-label="Select for analysis"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <a href={t.url} target="_blank" rel="noreferrer noopener" className="group min-w-0 flex-1">
            <span className="text-[15.5px] transition-colors group-hover:text-gold">{t.title}</span>
            <ExternalLink size={12} className="ml-1.5 inline text-muted" />
            <div className="mt-1 text-xs text-muted">
              {kind} · {t.posts} {t.source_kind === "telegram" ? "messages" : "posts"}
              {t.source_kind === "forum" && t.pages > 1 && ` · ${t.pages_captured}/${t.pages} pages`} · updated {ago(t.last_captured, now)}
              {t.extract_cost != null && ` · spent $${t.extract_cost.toFixed(2)}`}
            </div>
          </a>
          <span className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider", status.tone)}>
            {status.icon}
            {status.label}
          </span>
        </div>
        {t.summary && <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-paper/85">{t.summary}</p>}
        {t.extract_error && <p className="mt-2 text-xs text-bad">{t.extract_error}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {builds.map((id) => (
            <Link key={id} to={`/build/${id}`} className="rounded-full border border-line px-2.5 py-0.5 font-mono text-[11px] text-muted hover:border-line-strong hover:text-paper">
              {id}
            </Link>
          ))}
          <span className="ml-auto flex items-center gap-3">
            {t.analyse_requested ? (
              <button onClick={onCancel} className="text-xs text-muted hover:text-paper">
                Cancel
              </button>
            ) : (
              !busy && (
                <button onClick={onQueue} className="inline-flex items-center gap-1 rounded-full border border-line-strong px-3 py-1 text-xs hover:bg-white/5">
                  <Sparkles size={11} /> {t.extracted_at ? "Re-analyse" : "Analyse"} · ~${t.estimate_usd.toFixed(2)}
                </button>
              )
            )}
          </span>
        </div>
      </div>
    </li>
  );
}

function Setup() {
  const { data } = useApi<{ token: string; port: number }>("capture/setup");
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const endpoint = `http://<your-pi-ip>:${data?.port ?? 8766}`;
  const copy = (label: string, v: string) => {
    navigator.clipboard.writeText(v).then(() => {
      setCopied(label);
      setTimeout(() => setCopied(null), 1500);
    });
  };
  return (
    <div className="rounded-2xl border border-line bg-panel p-5">
      <div className="mb-4 flex items-center gap-2">
        <Puzzle size={16} className="text-gold" />
        <span className="font-display text-2xl leading-none">Extension setup</span>
      </div>
      <ol className="list-decimal space-y-2 pl-4 text-[13px] text-muted">
        <li>
          Chrome → <span className="font-mono text-paper">chrome://extensions</span> → Developer mode → Load unpacked → the repo’s <span className="font-mono text-paper">extension/</span> folder.
        </li>
        <li>In the extension’s options, enter the Pi’s IP address (not homeassistant.local) and the token below.</li>
        <li>On any RWI thread, click the extension icon → Capture whole thread.</li>
      </ol>
      <Field label="Address" value={endpoint} onCopy={() => copy("addr", endpoint)} copied={copied === "addr"} />
      <Field
        label="Token"
        value={data ? (show ? data.token : "•".repeat(24)) : "…"}
        onCopy={() => data && copy("token", data.token)}
        copied={copied === "token"}
        extra={
          <button onClick={() => setShow((s) => !s)} className="text-muted hover:text-paper" aria-label="Show token">
            {show ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        }
      />
    </div>
  );
}

function Field({ label, value, onCopy, copied, extra }: { label: string; value: string; onCopy: () => void; copied: boolean; extra?: React.ReactNode }) {
  return (
    <div className="mt-4">
      <div className="eyebrow mb-1.5">{label}</div>
      <div className="flex items-center gap-2 rounded-lg border border-line bg-ink px-3 py-2">
        <span className="flex-1 truncate font-mono text-[12px]">{value}</span>
        {extra}
        <button onClick={onCopy} className="text-muted hover:text-paper" aria-label={`Copy ${label}`}>
          {copied ? <Check size={14} className="text-good" /> : <Copy size={14} />}
        </button>
      </div>
    </div>
  );
}

function Budget({ ex }: { ex: Extraction }) {
  const pct = Math.min(100, (100 * ex.spent_today) / ex.daily_budget);
  return (
    <div className="rounded-2xl border border-line bg-panel p-5">
      <div className="flex items-baseline justify-between">
        <span className="font-display text-2xl leading-none">Analysis budget</span>
        <span className="tnum text-sm text-muted">
          ${ex.spent_today.toFixed(2)} / ${ex.daily_budget.toFixed(2)} today
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className={cx("h-full", ex.budget_reached ? "bg-warn" : "bg-gold")} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted">
        {ex.queued} queued{ex.budget_reached ? " — daily budget reached, the rest continues tomorrow" : ""}. Only threads you picked are analysed.
      </p>
    </div>
  );
}

function RwgCard({ nonce, onChange }: { nonce: number; onChange: () => void }) {
  const { data: s } = useApi<RwgStatus>(`rwg?n=${nonce}`);
  if (!s) return null;
  const state = s.paused ? "Paused" : !s.enabled ? "Off" : s.last_error ? "Waiting" : "Collecting";
  const tone = s.paused ? "text-bad border-bad/30" : !s.enabled ? "text-muted border-line" : s.last_error ? "text-warn border-warn/30" : "text-good border-good/30";
  return (
    <div className="rounded-2xl border border-line bg-panel p-5">
      <div className="flex items-center justify-between">
        <span className="font-display text-2xl leading-none">RWG collector</span>
        <span className={cx("rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider", tone)}>{state}</span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
        <div>
          <dt className="eyebrow">Threads found</dt>
          <dd className="tnum">{s.topics_known.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="eyebrow">Fully read</dt>
          <dd className="tnum">{s.topics_complete.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="eyebrow">Requests today</dt>
          <dd className="tnum">
            {s.requests_today} / {s.daily_cap}
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Sections backfilled</dt>
          <dd className="tnum">
            {s.forums_backfilled} / {s.forums}
          </dd>
        </div>
      </dl>
      {s.exit && <p className="mt-3 font-mono text-[11px] text-faint">via {s.exit}</p>}
      {!s.enabled && <p className="mt-3 text-xs text-muted">Enable in Settings → Apps → Rep Index → Configuration → collectors → rwg. Only runs through the VPN route.</p>}
      {s.paused && <p className="mt-3 text-xs text-bad">{s.pause_reason}</p>}
      {!s.paused && s.last_error && <p className="mt-3 text-xs text-warn">{s.last_error}</p>}
      <div className="mt-4 flex gap-2">
        {s.paused && (
          <button onClick={() => postJson("rwg/resume").then(onChange)} className="rounded-full border border-line-strong px-3 py-1 text-xs hover:bg-white/5">
            Resume
          </button>
        )}
        {s.enabled && !s.paused && (
          <button onClick={() => postJson("rwg/run").then(() => setTimeout(onChange, 1500))} className="rounded-full border border-line-strong px-3 py-1 text-xs hover:bg-white/5">
            Run a cycle now
          </button>
        )}
      </div>
    </div>
  );
}
