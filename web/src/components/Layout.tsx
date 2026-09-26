import { Menu, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useApi, type Meta } from "../api";
import { useCompare } from "../lib/compare";
import { cx, fmtDate, fmtInt } from "../lib/format";

const NAV = [
  { to: "/tiers", label: "Tiers" },
  { to: "/factories", label: "Factories" },
  { to: "/explore", label: "Explore" },
  { to: "/pivot", label: "Pivot" },
  { to: "/compare", label: "Compare" },
  { to: "/captures", label: "Captures" },
  { to: "/telegram", label: "Telegram" },
];

export default function Layout() {
  const { data: meta } = useApi<Meta>("meta");
  const compared = useCompare();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0 });
    setOpen(false);
  }, [pathname]);

  return (
    <div className="grain min-h-dvh">
      {meta?.dataset === "demo" && (
        <div className="border-b border-warn/20 bg-warn/[0.07] px-4 py-1.5 text-center font-mono text-[10.5px] uppercase tracking-[0.16em] text-warn/90">
          Demo data — builds, scores, defects and prices are synthetic until the collectors run
        </div>
      )}
      <header className="sticky top-0 z-40 border-b border-line bg-ink/75 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1360px] items-center justify-between px-4 md:px-10">
          <Link to="/" className="flex items-baseline gap-2.5">
            <span className="font-display text-[26px] leading-none tracking-tight">The Rep Index</span>
            <span className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-gold sm:inline">Rolex</span>
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  cx("relative rounded-full px-3.5 py-1.5 text-[13.5px] transition-colors", isActive ? "text-paper" : "text-muted hover:text-paper")
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-full bg-white/[0.07]" transition={{ type: "spring", bounce: 0.2, duration: 0.5 }} />}
                    <span className="relative">
                      {n.label}
                      {n.to === "/compare" && compared.length > 0 && <span className="ml-1.5 font-mono text-[10.5px] text-gold">{compared.length}</span>}
                      {n.to === "/factories" && (meta?.factories_to_review ?? 0) > 0 && <span className="ml-1.5 inline-block h-1.5 w-1.5 -translate-y-1.5 rounded-full bg-warn" title="Factories to review" />}
                    </span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
          <button className="p-2 text-muted md:hidden" onClick={() => setOpen((o) => !o)} aria-label="Menu">
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
        <AnimatePresence>
          {open && (
            <motion.nav
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-line md:hidden"
            >
              {NAV.map((n) => (
                <NavLink key={n.to} to={n.to} className={({ isActive }) => cx("block px-5 py-3 font-display text-2xl", isActive ? "text-paper" : "text-muted")}>
                  {n.label}
                </NavLink>
              ))}
            </motion.nav>
          )}
        </AnimatePresence>
      </header>

      <main>
        <AnimatePresence mode="wait">
          <motion.div key={pathname} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="mt-24 border-t border-line">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-3 px-4 py-8 text-[12px] text-faint md:flex-row md:items-center md:justify-between md:px-10">
          <span>
            Scores as of {fmtDate(meta?.as_of, "long")} · {fmtInt(meta?.counts.claim)} claims from {fmtInt(meta?.counts.post)} posts across {meta?.sources.length ?? "—"} sources
          </span>
          <span>Tiers use the conservative lower bound — consensus beats hype.</span>
        </div>
      </footer>
    </div>
  );
}
