import { useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";

export function PasswordForm({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next !== confirm) return setError("The new passwords do not match.");
    setBusy(true);
    try {
      await api.post("/auth/password", { current_password: current, new_password: next });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Current password"><Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
      <Field label="New password" hint="At least 12 characters, using three of: lowercase, uppercase, digits, symbols.">
        <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
      </Field>
      <Field label="Confirm new password"><Input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
      {error && <p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}
      <Button type="submit" loading={busy} className="w-full">Update password</Button>
    </form>
  );
}

/** Shown after signing in with a temporary password: nothing else is reachable until it is changed. */
export default function ChangePasswordGate() {
  const { refresh, logout } = useAuth();
  return (
    <div className="grid min-h-full place-items-center bg-bg px-4">
      <Card className="w-full max-w-md">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-xl bg-brand/10 text-brand"><KeyRound className="size-5" /></div>
          <div>
            <h1 className="text-lg font-semibold">Set a new password</h1>
            <p className="text-sm text-muted">You signed in with a temporary password. Choose your own to continue.</p>
          </div>
        </div>
        <PasswordForm onDone={() => void refresh()} />
        <button onClick={() => void logout()} className="mt-4 w-full text-center text-xs text-muted hover:text-ink">Sign out</button>
      </Card>
    </div>
  );
}
