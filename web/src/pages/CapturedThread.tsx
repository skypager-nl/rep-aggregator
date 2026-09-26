import { ExternalLink, Quote } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { useApi, type CapturedPost } from "../api";
import { Chip, ErrorNote, PageLoading } from "../components/ui";
import { cx, fmtDate } from "../lib/format";

type ThreadDetail = { external_id: string; url: string; title: string; forum: string | null; pages: number; posts: CapturedPost[] };

export default function CapturedThread() {
  const { id } = useParams();
  const { data: t, error } = useApi<ThreadDetail>(`captures/${id}`);
  const [photosOnly, setPhotosOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  if (error) return <ErrorNote error={error} />;
  if (!t) return <PageLoading />;
  const posts = t.posts.filter((p) => !photosOnly || p.photos.length);
  const captured = new Set(t.posts.map((p) => p.page));

  return (
    <div className="mx-auto max-w-[980px] px-4 md:px-10">
      <header className="pb-8 pt-12">
        <Link to="/captures" className="eyebrow hover:text-paper">
          Captures · {t.forum}
        </Link>
        <h1 className="mt-4 font-display text-[40px] leading-[1.02] tracking-tight md:text-[56px]">{t.title}</h1>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-muted">
          <span>
            {t.posts.length} posts · pages captured{" "}
            {Array.from({ length: t.pages }, (_, i) => (
              <span key={i} className={cx("ml-1 inline-block h-2 w-2 rounded-full", captured.has(i + 1) ? "bg-gold" : "bg-white/15")} title={`page ${i + 1}`} />
            ))}
          </span>
          <a href={t.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 hover:text-paper">
            open on RWI <ExternalLink size={12} />
          </a>
          <Chip active={photosOnly} onClick={() => setPhotosOnly((v) => !v)}>
            With photos only
          </Chip>
        </div>
      </header>

      <ol className="space-y-4">
        {posts.map((p) => {
          const quotes: { author: string | null; text: string }[] = p.quotes ? JSON.parse(p.quotes) : [];
          const long = p.body.length > 900;
          const expanded = open === p.external_id;
          return (
            <li key={p.id} className={cx("rounded-2xl border bg-panel p-5", p.is_starter ? "border-gold/30" : "border-line")}>
              <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-medium">{p.handle}</span>
                <span className="font-mono text-[11px] text-gold" title="Reputation weight">
                  ×{p.reputation?.toFixed(2)}
                </span>
                <span className="text-xs text-faint">
                  {p.post_count?.toLocaleString()} msgs · joined {fmtDate(p.joined, "month")}
                </span>
                <span className="ml-auto font-mono text-[11px] text-faint">
                  #{p.number} · {fmtDate(p.posted_at)}
                </span>
              </div>
              {quotes.map((q, i) => (
                <div key={i} className="mb-3 border-l-2 border-line-strong pl-3 text-[13px] text-muted">
                  <Quote size={11} className="mr-1 inline" /> {q.author}: {q.text.slice(0, 220)}
                  {q.text.length > 220 && "…"}
                </div>
              ))}
              <div className={cx("whitespace-pre-line text-[14.5px] leading-relaxed", long && !expanded && "line-clamp-[12]")}>{p.body}</div>
              {long && (
                <button onClick={() => setOpen(expanded ? null : p.external_id)} className="mt-2 text-xs text-gold hover:underline">
                  {expanded ? "Show less" : "Show full post"}
                </button>
              )}
              {p.photos.length > 0 && (
                <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-5">
                  {p.photos.map((ph) =>
                    ph.path ? (
                      <a key={ph.url} href={`photos/${ph.path}`} target="_blank" rel="noreferrer noopener" className="aspect-square overflow-hidden rounded-lg bg-ink">
                        <img src={`photos/${ph.path}`} alt="" loading="lazy" className="h-full w-full object-cover transition-transform duration-500 hover:scale-105" />
                      </a>
                    ) : (
                      <a key={ph.url} href={ph.url} target="_blank" rel="noreferrer noopener" title="Not stored yet — re-capture this page" className="grid aspect-square place-items-center rounded-lg border border-dashed border-line text-[10px] text-faint">
                        not stored
                      </a>
                    ),
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
