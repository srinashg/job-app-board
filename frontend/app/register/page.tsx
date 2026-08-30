"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function RegisterPage() {
  const { signUp } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await signUp({ ...form, accepted_terms: acceptedTerms });
      router.push("/onboarding");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create the account");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page narrow" style={{ paddingTop: "3rem" }}>
      <div className="page-header">
        <h1>Create your account</h1>
      </div>
      <div className="card">
        <Alert kind="error">{error}</Alert>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="full_name">Full name</label>
            <input
              id="full_name"
              type="text"
              autoComplete="name"
              value={form.full_name}
              onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
            <div className="field-hint">
              At least 10 characters, including a letter and a number.
            </div>
          </div>
          <div className="checkbox-row">
            <input
              id="terms"
              type="checkbox"
              checked={acceptedTerms}
              onChange={(event) => setAcceptedTerms(event.target.checked)}
            />
            <label htmlFor="terms">
              I accept the terms of service and privacy policy, and consent to my resume being
              processed to match me with jobs.
            </label>
          </div>
          <button
            type="submit"
            className="primary"
            disabled={busy || !acceptedTerms}
            style={{ width: "100%", marginTop: "0.5rem" }}
          >
            {busy ? "Creating…" : "Create account"}
          </button>
        </form>
        <p className="subtle" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
