"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth, useRequireAuth } from "@/lib/auth";
import { formatDate, titleCase } from "@/lib/format";
import type { PrivacySummary } from "@/lib/types";

export default function PrivacyPage() {
  const { loading } = useRequireAuth();
  const { signOut } = useAuth();
  const [summary, setSummary] = useState<PrivacySummary | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");

  const load = useCallback(async () => {
    try {
      setSummary(await api.privacySummary());
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load your privacy summary");
    }
  }, []);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  const exportData = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await api.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "job-board-data-export.json";
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice("Your data export has been downloaded.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not export your data");
    } finally {
      setBusy(false);
    }
  };

  const deleteResumes = async () => {
    if (!window.confirm("Delete every resume and its stored file? This cannot be undone.")) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.deleteAllResumes();
      setNotice(result.detail);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete your resumes");
    } finally {
      setBusy(false);
    }
  };

  const deleteAccount = async () => {
    setBusy(true);
    setError("");
    try {
      await api.deleteAccount(confirmation, password || undefined);
      signOut();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete your account");
      setBusy(false);
    }
  };

  if (loading || (!summary && !error)) {
    return (
      <div className="page medium">
        <Loading />
      </div>
    );
  }

  return (
    <div className="page medium">
      <div className="page-header">
        <h1>Privacy and account</h1>
        <p>
          Your phone number, home address and recruiter contact details are encrypted before they
          are written to the database. Everything below acts on your data immediately.
        </p>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{notice}</Alert>

      {summary && (
        <>
          <div className="card">
            <h2>What we hold</h2>
            <div className="divider" />
            <dl style={{ margin: 0 }}>
              <Row label="Resume versions" value={summary.resume_count} />
              <Row label="Resume files stored" value={summary.stored_resume_files} />
              <Row label="Applications" value={summary.application_count} />
              <Row label="Recruiter contacts" value={summary.contact_count} />
            </dl>
          </div>

          <div className="card">
            <h2>Consent history</h2>
            <div className="divider" />
            {summary.consents.length === 0 ? (
              <p className="subtle">No consent events recorded.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Consent</th>
                      <th>State</th>
                      <th>Recorded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.consents.map((consent, index) => (
                      <tr key={`${consent.consent_type}-${index}`}>
                        <td>{titleCase(consent.consent_type)}</td>
                        <td>{consent.granted ? "Granted" : "Withdrawn"}</td>
                        <td>{formatDate(consent.recorded_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="divider" />
            <div className="row">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void api
                    .recordConsent("marketing_email", true)
                    .then(() => load())
                    .then(() => setNotice("Marketing consent granted."))
                }
              >
                Grant marketing email consent
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void api
                    .recordConsent("marketing_email", false)
                    .then(() => load())
                    .then(() => setNotice("Marketing consent withdrawn."))
                }
              >
                Withdraw it
              </button>
            </div>
          </div>

          <div className="card">
            <h2>Export</h2>
            <p className="muted">
              Download everything on this account as JSON — profile, preferences, resumes,
              applications, contacts and consent history.
            </p>
            <button type="button" onClick={exportData} disabled={busy}>
              Download my data
            </button>
          </div>

          <div className="card">
            <h2>Delete resumes</h2>
            <p className="muted">
              Removes every stored resume file and the text extracted from it. Your applications
              keep their own snapshots.
            </p>
            <button type="button" className="danger" onClick={deleteResumes} disabled={busy}>
              Delete all my resumes
            </button>
          </div>

          <div className="card" style={{ borderColor: "var(--missing)" }}>
            <h2>Delete this account</h2>
            <p className="muted">
              Permanently erases your account, resumes, applications, contacts and recommendation
              history. This cannot be undone.
            </p>
            <div className="field">
              <label htmlFor="confirm">Type DELETE to confirm</label>
              <input
                id="confirm"
                type="text"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="pw">Your password</label>
              <input
                id="pw"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            <button
              type="button"
              className="danger"
              onClick={deleteAccount}
              disabled={busy || confirmation !== "DELETE"}
            >
              Delete my account permanently
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="row-between" style={{ padding: "0.3rem 0" }}>
      <dt className="subtle">{label}</dt>
      <dd style={{ margin: 0, fontWeight: 600 }}>{value}</dd>
    </div>
  );
}
