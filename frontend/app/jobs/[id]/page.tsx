"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApplyDialog } from "@/components/ApplyDialog";
import { SkipDialog } from "@/components/SkipDialog";
import { Alert, Loading, MatchExplanation, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { formatDate, formatSalary, relativeDays, skillLabel, titleCase } from "@/lib/format";
import type { JobDetailResponse, SkipReason } from "@/lib/types";

export default function JobDetailPage() {
  const { loading } = useRequireAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<JobDetailResponse | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showSkip, setShowSkip] = useState(false);
  const [showApply, setShowApply] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.job(params.id));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this job");
    }
  }, [params.id]);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  if (loading || (!data && !error)) {
    return (
      <div className="page medium">
        <Loading />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page medium">
        <Alert kind="error">{error}</Alert>
        <Link href="/jobs" className="button">
          Back to my five
        </Link>
      </div>
    );
  }

  const { job, match, recommendation_id, is_saved, already_applied } = data;
  const canAct = Boolean(recommendation_id) && !already_applied;

  const skip = async (reason: SkipReason, note: string) => {
    if (!recommendation_id) return;
    setBusy(true);
    setShowSkip(false);
    try {
      await api.skipRecommendation(recommendation_id, reason, note || undefined);
      router.push("/jobs");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not skip this job");
      setBusy(false);
    }
  };

  const apply = async (payload: {
    resume_id?: string;
    application_url?: string;
    notes?: string;
  }) => {
    if (!recommendation_id) return;
    setBusy(true);
    setShowApply(false);
    try {
      await api.applyToRecommendation(recommendation_id, payload);
      setNotice("Application logged.");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not log this application");
    } finally {
      setBusy(false);
    }
  };

  const toggleSave = async () => {
    if (!recommendation_id) return;
    setBusy(true);
    try {
      if (is_saved) await api.unsaveRecommendation(recommendation_id);
      else await api.saveRecommendation(recommendation_id);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update this job");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <Link href="/jobs" className="subtle">
          ← Back to my five
        </Link>
        <div className="row-between" style={{ marginTop: "0.5rem" }}>
          <div>
            <h1>{job.title}</h1>
            <p className="muted" style={{ margin: "0.3rem 0 0" }}>
              {job.company.name} · {job.location ?? titleCase(job.work_arrangement)} ·{" "}
              {formatSalary(job.salary_min, job.salary_max, job.salary_currency)}
            </p>
          </div>
          <StatusBadge status={job.status} />
        </div>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{notice}</Alert>
      {already_applied && <Alert kind="info">You have already logged an application for this job.</Alert>}

      <div className="grid-sidebar">
        <div>
          <div className="card">
            <h2>Job description</h2>
            <p className="subtle">
              Saved snapshot from {formatDate(job.first_seen_at)} — this is what the posting said
              when we captured it, so it stays readable even if the listing changes.
            </p>
            <div className="divider" />
            <div className="job-description">
              {job.description_snapshot || job.description || "No description was provided."}
            </div>
          </div>

          {match && (
            <div className="card">
              <h2>Why this matched</h2>
              <div className="divider" />
              <MatchExplanation match={match} />
            </div>
          )}
        </div>

        <div>
          <div className="card">
            <h3>Actions</h3>
            <div className="stack-sm" style={{ marginTop: "0.6rem" }}>
              <a
                href={job.apply_url ?? job.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="button button-primary"
              >
                Apply on the official site ↗
              </a>
              {canAct ? (
                <>
                  <button type="button" onClick={() => setShowApply(true)} disabled={busy}>
                    I applied — log it
                  </button>
                  <button type="button" onClick={() => setShowSkip(true)} disabled={busy}>
                    Skip this job
                  </button>
                  <button type="button" onClick={toggleSave} disabled={busy}>
                    {is_saved ? "Remove from saved" : "Save for later"}
                  </button>
                </>
              ) : (
                <p className="subtle" style={{ margin: 0 }}>
                  {already_applied
                    ? "Manage this from the Applications tab."
                    : "This job is not in your current batch."}
                </p>
              )}
            </div>
          </div>

          <div className="card">
            <h3>Company and location</h3>
            <dl style={{ margin: 0 }}>
              <Row label="Company" value={job.company.name} />
              <Row label="Industry" value={job.company.industry ?? job.industry} />
              <Row label="Headquarters" value={job.company.headquarters} />
              <Row label="Work setup" value={titleCase(job.work_arrangement)} />
              <Row
                label="Address"
                value={
                  job.work_arrangement === "remote"
                    ? "Remote — no office required"
                    : [job.street_address, job.city, job.region, job.postal_code]
                        .filter(Boolean)
                        .join(", ") || job.location
                }
              />
              <Row label="Posted" value={relativeDays(job.date_posted)} />
              <Row label="Last verified" value={formatDate(job.last_verified_at)} />
              <Row
                label="Experience"
                value={
                  job.min_years_experience
                    ? `${job.min_years_experience}+ years · ${titleCase(job.experience_level)}`
                    : titleCase(job.experience_level)
                }
              />
              <Row
                label="Clearance"
                value={job.requires_clearance ? titleCase(job.requires_clearance) : "Not required"}
              />
              <Row
                label="Sponsorship"
                value={
                  job.sponsorship_available === null
                    ? "Not stated"
                    : job.sponsorship_available
                      ? "Available"
                      : "Not offered"
                }
              />
            </dl>
            <div className="divider" />
            <a href={job.source_url} target="_blank" rel="noreferrer noopener" className="subtle">
              Official source ↗
            </a>
          </div>

          {(job.required_skills.length > 0 || job.preferred_skills.length > 0) && (
            <div className="card">
              <h3>Skills in this posting</h3>
              {job.required_skills.length > 0 && (
                <>
                  <div className="subtle" style={{ marginTop: "0.5rem" }}>
                    Required
                  </div>
                  <div className="chip-list">
                    {job.required_skills.map((skill) => (
                      <span className="chip" key={skill}>
                        {skillLabel(skill)}
                      </span>
                    ))}
                  </div>
                </>
              )}
              {job.preferred_skills.length > 0 && (
                <>
                  <div className="subtle" style={{ marginTop: "0.6rem" }}>
                    Nice to have
                  </div>
                  <div className="chip-list">
                    {job.preferred_skills.map((skill) => (
                      <span className="chip" key={skill}>
                        {skillLabel(skill)}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {showSkip && (
        <SkipDialog jobTitle={job.title} onCancel={() => setShowSkip(false)} onConfirm={skip} />
      )}
      {showApply && (
        <ApplyDialog
          jobTitle={job.title}
          applyUrl={job.apply_url ?? job.source_url}
          onCancel={() => setShowApply(false)}
          onConfirm={apply}
        />
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="row-between" style={{ padding: "0.3rem 0", gap: "0.75rem" }}>
      <dt className="subtle" style={{ flex: "none" }}>
        {label}
      </dt>
      <dd style={{ margin: 0, textAlign: "right", fontSize: "0.88rem" }}>{value || "—"}</dd>
    </div>
  );
}
