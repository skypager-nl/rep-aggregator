import { Check, Copy, Eye, EyeOff, Puzzle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { useApi, type CaptureLog, type CapturedThread } from "../api";
import { ErrorNote, PageLoading, SectionHead } from "../components/ui";
import { ago, fmtDate } from "../lib/format";

export default function Captures() {
  const { data, error } = useApi<{ threads: CapturedThread[]; log: CaptureLog[] }>("captures");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <PageLoading />;
  const now = new Date().toISOString();

  return (
    <div className="mx-auto max-w-[1360px] px-4 md:px-10">
      <header className="pb-10 pt-14">
        <div className="eyebrow mb-4">RWI · from your own browsing</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Captures</h1>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
          Threads you sent with the Chrome extension. Each capture is your own visit at reading pace — nothing here is crawled in the background.
        </p>
      </header>

      <div className="grid gap-12 lg:grid-cols-[1fr_380px]">
        <section>
          <SectionHead eyebrow={`${data.threads.length} threads`} title="Captured threads" />
          {!data.threads.length && <p className="text-sm text-muted">Nothing yet — open an RWI thread and click the extension’s button.</p>}
          <ul>
            {data.threads.map((t) => (
              <li key={t.thread_id} className="border-b border-line">
                <Link to={`/captures/${t.thread_id}`} className="group grid gap-2 py-4 sm:grid-cols-[1fr_auto] sm:items-center">
                  <div className="min-w-0">
                    <div className="truncate text-[16px] transition-colors group-hover:text-gold">{t.title}</div>
                    <div className="mt-1 text-xs text-muted">
                      {t.forum} · captured {ago(t.last_captured, now)}
                    </div>
                  </div>
                  <div className="flex items-center gap-5 text-xs text-muted">
                    <span className="flex items-center gap-2">
                      <span className="h-1 w-16 overflow-hidden rounded-full bg-white/10">
                        <span className="block h-full bg-gold" style={{ width: `${(100 * t.pages_captured) / t.pages}%` }} />
                      </span>
                      <span className="tnum">
                        {t.pages_captured}/{t.pages} pages
                      </span>
                    </span>
                    <span className="tnum">{t.posts} posts</span>
                    <span className="tnum">
                      {t.photos_stored}/{t.photos} photos
                    </span>
                  </div>
                </Link>
              </li>
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
                    +{l.new_posts} posts · +{l.photos} photos · {fmtDate(l.captured_at)}
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

function Setup() {
  const { data } = useApi<{ token: string; port: number }>("capture/setup");
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const endpoint = `http://homeassistant.local:${data?.port ?? 8766}`;
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
        <li>Open the extension’s options and paste the address and token below.</li>
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
