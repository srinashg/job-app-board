"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApplyDialog } from "@/components/ApplyDialog";
import { SkipDialog } from "@/components/SkipDialog";
import { Alert, EmptyState, Loading, QualificationList, ScoreBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { formatPlace, formatSalary, relativeDays, skillLabel, titleCase } from "@/lib/format";
import type { BatchState, Recommendation, SkipReason } from "@/lib/types";

export default function BatchPage() {
  const { loading } = useRequireAuth();
  const [state, setState] = useState<BatchState | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [skipTarget, setSkipTarget] = useState<Recommendation | null>(null);
  const [applyTarget, setApplyTarget] = useState<Recommendation | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await api.currentBatch());
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load your batch");
    }
  }, []);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  const skip = async (recommendation: Recommendation, reason: SkipReason, note: string) => {
    setBusy(true);
    setSkipTarget(null);
    try {
      const next = await api.skipRecommendation(recommendation.id, reason, note || undefined);
      setState(next);
      setNotice(
        reason === "already_applied" || reason === "closed"
          ? "Skipped and replaced with another job."
          : "Skipped.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not skip that job");
    } finally {
      setBusy(false);
    }
  };

  const apply = async (
    recommendation: Recommendation,
    payload: { resume_id?: string; application_url?: string; notes?: string },
  ) => {
    setBusy(true);
    setApplyTarget(null);
    try {
      await api.applyToRecommendation(recommendation.id, payload);
      setNotice("Application logged. Track it from the Applications tab.");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not log that application");
    } finally {
      setBusy(false);
    }
  };

  const toggleSave = async (recommendation: Recommendation) => {
    setBusy(true);
    try {
      if (recommendation.status === "saved") {
        await api.unsaveRecommendation(recommendation.id);
      } else {
        await api.saveRecommendation(recommendation.id);
      }
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update that job");
    } finally {
      setBusy(false);
    }
  };

  const unlockNext = async () => {
    setBusy(true);
    setNotice("");
    try {
      setState(await api.nextBatch());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not unlock the next batch");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !state) {
    return (
      <div className="page medium">
        <Loading label="Finding your five…" />
      </div>
    );
  }

  const batch = state.batch;
  const total = batch?.recommendations.length ?? 0;
  const resolved = total - state.remaining;

  return (
    <div className="page">
      <div className="page-header">
        <div className="row-between">
          <div>
            <h1>Your five</h1>
            <p>
              Resolve every job below — apply, skip with a reason, or mark it unavailable — and the
              next five unlock.
            </p>
          </div>
          {batch && (
            <div style={{ minWidth: "180px" }}>
              <div className="row-between">
                <span className="subtle">Batch {batch.sequence}</span>
                <span className="subtle">
                  {resolved} of {total} resolved
                </span>
              </div>
              <div className="progress" style={{ marginTop: "0.35rem" }}>
                <div
                  className="progress-bar"
                  style={{ width: `${total ? (resolved / total) * 100 : 0}%` }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{notice}</Alert>

      {!batch && state.exhausted && (
        <EmptyState title="Nothing matches right now">
          {state.message ??
            "No open jobs clear your filters. Widen your preferences or wait for the next fetch."}
        </EmptyState>
      )}

      {!batch && !state.exhausted && (
        <div className="card" style={{ textAlign: "center" }}>
          <h2>Batch complete</h2>
          <p className="muted">{state.message ?? "You resolved all five. Ready for the next set?"}</p>
          <button type="button" className="primary" onClick={unlockNext} disabled={busy}>
            Unlock the next five
          </button>
        </div>
      )}

      {batch && (
        <div className="stack">
          {batch.recommendations.map((recommendation) => (
            <JobCard
              key={recommendation.id}
              recommendation={recommendation}
              busy={busy}
              onSkip={() => setSkipTarget(recommendation)}
              onApply={() => setApplyTarget(recommendation)}
              onToggleSave={() => toggleSave(recommendation)}
            />
          ))}

          {state.remaining === 0 && (
            <div className="card" style={{ textAlign: "center" }}>
              <h3>All five resolved</h3>
              <button type="button" className="primary" onClick={unlockNext} disabled={busy}>
                Unlock the next five
              </button>
            </div>
          )}
        </div>
      )}

      {skipTarget && (
        <SkipDialog
          jobTitle={skipTarget.job.title}
          onCancel={() => setSkipTarget(null)}
          onConfirm={(reason, note) => skip(skipTarget, reason, note)}
        />
      )}
      {applyTarget && (
        <ApplyDialog
          jobTitle={applyTarget.job.title}
          applyUrl={applyTarget.job.source_url}
          onCancel={() => setApplyTarget(null)}
          onConfirm={(payload) => apply(applyTarget, payload)}
        />
      )}
    </div>
  );
}

function JobCard({
  recommendation,
  busy,
  onSkip,
  onApply,
  onToggleSave,
}: {
  recommendation: Recommendation;
  busy: boolean;
  onSkip: () => void;
  onApply: () => void;
  onToggleSave: () => void;
}) {
  const { job, match_explanation: match } = recommendation;
  const resolved = ["applied", "skipped", "closed"].includes(recommendation.status);

  return (
    <article className="card" style={resolved ? { opacity: 0.65 } : undefined}>
      <div className="card-header">
        <div className="row" style={{ alignItems: "flex-start" }}>
          <ScoreBadge score={recommendation.match_score} />
          <div>
            <h2>
              <Link href={`/jobs/${job.id}`}>{job.title}</Link>
            </h2>
            <div className="muted">
              {job.company.name} · {formatPlace(job)}
            </div>
            <div className="subtle">
              {formatSalary(job.salary_min, job.salary_max, job.salary_currency)} ·{" "}
              {relativeDays(job.date_posted)}
              {job.experience_level ? ` · ${titleCase(job.experience_level)} level` : ""}
            </div>
          </div>
        </div>
        {resolved && <span className="badge">{titleCase(recommendation.status)}</span>}
        {recommendation.status === "saved" && <span className="badge badge-accent">Saved</span>}
      </div>

      {match && (
        <div className="grid-2">
          <div>
            <h4 className="subtle" style={{ textTransform: "uppercase", fontSize: "0.75rem" }}>
              Strong
            </h4>
            <QualificationList items={match.strong.slice(0, 4)} />
          </div>
          <div>
            <h4 className="subtle" style={{ textTransform: "uppercase", fontSize: "0.75rem" }}>
              Missing
            </h4>
            <QualificationList items={match.missing.slice(0, 4)} />
          </div>
        </div>
      )}

      {job.technologies.length > 0 && (
        <div className="chip-list" style={{ marginTop: "0.75rem" }}>
          {job.technologies.slice(0, 10).map((technology) => (
            <span className="chip" key={technology}>
              {skillLabel(technology)}
            </span>
          ))}
        </div>
      )}

      {!resolved && (
        <>
          <div className="divider" />
          <div className="row">
            <button type="button" className="primary" onClick={onApply} disabled={busy}>
              Apply
            </button>
            <button type="button" onClick={onSkip} disabled={busy}>
              Skip
            </button>
            <button type="button" onClick={onToggleSave} disabled={busy}>
              {recommendation.status === "saved" ? "Unsave" : "Save for later"}
            </button>
            <Link href={`/jobs/${job.id}`} className="button">
              Details
            </Link>
            <a href={job.source_url} target="_blank" rel="noreferrer noopener" className="button">
              Official posting ↗
            </a>
          </div>
        </>
      )}
    </article>
  );
}
