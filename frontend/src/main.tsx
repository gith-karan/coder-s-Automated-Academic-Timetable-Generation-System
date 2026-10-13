import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster, toast } from "sonner";
import { ApiError } from "@/lib/api";
import { TooltipProvider } from "@/components/ui/overlay";
import { AuthProvider } from "@/app/auth";
import { PreferencesProvider, usePrefs } from "@/app/preferences";
import { router } from "@/app/router";
import "@/styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
  // Every failed mutation shows the server's human-readable message (unless the caller handles it).
  mutationCache: new MutationCache({
    onError: (err, _v, _c, mutation) => {
      if (mutation.options.meta?.silent) return;
      toast.error(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    },
  }),
});

declare module "@tanstack/react-query" {
  interface Register {
    mutationMeta: { silent?: boolean };
  }
}

function ThemedToaster() {
  const { isDark } = usePrefs();
  return <Toaster position="top-right" richColors closeButton theme={isDark ? "dark" : "light"} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <PreferencesProvider>
          <TooltipProvider>
            <RouterProvider router={router} />
            <ThemedToaster />
          </TooltipProvider>
        </PreferencesProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
