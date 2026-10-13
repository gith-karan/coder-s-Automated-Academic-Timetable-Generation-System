import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError, setUnauthorizedHandler } from "@/lib/api";
import type { Me, Role } from "@/lib/types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  setMe: (m: Me | null) => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  can: (perm: string) => boolean;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/auth/me"));
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) console.error(e);
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    setUnauthorizedHandler(() => {
      setMe(null);
      qc.clear();
    });
  }, [refresh, qc]);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      qc.clear();
      setMe(null);
    }
  }, [qc]);

  const value = useMemo<AuthState>(
    () => ({
      me,
      loading,
      setMe,
      logout,
      refresh,
      can: (perm) => !!me && (me.permissions.includes("*") || me.permissions.includes(perm)),
      hasRole: (...roles) => !!me && roles.includes(me.role),
    }),
    [me, loading, logout, refresh],
  );
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
