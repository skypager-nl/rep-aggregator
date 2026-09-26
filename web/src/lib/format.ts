export const fmtScore = (v: number | null | undefined, d = 1) => (v == null ? "—" : v.toFixed(d));
export const fmtPrice = (v: number | null | undefined) => (v == null ? "—" : `$${Math.round(v)}`);
export const fmtInt = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString("en-US"));

export function fmtDate(iso: string | null | undefined, style: "short" | "long" | "month" = "short") {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  if (style === "month") return d.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
  if (style === "long") return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
}

export function ago(iso: string, now: string) {
  const days = Math.round((Date.parse(now) - Date.parse(iso.slice(0, 10))) / 864e5);
  if (days < 1) return "today";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.round(days / 30)}mo ago`;
  return `${(days / 365).toFixed(1)}y ago`;
}

export const TIER_ORDER = ["S", "A", "B", "C"] as const;
export const TIER_COLOR: Record<string, string> = {
  S: "var(--color-tier-s)",
  A: "var(--color-tier-a)",
  B: "var(--color-tier-b)",
  C: "var(--color-tier-c)",
};
export const TIER_NAME: Record<string, string> = { S: "Reference grade", A: "Excellent", B: "Solid", C: "Compromised" };

/** 0..10 score -> colour on a muted red → sand → green scale. */
export function scoreColor(v: number | null | undefined, alpha = 1) {
  if (v == null) return "transparent";
  const t = Math.max(0, Math.min(1, (v - 5) / 4));
  const stops = [
    [217, 130, 111],
    [216, 178, 94],
    [127, 184, 154],
  ];
  const [a, b, k] = t < 0.5 ? [stops[0], stops[1], t * 2] : [stops[1], stops[2], (t - 0.5) * 2];
  const c = a.map((x, i) => Math.round(x + (b[i] - x) * k));
  return `rgb(${c[0]} ${c[1]} ${c[2]} / ${alpha})`;
}

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export const GUIDE_RANK = ["", "Best factory", "2nd best", "3rd best"];
export const GUIDE_QUALITY: Record<string, string> = { nwbig: "NWBIG", super: "Super Rep" };
export function guideLabel(rank: number | null | undefined, quality: string | null | undefined) {
  if (!rank) return null;
  return `${GUIDE_RANK[rank]}${quality ? ` · ${GUIDE_QUALITY[quality]}` : ""}`;
}

/** Version label for display: only a known release number (V2, V3...). Anything else -- "unspecified",
 *  or descriptors like "Free Sprung" / "Tungsten" -- is hidden. */
export function ver(v: string | null | undefined): string {
  const m = (v || "").match(/^V\d+(?:\.\d+)?\b/i);
  return m ? m[0].toUpperCase() : "";
}
