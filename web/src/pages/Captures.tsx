import { AlertTriangle, Check, Copy, ExternalLink, Eye, EyeOff, Loader2, Puzzle, RotateCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { postJson, useApi, type CaptureLog, type CapturedThread, type Extraction } from "../api";
import { ErrorNote, PageLoading, SectionHead } from "../components/ui";
import { ago, cx, fmtDate } from "../lib/format";

export default function Captures() {
  const [nonce, setNonce] = useState(0);
  const { data, error } = useApi<{ threads: CapturedThread[]; log: CaptureLog[] }>(`captures?n=${nonce}`);
  const { data: ex } = useApi<Extraction>(`extraction?n=${nonce}`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <PageLoading />;
  const now = new Date().toISOString();
  const refresh = () => setNonce((n) => n + 1);

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="pb-10 pt-14">
        <div className="eyebrow mb-4">RWI · Reddit · Telegram</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Captures</h1>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
          RWI and Reddit pages you sent with the Chrome extension, and the Telegram channels you follow. Claude reads each thread and turns it into findings that feed the scores — only the conclusion and a link to the
          source are kept on the site.
        </p>
        {ex && !ex.configured && (
          <div className="mt-6 flex max-w-2xl items-start gap-3 rounded-xl border border-warn/30 bg-warn/[0.06] px-4 py-3 text-sm text-warn">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            Analysis is paused: add your Anthropic API key under Settings → Apps → Rep Index → Configuration.
          </div>
        )}
      </header>

      <div className="grid gap-12 lg:grid-cols-[1fr_380px]">
        <section>
          <SectionHead
            eyebrow={`${data.threads.length} threads${ex?.configured ? ` · ${ex.model}` : ""}`}
            title="Analysed sources"
            action={
              <button onClick={refresh} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-paper">
                <RotateCw size={13} /> Refresh
              </button>
            }
          />
          {!data.threads.length && <p className="text-sm text-muted">Nothing yet — open an RWI thread and click the extension’s button.</p>}
          <ul>
            {data.threads.map((t) => (
              <ThreadRow key={`${t.source_id}/${t.thread_id}`} t={t} now={now} busy={ex?.busy === t.thread_id} onQueued={refresh} />
            ))}
          </ul>
        </section>

        <aside className="space-y-10">
          <Setup />
          <div>
            <SectionHead eyebrow="Last 50" title="Log" />
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
        </aside>
      </div>
    </div>
  );
}

function ThreadRow({ t, now, busy, onQueued }: { t: CapturedThread; now: string; busy: boolean; onQueued: () => void }) {
  const builds: string[] = t.builds ? JSON.parse(t.builds) : [];
  const stale = !t.extracted_at || t.extracted_at < t.last_captured;
  const status = busy
    ? { label: "Analysing…", tone: "text-gold border-gold/40", icon: <Loader2 size={11} className="animate-spin" /> }
    : t.extract_error
      ? { label: "Failed", tone: "text-bad border-bad/30", icon: <AlertTriangle size={11} /> }
      : stale
        ? { label: "Queued", tone: "text-muted border-line", icon: null }
        : { label: "Analysed", tone: "text-good border-good/30", icon: <Sparkles size={11} /> };
  return (
    <li className="border-b border-line py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <a href={t.url} target="_blank" rel="noreferrer noopener" className="group min-w-0 flex-1">
          <span className="text-[16px] transition-colors group-hover:text-gold">{t.title}</span>
          <ExternalLink size={12} className="ml-1.5 inline text-muted" />
          <div className="mt-1 text-xs text-muted">
            {t.source_kind === "telegram" ? "Telegram channel" : t.forum}
            {t.source_kind === "forum" && ` · ${t.pages_captured}/${t.pages} pages`} · {t.posts} {t.source_kind === "telegram" ? "messages" : "posts"} · {t.photos_stored}{" "}
            photos · updated {ago(t.last_captured, now)}
            {t.extract_cost != null && ` · analysis $${t.extract_cost.toFixed(2)}`}
          </div>
        </a>
        <span className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider", status.tone)}>
          {status.icon}
          {status.label}
        </span>
      </div>
      {t.summary && !stale && <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-paper/85">{t.summary}</p>}
      {t.extract_error && <p className="mt-3 text-xs text-bad">{t.extract_error}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {builds.map((id) => (
          <Link key={id} to={`/build/${id}`} className="rounded-full border border-line px-2.5 py-0.5 font-mono text-[11px] text-muted hover:border-line-strong hover:text-paper">
            {id}
          </Link>
        ))}
        {!busy && (
          <button onClick={() => postJson(`captures/${encodeURIComponent(t.source_id)}/${encodeURIComponent(t.thread_id)}/extract`).then(onQueued)} className="ml-auto inline-flex items-center gap-1 text-xs text-muted hover:text-paper">
            <RotateCw size={11} /> Analyse again
          </button>
        )}
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
