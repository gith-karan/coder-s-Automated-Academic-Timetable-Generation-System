import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, Eye, EyeOff, KeyRound, Lock, Mail, ShieldCheck, User } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/types";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";

type Mode = "password" | "otp-request" | "otp-verify";

export default function LoginPage() {
  const { me, setMe } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [mode, setMode] = useState<Mode>("password");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [remember, setRemember] = useState(false);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  if (me) return <Navigate to={loc.state?.from ?? "/"} replace />;

  const done = (m: Me) => {
    setMe(m);
    navigate(loc.state?.from ?? "/", { replace: true });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "password") {
        done(await api.post<Me>("/auth/login", { identifier, password, remember_me: remember }));
      } else if (mode === "otp-request") {
        await api.post("/auth/otp/request", { identifier });
        setInfo("If an account exists for this email, a 6-digit code has been sent. It expires in 5 minutes.");
        setMode("otp-verify");
      } else {
        done(await api.post<Me>("/auth/otp/verify", { identifier, code, remember_me: remember }));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach the server. Check your connection.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-side lg:flex lg:flex-col lg:items-center lg:justify-center">
        <div
          aria-hidden
          className="absolute inset-0 opacity-[.08]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 20%, #fff 1px, transparent 1px), radial-gradient(circle at 80% 60%, #fff 1px, transparent 1px)",
            backgroundSize: "28px 28px, 36px 36px",
          }}
        />
        <div aria-hidden className="absolute -right-32 -top-32 size-96 rounded-full bg-brand/30 blur-3xl" />
        <div aria-hidden className="absolute -bottom-40 -left-24 size-[28rem] rounded-full bg-gold/20 blur-3xl" />
        <div className="relative z-10 flex max-w-md flex-col items-center px-10 text-center">
          <div className="rounded-3xl bg-white/95 p-5 shadow-2xl">
            <img src="/brand/nfsu-crest.png" alt="National Forensic Sciences University emblem" className="h-44 w-auto" />
          </div>
          <h1 className="mt-8 font-serif text-3xl font-semibold leading-tight text-white">National Forensic Sciences University</h1>
          <p className="mt-3 text-sm tracking-wide text-gold">Knowledge&nbsp;&nbsp;|&nbsp;&nbsp;Wisdom&nbsp;&nbsp;|&nbsp;&nbsp;Fulfilment</p>
          <p className="mt-1 text-xs text-side-text/70">An Institution of National Importance · Ministry of Home Affairs, Government of India</p>
          <div className="mt-10 grid w-full grid-cols-3 gap-3 text-left">
            {[
              ["Automated", "CP-SAT optimisation engine"],
              ["Conflict-free", "Every rule verified twice"],
              ["Secure", "Audited, role-based access"],
            ].map(([t, d]) => (
              <div key={t} className="rounded-xl border border-white/10 bg-white/5 p-3">
                <p className="text-sm font-semibold text-white">{t}</p>
                <p className="mt-0.5 text-[11px] leading-snug text-side-text/70">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Form */}
      <div className="flex flex-col items-center justify-center bg-surface px-6 py-10">
        <div className="w-full max-w-sm">
          <img src="/brand/nfsu-logo.png" alt="National Forensic Sciences University" className="mb-8 h-14 w-auto lg:hidden" />
          <h2 className="text-2xl font-semibold tracking-tight">Academic Timetable System</h2>
          <p className="mt-1 text-sm text-muted">Automated · Efficient · Conflict-free</p>

          <form onSubmit={submit} className="mt-8 space-y-4" noValidate>
            {mode === "otp-verify" && info && <p className="rounded-lg bg-info/10 px-3 py-2 text-xs text-info">{info}</p>}
            <Field label="Email or username" htmlFor="identifier">
              <Input
                id="identifier"
                icon={<User />}
                autoComplete="username"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="you@nfsu.ac.in"
                required
                disabled={mode === "otp-verify"}
              />
            </Field>

            {mode === "password" && (
              <Field label="Password" htmlFor="password">
                <Input
                  id="password"
                  icon={<Lock />}
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  trailing={
                    <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="grid size-7 place-items-center rounded-md text-muted hover:text-ink">
                      {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  }
                />
              </Field>
            )}

            {mode === "otp-verify" && (
              <Field label="6-digit code" htmlFor="code">
                <Input
                  id="code"
                  icon={<KeyRound />}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  className="tracking-[.4em]"
                />
              </Field>
            )}

            {mode !== "otp-request" && (
              <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="size-4 accent-[var(--brand)]" />
                Remember me on this device
              </label>
            )}

            {error && <p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}

            <Button type="submit" size="lg" className="w-full" loading={busy}>
              {mode === "password" ? "Sign in" : mode === "otp-request" ? "Send code" : "Verify & sign in"}
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3 text-xs text-muted">
            <span className="h-px flex-1 bg-line" /> OR <span className="h-px flex-1 bg-line" />
          </div>

          {mode === "password" ? (
            <Button variant="secondary" size="lg" className="w-full" icon={<Mail className="size-4" />} onClick={() => { setMode("otp-request"); setError(null); }}>
              Sign in with email code (OTP)
            </Button>
          ) : (
            <Button variant="secondary" size="lg" className="w-full" icon={<ArrowLeft className="size-4" />} onClick={() => { setMode("password"); setError(null); setCode(""); }}>
              Back to password sign-in
            </Button>
          )}

          <p className="mt-8 flex items-center justify-center gap-1.5 text-[11px] text-muted">
            <ShieldCheck className="size-3.5" /> Protected session · All activity is audited
          </p>
          <p className="mt-2 text-center text-[11px] text-muted">© {new Date().getFullYear()} National Forensic Sciences University</p>
        </div>
      </div>
    </div>
  );
}
