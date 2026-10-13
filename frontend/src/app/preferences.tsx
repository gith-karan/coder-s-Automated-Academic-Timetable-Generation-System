import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Me, Preferences } from "@/lib/types";
import { TooltipsEnabled } from "@/components/ui/overlay";
import { useAuth } from "./auth";

export const DEFAULT_PREFS: Preferences = {
  theme_mode: "system",
  color_theme: "nfsu",
  compact_sidebar: false,
  show_tooltips: true,
  animations: true,
};

const KEY = "nfsu.prefs";

interface PrefsState {
  prefs: Preferences;
  update: (p: Partial<Preferences>) => void;
  isDark: boolean;
}

const PrefsCtx = createContext<PrefsState | null>(null);

function load(): Preferences {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return DEFAULT_PREFS;
  }
}

/** User preferences: applied instantly, cached locally (works before login) and synced to the profile. */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const { me, setMe } = useAuth();
  const [prefs, setPrefs] = useState<Preferences>(load);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  // Adopt server-side preferences after sign-in (another device may have changed them).
  useEffect(() => {
    if (me?.preferences && Object.keys(me.preferences).length) {
      setPrefs((p) => ({ ...p, ...me.preferences }));
    }
  }, [me?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const isDark = prefs.theme_mode === "dark" || (prefs.theme_mode === "system" && systemDark);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", isDark);
    root.dataset.theme = prefs.color_theme;
    root.classList.toggle("no-anim", !prefs.animations);
    localStorage.setItem(KEY, JSON.stringify(prefs));
  }, [prefs, isDark]);

  const update = useCallback(
    (p: Partial<Preferences>) => {
      setPrefs((cur) => {
        const next = { ...cur, ...p };
        if (me) api.put<Me>("/auth/me/preferences", next).then(setMe).catch(() => undefined);
        return next;
      });
    },
    [me, setMe],
  );

  const value = useMemo(() => ({ prefs, update, isDark }), [prefs, update, isDark]);
  return (
    <PrefsCtx.Provider value={value}>
      <TooltipsEnabled.Provider value={prefs.show_tooltips}>{children}</TooltipsEnabled.Provider>
    </PrefsCtx.Provider>
  );
}

export function usePrefs() {
  const ctx = useContext(PrefsCtx);
  if (!ctx) throw new Error("usePrefs outside PreferencesProvider");
  return ctx;
}
