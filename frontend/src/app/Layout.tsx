import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell, CheckCheck, ChevronDown, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Search, Sun, User,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Notification } from "@/lib/types";
import { cn, initials, ROLE_LABEL, timeAgo } from "@/lib/utils";
import { IconButton } from "@/components/ui/button";
import { MenuContent, MenuItem, MenuRoot, MenuSeparator, MenuTrigger } from "@/components/ui/overlay";
import { useAuth } from "./auth";
import { navFor, SECTION_LABEL, type NavItem } from "./nav";
import { usePrefs } from "./preferences";

export function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <img src="/brand/nfsu-shield.png" alt="NFSU emblem" className="size-10 shrink-0 object-contain" />
      {!compact && (
        <div className="leading-tight">
          <p className="text-[15px] font-bold tracking-wide text-white">NFSU</p>
          <p className="text-[11px] text-side-text/80">Timetable System</p>
        </div>
      )}
    </div>
  );
}

function Sidebar({ compact, onNavigate }: { compact: boolean; onNavigate?: () => void }) {
  const { me } = useAuth();
  const items = navFor(me);
  const sections = useMemo(() => {
    const out: [NavItem["section"], NavItem[]][] = [];
    for (const it of items) {
      const last = out[out.length - 1];
      if (last && last[0] === it.section) last[1].push(it);
      else out.push([it.section, [it]]);
    }
    return out;
  }, [items]);

  return (
    <aside className={cn("flex h-full flex-col bg-side text-side-text transition-[width] duration-200", compact ? "w-[76px]" : "w-64")}>
      <div className={cn("flex h-16 items-center border-b border-white/10", compact ? "justify-center px-2" : "px-5")}>
        <Brand compact={compact} />
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin" aria-label="Main">
        {sections.map(([section, list]) => (
          <div key={section} className="mb-3">
            {SECTION_LABEL[section] && !compact && (
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[.14em] text-side-text/50">{SECTION_LABEL[section]}</p>
            )}
            {list.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.to === "/"}
                onClick={onNavigate}
                title={compact ? it.label : undefined}
                className={({ isActive }) =>
                  cn(
                    "group relative mb-0.5 flex items-center gap-3 rounded-[10px] px-3 py-2 text-[13.5px] font-medium transition-colors",
                    compact && "justify-center px-0",
                    isActive ? "bg-brand text-white shadow-sm" : "hover:bg-white/8 hover:text-white",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && <span className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-gold" />}
                    <it.icon className="size-[18px] shrink-0" />
                    {!compact && <span className="truncate">{it.label}</span>}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      {!compact && <p className="border-t border-white/10 px-5 py-3 text-[10px] text-side-text/50">National Forensic Sciences University</p>}
    </aside>
  );
}

function NotificationBell() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ items: Notification[]; unread: number }>("/notifications?limit=15"),
    refetchInterval: 30_000,
  });
  const readAll = useMutation({
    mutationFn: () => api.post("/notifications/read-all"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const open = async (n: Notification) => {
    if (!n.read_at) await api.post(`/notifications/${n.id}/read`).catch(() => undefined);
    qc.invalidateQueries({ queryKey: ["notifications"] });
    if (n.link) navigate(n.link);
  };
  const unread = data?.unread ?? 0;
  return (
    <MenuRoot>
      <MenuTrigger asChild>
        <button aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} className="relative grid size-9 place-items-center rounded-[10px] text-muted hover:bg-line/50 hover:text-ink">
          <Bell className="size-[18px]" />
          {unread > 0 && (
            <span className="absolute right-1 top-1 grid min-w-4 place-items-center rounded-full bg-brand px-1 text-[10px] font-bold leading-4 text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </button>
      </MenuTrigger>
      <MenuContent>
        <div className="w-[340px]">
          <div className="flex items-center justify-between px-3 py-2">
            <p className="text-sm font-semibold">Notifications</p>
            {unread > 0 && (
              <button onClick={() => readAll.mutate()} className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline">
                <CheckCheck className="size-3.5" /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto scrollbar-thin">
            {data?.items.length === 0 && <p className="px-3 py-8 text-center text-sm text-muted">You're all caught up.</p>}
            {data?.items.map((n) => (
              <MenuItem key={n.id} onSelect={() => void open(n)}>
                <div className="flex w-full gap-2.5">
                  <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-brand")} />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{n.title}</p>
                    <p className="line-clamp-2 text-xs text-muted">{n.body}</p>
                    <p className="mt-0.5 text-[11px] text-muted/80">{timeAgo(n.created_at)}</p>
                  </div>
                </div>
              </MenuItem>
            ))}
          </div>
        </div>
      </MenuContent>
    </MenuRoot>
  );
}

function GlobalSearch() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const items = navFor(me).filter((n) => q && n.label.toLowerCase().includes(q.toLowerCase()));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="relative hidden w-full max-w-sm md:block">
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
      <input
        ref={ref}
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => { if (e.key === "Enter" && items[0]) { navigate(items[0].to); setQ(""); } }}
        placeholder="Search pages…"
        aria-label="Search pages"
        className="h-9 w-full rounded-[10px] border border-line bg-surface-2 pl-9 pr-14 text-sm placeholder:text-muted/70 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
      />
      <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-line px-1.5 text-[10px] text-muted">Ctrl K</kbd>
      {open && items.length > 0 && (
        <div className="absolute z-40 mt-1 w-full rounded-xl border border-line bg-surface p-1 shadow-xl">
          {items.map((it) => (
            <button key={it.to} onMouseDown={() => { navigate(it.to); setQ(""); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-line/60">
              <it.icon className="size-4 text-muted" /> {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AppLayout() {
  const { me, logout } = useAuth();
  const { prefs, update, isDark } = usePrefs();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className="flex h-full">
      <div className="no-print hidden lg:block">
        <Sidebar compact={prefs.compact_sidebar} />
      </div>
      {mobileOpen && (
        <div className="no-print fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <div className="relative h-full w-64 animate-fade-in">
            <Sidebar compact={false} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur md:px-6">
          <IconButton label="Open menu" className="lg:hidden" onClick={() => setMobileOpen(true)}>
            <Menu className="size-5" />
          </IconButton>
          <IconButton
            label={prefs.compact_sidebar ? "Expand sidebar" : "Collapse sidebar"}
            className="hidden lg:inline-flex"
            onClick={() => update({ compact_sidebar: !prefs.compact_sidebar })}
          >
            {prefs.compact_sidebar ? <PanelLeftOpen className="size-[18px]" /> : <PanelLeftClose className="size-[18px]" />}
          </IconButton>
          <GlobalSearch />
          <div className="ml-auto flex items-center gap-1">
            <NotificationBell />
            <IconButton label={isDark ? "Switch to light mode" : "Switch to dark mode"} onClick={() => update({ theme_mode: isDark ? "light" : "dark" })}>
              {isDark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
            </IconButton>
            {me && (
              <MenuRoot>
                <MenuTrigger asChild>
                  <button className="ml-1 flex items-center gap-2 rounded-[10px] py-1 pl-1 pr-2 hover:bg-line/50" aria-label="Account menu">
                    <span className="grid size-8 place-items-center rounded-full bg-brand text-xs font-bold text-white">{initials(me.full_name)}</span>
                    <span className="hidden text-left leading-tight sm:block">
                      <span className="block max-w-36 truncate text-sm font-medium">{me.full_name}</span>
                      <span className="block text-[11px] text-muted">{ROLE_LABEL[me.role]}</span>
                    </span>
                    <ChevronDown className="size-4 text-muted" />
                  </button>
                </MenuTrigger>
                <MenuContent>
                  <div className="px-3 py-2">
                    <p className="text-sm font-semibold">{me.full_name}</p>
                    <p className="text-xs text-muted">{me.email}</p>
                  </div>
                  <MenuSeparator />
                  <MenuItem icon={<User className="size-4" />} onSelect={() => navigate("/profile")}>Profile</MenuItem>
                  <MenuItem icon={<LogOut className="size-4" />} danger onSelect={() => void logout().then(() => navigate("/login"))}>
                    Sign out
                  </MenuItem>
                </MenuContent>
              </MenuRoot>
            )}
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-6 md:px-8 scrollbar-thin">
          <div key={location.pathname} className="mx-auto max-w-[1400px] animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
