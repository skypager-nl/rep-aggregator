import { AlertTriangle, LogOut, RefreshCw, Send } from "lucide-react";
import { useState } from "react";
import { postJson, useApi, type TgChannel, type TgStatus } from "../api";
import { ErrorNote, PageLoading, SectionHead } from "../components/ui";
import { ago, cx } from "../lib/format";

export default function Telegram() {
  const [nonce, setNonce] = useState(0);
  const { data, error } = useApi<TgStatus>(`telegram?n=${nonce}`);
  const [msg, setMsg] = useState<{ text: string; bad?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <PageLoading />;

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    try {
      await fn();
      if (ok) setMsg({ text: ok });
      else setMsg(null);
    } catch (e) {
      setMsg({ text: (e as Error).message, bad: true });
    } finally {
      setBusy(false);
      setNonce((n) => n + 1);
    }
  };
  const followed = data.channels.filter((c) => c.follow);

  return (
    <div className="mx-auto max-w-[1100px] px-4 md:px-10">
      <header className="pb-8 pt-14">
        <div className="eyebrow mb-4">Dealer channels</div>
        <h1 className="font-display text-[52px] leading-none tracking-tight md:text-[72px]">Telegram</h1>
        <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-muted">
          Reads the dealer channels you follow through Telegram’s official API, with your own account — never group chats or private messages. New messages are
          checked every 30 minutes; Claude turns them into releases, restocks, prices and the occasional quality note.
        </p>
      </header>

      {msg && (
        <div className={cx("mb-6 rounded-xl border px-4 py-2.5 text-sm", msg.bad ? "border-bad/30 text-bad" : "border-good/30 text-good")}>{msg.text}</div>
      )}

      {!data.configured ? (
        <Card title="Set up">
          <ol className="list-decimal space-y-2 pl-5 text-[14px] text-muted">
            <li>
              Open <span className="text-paper">my.telegram.org</span> → log in → <span className="text-paper">API development tools</span> → create an app (any name).
            </li>
            <li>
              Copy the <span className="font-mono text-paper">api_id</span> and <span className="font-mono text-paper">api_hash</span> into Settings → Apps → Rep Index →
              Configuration, then Save and Restart.
            </li>
            <li>Come back here to log in with your phone number.</li>
          </ol>
        </Card>
      ) : !data.authorized ? (
        <Login step={data.step} busy={busy} act={act} error={data.error} />
      ) : (
        <>
          <div className="mb-10 flex flex-wrap items-center gap-3">
            <span className="text-sm text-muted">
              Logged in as <span className="text-paper">{data.account}</span>
            </span>
            <button disabled={busy} onClick={() => act(() => postJson("telegram/refresh"), "Channel list updated.")} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3 py-1.5 text-sm hover:bg-white/5">
              <RefreshCw size={13} className={cx(busy && "animate-spin")} /> Refresh channel list
            </button>
            <button disabled={busy || !followed.length} onClick={() => act(() => postJson("telegram/poll"), "Checking followed channels now — refresh in a minute.")} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3 py-1.5 text-sm hover:bg-white/5 disabled:opacity-40">
              <Send size={13} /> Check now
            </button>
            <button onClick={() => confirm("Log out of Telegram on the Rep Index?") && act(() => postJson("telegram/logout"), "Logged out.")} className="ml-auto inline-flex items-center gap-1.5 text-sm text-muted hover:text-bad">
              <LogOut size={13} /> Log out
            </button>
          </div>

          <SectionHead eyebrow={`${followed.length} followed · ${data.channels.length} channels you’ve joined`} title="Channels" />
          {!data.channels.length && <p className="text-sm text-muted">No channels yet — click “Refresh channel list”. Only broadcast channels are listed.</p>}
          <ul>
            {data.channels.map((c) => (
              <ChannelRow key={c.id} c={c} onToggle={(follow) => act(() => postJson(`telegram/channels/${c.id}`, { follow }))} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Login({ step, busy, act, error }: { step: string | null; busy: boolean; act: (fn: () => Promise<unknown>, ok?: string) => void; error?: string }) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const input = "w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm outline-none focus:border-line-strong";
  const button = "rounded-full bg-paper px-5 py-2 text-sm font-medium text-ink disabled:opacity-40";
  return (
    <Card title="Log in to Telegram">
      {error && (
        <p className="mb-4 flex items-center gap-2 text-sm text-bad">
          <AlertTriangle size={14} /> {error}
        </p>
      )}
      {step === "password" ? (
        <form onSubmit={(e) => (e.preventDefault(), act(() => postJson("telegram/password", { password }), "Logged in."))} className="space-y-3">
          <p className="text-sm text-muted">Your account has two-step verification. Enter your Telegram cloud password.</p>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={input} />
          <button disabled={busy || !password} className={button}>
            Log in
          </button>
        </form>
      ) : step === "code" ? (
        <form onSubmit={(e) => (e.preventDefault(), act(() => postJson("telegram/code", { code }), "Logged in."))} className="space-y-3">
          <p className="text-sm text-muted">Telegram sent a login code to your Telegram app. Enter it here.</p>
          <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} className={input} />
          <button disabled={busy || !code} className={button}>
            Sign in
          </button>
        </form>
      ) : (
        <form onSubmit={(e) => (e.preventDefault(), act(() => postJson("telegram/login", { phone })))} className="space-y-3">
          <p className="text-sm text-muted">Your phone number in international format. Telegram will send a login code to your Telegram app.</p>
          <input type="tel" autoComplete="tel" placeholder="+31 6 …" value={phone} onChange={(e) => setPhone(e.target.value)} className={input} />
          <button disabled={busy || phone.length < 8} className={button}>
            Send code
          </button>
        </form>
      )}
    </Card>
  );
}

function ChannelRow({ c, onToggle }: { c: TgChannel; onToggle: (follow: boolean) => void }) {
  const now = new Date().toISOString();
  return (
    <li className="border-b border-line py-4">
      <div className="flex items-start gap-4">
        <button
          role="switch"
          aria-checked={!!c.follow}
          onClick={() => onToggle(!c.follow)}
          className={cx("mt-1 h-5 w-9 shrink-0 rounded-full p-0.5 transition-colors", c.follow ? "bg-gold" : "bg-white/15")}
          title={c.follow ? "Following — click to stop" : "Follow this channel"}
        >
          <span className={cx("block h-4 w-4 rounded-full bg-ink transition-transform", !!c.follow && "translate-x-4")} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="text-[15.5px]">
            {c.title}
            {c.username && <span className="ml-2 font-mono text-xs text-faint">@{c.username}</span>}
          </div>
          {c.follow ? (
            <div className="mt-1 text-xs text-muted">
              {c.messages} messages · {c.events} events · {c.prices} prices · {c.findings} quality notes
              {c.last_polled && ` · checked ${ago(c.last_polled, now)}`}
              {!c.backfill_done && c.messages > 0 && " · backfilling history"}
              {c.extract_cost != null && ` · analysis $${c.extract_cost.toFixed(2)}`}
            </div>
          ) : null}
          {c.follow && c.summary ? <p className="mt-2 max-w-3xl text-[13.5px] leading-relaxed text-paper/80">{c.summary}</p> : null}
          {(c.error || c.extract_error) && <p className="mt-1 text-xs text-bad">{c.error || c.extract_error}</p>}
        </div>
      </div>
    </li>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="max-w-xl rounded-2xl border border-line bg-panel p-6">
      <div className="mb-4 font-display text-2xl">{title}</div>
      {children}
    </div>
  );
}
