"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth, useRequireAuth } from "@/lib/auth";
import { titleCase } from "@/lib/format";
import type { DashboardStats } from "@/lib/types";

export default function DashboardPage() {
  const { loading } = useRequireAuth();
  const { user } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (loading) return;
    void (async () => {
      try {
        setStats(await api.dashboard());
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not load your dashboard");
      }
    })();
  }, [loading]);

  if (loading || (!stats && !error)) {
    return (
      <div className="page">
        <Loading />
      </div>
    );
  }

  const needsOnboarding = user && !user.onboarding_completed_at;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>How your search is actually going, not how much you browsed.</p>
      </div>

      <Alert kind="error">{error}</Alert>

      {needsOnboarding && (
        <Alert kind="info">
          Your setup is not finished. <Link href="/onboarding">Complete onboarding</Link> to start
          receiving recommendations.
        </Alert>
      )}

      {stats && (
        <>
          <div className="grid-3">
            <Stat label="Applications" value={stats.total_applications} />
            <Stat label="Responses" value={stats.responses} />
            <Stat label="Interviews" value={stats.interviews} />
            <Stat label="Offers" value={stats.offers} />
          </div>

          <div className="grid-3" style={{ marginTop: "1rem" }}>
            <Stat label="Response rate" value={`${stats.response_rate}%`} />
            <Stat label="Interview rate" value={`${stats.interview_rate}%`} />
            <Stat label="Offer rate" value={`${stats.offer_rate}%`} />
            <Stat label="Live pipeline" value={stats.in_pipeline} />
          </div>

          <div className="grid-2" style={{ marginTop: "1rem" }}>
            <div className="card">
              <h2>Pipeline</h2>
              <div className="divider" />
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th style={{ textAlign: "right" }}>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.pipeline_by_status.map((row) => (
                      <tr key={row.status}>
                        <td>{titleCase(row.status)}</td>
                        <td style={{ textAlign: "right" }}>{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <h2>Activity</h2>
              <div className="divider" />
              <dl style={{ margin: 0 }}>
                <Row label="Applied in the last 7 days" value={stats.applications_last_7_days} />
                <Row label="Applied in the last 30 days" value={stats.applications_last_30_days} />
                <Row label="Jobs skipped" value={stats.jobs_skipped} />
                <Row label="Rejections" value={stats.rejections} />
                <Row label="Withdrawn" value={stats.withdrawn} />
              </dl>
              <div className="divider" />
              {stats.active_batch_remaining > 0 ? (
                <>
                  <p className="muted">
                    You have {stats.active_batch_remaining} job
                    {stats.active_batch_remaining === 1 ? "" : "s"} left to resolve in your current
                    batch.
                  </p>
                  <Link href="/jobs" className="button button-primary">
                    Resolve my five
                  </Link>
                </>
              ) : (
                <>
                  <p className="muted">Your current batch is clear.</p>
                  <Link href="/jobs" className="button button-primary">
                    Get the next five
                  </Link>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
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
