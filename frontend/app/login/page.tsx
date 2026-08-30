"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const account = await signIn(email, password);
      router.push(account.onboarding_completed_at ? "/dashboard" : "/onboarding");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  };

  const startOAuth = async () => {
    setError("");
    try {
      const { authorization_url, state } = await api.oauthAuthorize("google");
      window.sessionStorage.setItem("jab.oauth_state", state);
      window.location.href = authorization_url;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start Google sign-in");
    }
  };

  return (
    <div className="page narrow" style={{ paddingTop: "3rem" }}>
      <div className="page-header">
        <h1>Sign in</h1>
      </div>
      <div className="card">
        <Alert kind="error">{error}</Alert>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <button type="submit" className="primary" disabled={busy} style={{ width: "100%" }}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="divider" />
        <button type="button" onClick={startOAuth} style={{ width: "100%" }}>
          Continue with Google
        </button>
        <p className="subtle" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
          New here? <Link href="/register">Create an account</Link>
        </p>
      </div>
    </div>
  );
}
