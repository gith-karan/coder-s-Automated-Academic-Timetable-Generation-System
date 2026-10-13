import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, qs } from "./api";
import type { Paged } from "./types";

type Params = Record<string, string | number | boolean | undefined | null>;

/** Paged list of a REST resource (rooms, faculty, …). */
export function useList<T>(resource: string, params: Params = {}) {
  return useQuery({
    queryKey: [resource, "list", params],
    queryFn: () => api.get<Paged<T>>(`/${resource}${qs(params)}`),
    placeholderData: keepPreviousData,
  });
}

/** All rows of a small reference resource (for selects & lookups). */
export function useAll<T>(resource: string, params: Params = {}, enabled = true) {
  return useQuery({
    queryKey: [resource, "all", params],
    queryFn: async () => (await api.get<Paged<T>>(`/${resource}${qs({ ...params, size: 200 })}`)).items,
    staleTime: 60_000,
    enabled,
  });
}

/** Create (no id) or update (with id) a resource; invalidates every query of that resource. */
export function useSave<T>(resource: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: unknown }) =>
      id ? api.patch<T>(`/${resource}/${id}`, body) : api.post<T>(`/${resource}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [resource] }),
    meta: { silent: true },
  });
}

export function useRemove(resource: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/${resource}/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [resource] }),
  });
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
