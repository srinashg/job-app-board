"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { EligibilityFields, PreferenceFields } from "@/components/PreferenceFields";
import { Alert, Loading, ScoreBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { formatPlace } from "@/lib/format";
import type { Eligibility, Preferences, Recommendation } from "@/lib/types";

export default function PreferencesPage() {
  const { loading } = useRequireAuth();
  const [preferences, setPreferences] = useState<Partial<Preferences>>({});
  const [eligibility, setEligibility] = useState<Partial<Eligibility>>({});
  const [preview, setPreview] = useState<Recommendation[] | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (loading) return;
    void (async () => {
      try {
        const [prefs, elig] = await Promise.all([api.preferences(), api.eligibility()]);
        setPreferences(prefs);
        setEligibility(elig);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not load your filters");
      } finally {
        setReady(true);
      }
    })();
  }, [loading]);

  const save = async () => {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await api.savePreferences(preferences);
      await api.saveEligibility(eligibility);
      setStatus("Filters saved. They apply to your next batch.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save your filters");
    } finally {
      setBusy(false);
    }
  };

  const runPreview = async () => {
    setBusy(true);
    setError("");
    try {
      await api.savePreferences(preferences);
      await api.saveEligibility(eligibility);
      setPreview(await api.previewMatches());
      setStatus("Preview updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not preview matches");
    } finally {
      setBusy(false);
    }
  };

  const rebuild = async () => {
    setBusy(true);
    setError("");
    try {
      await api.savePreferences(preferences);
      await api.saveEligibility(eligibility);
      await api.rebuildBatch();
      setStatus("Your current five were rebuilt with these filters.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not rebuild your batch");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !ready) {
    return (
      <div className="page medium">
        <Loading />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Filters</h1>
        <p>
          Eligibility rules remove a job entirely. Preferences change how the remaining jobs rank
          and which ones clear your match threshold.
        </p>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{status}</Alert>

      <div className="grid-sidebar">
        <div>
          <div className="card">
            <h2>Preferences</h2>
            <div className="divider" />
            <PreferenceFields value={preferences} onChange={setPreferences} />
          </div>

          <div className="card">
            <h2>Eligibility rules</h2>
            <div className="divider" />
            <EligibilityFields value={eligibility} onChange={setEligibility} />
          </div>

          <div className="card">
            <div className="row">
              <button type="button" className="primary" onClick={save} disabled={busy}>
                Save filters
              </button>
              <button type="button" onClick={runPreview} disabled={busy}>
                Preview matches
              </button>
              <button type="button" onClick={rebuild} disabled={busy}>
                Rebuild my five now
              </button>
            </div>
            <p className="subtle" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
              Rebuilding releases the jobs you have not resolved yet and picks a fresh five.
            </p>
          </div>
        </div>

        <div className="card">
          <h3>Preview</h3>
          <p className="subtle">
            The top matches under these filters, without consuming them from your queue.
          </p>
          {preview === null ? (
            <p className="subtle">Run a preview to see what these filters return.</p>
          ) : preview.length === 0 ? (
            <Alert kind="info">
              No jobs clear these filters right now. Try lowering the match threshold or widening
              your locations.
            </Alert>
          ) : (
            <div className="stack-sm">
              {preview.map((item) => (
                <div key={item.job_id} className="row" style={{ alignItems: "flex-start" }}>
                  <ScoreBadge score={item.match_score} />
                  <div>
                    <Link href={`/jobs/${item.job_id}`}>{item.job.title}</Link>
                    <div className="subtle">
                      {item.job.company.name} · {formatPlace(item.job)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
