import { useEffect, useState } from "react";

// Relative on purpose: resolves under the HA ingress prefix in production.
const BASE = "api/";

export type AspectScore = { score: number; lower: number; n: number; prev?: number | null };

export type Meta = {
  dataset: "demo" | "live";
  as_of: string;
  previous_as_of: string;
  counts: Record<"reference" | "factory" | "build" | "post" | "claim" | "photo" | "defect", number>;
  aspects: { id: string; label: string; weight: number }[];
  tiers: string[];
  families: string[];
  factories: { id: string; name: string; status: string }[];
  sources: { id: string; kind: string; name: string; trust: number }[];
};

export type Reference = {
  id: string;
  brand: string;
  family: string;
  name: string;
  size_mm: number;
  material: string;
  movement: string;
  year_intro: number;
  dial_color: string;
  bezel_color: string;
  metal_color: string;
};

export type BuildLite = {
  id: string;
  factory: string;
  factory_id: string;
  version: string;
  tier: Tier | null;
  rank: number | null;
  score: number | null;
  status: BuildStatus;
  claims?: number;
};

export type Tier = "S" | "A" | "B" | "C";
export type BuildStatus = "current" | "superseded" | "discontinued";

export type BuildSummary = {
  id: string;
  reference_id: string;
  factory_id: string;
  version: string;
  movement: string;
  released: string;
  status: BuildStatus;
  factory: string;
  factory_status: string;
  family: string;
  reference_name: string;
  dial_color: string;
  bezel_color: string;
  metal_color: string;
  tier: Tier | null;
  prev_tier: Tier | null;
  rank: number | null;
  controversy: number | null;
  score: number | null;
  lower: number | null;
  claims: number | null;
  open_defects: number;
  photos: number;
  price: number | null;
  ref_photo: string | null;
  qc_gl: number;
  qc_rl: number;
  qc_mixed: number;
  aspects: Record<string, AspectScore>;
};

export type QcVerdict = {
  verdict: "GL" | "RL" | "mixed";
  gl_votes: number;
  rl_votes: number;
  flaws: string;
  decided_at: string;
  thread_title: string;
  url: string | null;
  source: string;
};

export type Defect = {
  id: number;
  build_id: string;
  aspect: string;
  title: string;
  description: string | null;
  severity: 1 | 2 | 3;
  status: "open" | "fixed" | "disputed";
  fixed_in_version: string | null;
  reports: number;
  first_seen: string | null;
  last_seen: string | null;
};

export type Quote = {
  aspect: string;
  kind: "defect" | "praise" | "neutral";
  sentiment: number;
  evidence: string;
  quote: string;
  posted_at: string;
  url: string | null;
  thread_title: string;
  source: string;
  source_kind: string;
  handle: string | null;
  reputation: number | null;
};

export type Photo = { id: number; aspect: string; path: string; width: number; height: number };
export type RefPhoto = { id: number; view: string; path: string; credit: string | null; source_url: string | null };

export type BuildDetail = BuildSummary & {
  prev_score: number | null;
  reference: Reference;
  ref_photos: RefPhoto[];
  defects: Defect[];
  photo_list: Photo[];
  prices: { dealer: string; price: number; observed_at: string }[];
  quotes: Quote[];
  qc: QcVerdict[];
  qc_trend: { period: string; gl_rate: number; n: number }[];
  siblings: BuildLite[];
};

export type ReferenceListItem = Reference & { ref_photo: string | null; builds: BuildLite[]; claims: number };
export type ReferenceDetail = Reference & { aliases: string[]; photos: RefPhoto[]; builds: BuildSummary[] };

export type FactoryListItem = {
  id: string;
  name: string;
  status: string;
  founded: number | null;
  notes: string | null;
  aliases: string[];
  builds: { id: string; reference_id: string; family: string; version: string; tier: Tier | null; score: number | null; status: BuildStatus; open_defects: number }[];
  avg_score: number | null;
  references: string[];
  tier_counts: Record<Tier, number>;
};

export type FeedEvent = {
  id: number;
  kind: string;
  title: string;
  occurred_at: string;
  factory: string | null;
  factory_id: string | null;
  build_id: string | null;
  reference_id: string | null;
  version: string | null;
  source: string | null;
  source_kind: string | null;
};

export type FactoryDetail = Omit<FactoryListItem, "builds" | "avg_score" | "references" | "tier_counts"> & {
  builds: BuildSummary[];
  reputation: { period: string; score: number; n: number; defect_rate: number }[];
  events: FeedEvent[];
};

export type Feed = {
  events: FeedEvent[];
  defects: (Pick<Defect, "id" | "title" | "aspect" | "severity" | "status" | "build_id" | "reports" | "last_seen"> & {
    reference_id: string;
    version: string;
    factory: string;
  })[];
  movers: BuildSummary[];
  top: BuildSummary[];
};

export type Pivot = {
  rows: string[];
  cols: string[];
  cells: { r: string; c: string; v: number; n: number }[];
  row_totals: Record<string, { v: number; n: number }>;
  col_totals: Record<string, { v: number; n: number }>;
  grand: { v: number; n: number };
  dims: string[];
  measures: string[];
};

const cache = new Map<string, Promise<unknown>>();

export function fetchJson<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    const p = fetch(BASE + path).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${path}`);
      return r.json();
    });
    p.catch(() => cache.delete(path));
    cache.set(path, p);
  }
  return cache.get(path) as Promise<T>;
}

export function useApi<T>(path: string | null): { data: T | undefined; error: Error | undefined } {
  const [state, setState] = useState<{ path: string | null; data?: T; error?: Error }>({ path });
  useEffect(() => {
    if (!path) return;
    let live = true;
    fetchJson<T>(path).then(
      (data) => live && setState({ path, data }),
      (error: Error) => live && setState({ path, error }),
    );
    return () => {
      live = false;
    };
  }, [path]);
  // Don't show a previous path's data while the next one loads.
  return state.path === path ? { data: state.data, error: state.error } : { data: undefined, error: undefined };
}

export type CapturedThread = {
  thread_id: string;
  url: string;
  title: string;
  forum: string | null;
  pages: number;
  pages_captured: number;
  posts: number;
  photos: number;
  photos_stored: number;
  first_seen: string;
  last_captured: string;
};
export type CaptureLog = { id: number; thread_id: string; page: number; captured_at: string; posts: number; new_posts: number; photos: number; status: string };
export type CapturedPost = {
  id: number;
  external_id: string;
  number: number | null;
  page: number;
  posted_at: string;
  body: string;
  quotes: string | null;
  reactions: number | null;
  is_starter: number;
  url: string;
  handle: string;
  joined: string | null;
  post_count: number | null;
  reputation: number;
  banners: string | null;
  photos: { url: string; path: string | null }[];
};
