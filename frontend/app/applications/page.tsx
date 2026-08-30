"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Alert, EmptyState, Loading, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { APPLICATION_STATUSES, formatDate, titleCase } from "@/lib/format";
import type { Application, ApplicationStatus } from "@/lib/types";

export default function ApplicationsPage() {
  const { loading } = useRequireAuth();
  const [rows, setRows] = useState<Application[] | null>(null);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "">("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    try {
      const page = await api.applications({
        status: statusFilter ? [statusFilter] : undefined,
        q: search || undefined,
        limit: 100,
      });
      setRows(page.items);
      setTotal(page.total);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load your applications");
      setRows([]);
    }
  }, [statusFilter, search]);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  if (loading || rows === null) {
    return (
      <div className="page">
        <Loading />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div className="row-between">
          <div>
            <h1>Applications</h1>
            <p>Every job you applied to, skipped or closed — with the resume and snapshot used.</p>
          </div>
          <button type="button" className="primary" onClick={() => setShowAdd((open) => !open)}>
            {showAdd ? "Cancel" : "Log an application"}
          </button>
        </div>
      </div>

      <Alert kind="error">{error}</Alert>

      {showAdd && (
        <ManualApplicationForm
          onDone={() => {
            setShowAdd(false);
            void load();
          }}
        />
      )}

      <div className="card">
        <div className="row">
          <div style={{ flex: 1, minWidth: "200px" }}>
            <input
              type="search"
              placeholder="Search company or role"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as ApplicationStatus | "")}
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              {APPLICATION_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {titleCase(status)}
                </option>
              ))}
            </select>
          </div>
          <span className="subtle">{total} total</span>
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No applications yet">
          Apply to a job from your five, or log one you sent elsewhere.
        </EmptyState>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Position</th>
                  <th>Work setup</th>
                  <th>Status</th>
                  <th>Applied</th>
                  <th>Match</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.company_name}</td>
                    <td>
                      <Link href={`/applications/${row.id}`}>{row.position_title}</Link>
                      <div className="subtle">{row.location ?? "—"}</div>
                    </td>
                    <td>
                      {row.work_arrangement === "remote"
                        ? "Remote"
                        : row.work_address || titleCase(row.work_arrangement)}
                    </td>
                    <td>
                      <StatusBadge status={row.status} />
                    </td>
                    <td>{formatDate(row.applied_at)}</td>
                    <td>{row.match_score ?? "—"}</td>
                    <td>
                      <Link href={`/applications/${row.id}`} className="button small">
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function ManualApplicationForm({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState({
    company_name: "",
    position_title: "",
    location: "",
    work_arrangement: "remote",
    work_address: "",
    application_url: "",
    status: "applied",
    notes: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createApplication({
        ...form,
        work_address: form.work_arrangement === "remote" ? null : form.work_address || null,
        location: form.location || null,
        application_url: form.application_url || null,
        notes: form.notes || null,
      });
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save that application");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3>Log an application you sent elsewhere</h3>
      <Alert kind="error">{error}</Alert>
      <form onSubmit={submit}>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="m-company">Company</label>
            <input
              id="m-company"
              type="text"
              required
              value={form.company_name}
              onChange={(event) => setForm({ ...form, company_name: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="m-position">Position</label>
            <input
              id="m-position"
              type="text"
              required
              value={form.position_title}
              onChange={(event) => setForm({ ...form, position_title: event.target.value })}
            />
          </div>
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="m-location">Location</label>
            <input
              id="m-location"
              type="text"
              value={form.location}
              onChange={(event) => setForm({ ...form, location: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="m-setup">Work setup</label>
            <select
              id="m-setup"
              value={form.work_arrangement}
              onChange={(event) => setForm({ ...form, work_arrangement: event.target.value })}
            >
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </div>
        </div>
        {form.work_arrangement !== "remote" && (
          <div className="field">
            <label htmlFor="m-address">Office address</label>
            <input
              id="m-address"
              type="text"
              value={form.work_address}
              onChange={(event) => setForm({ ...form, work_address: event.target.value })}
            />
          </div>
        )}
        <div className="grid-2">
          <div className="field">
            <label htmlFor="m-url">Application URL</label>
            <input
              id="m-url"
              type="url"
              value={form.application_url}
              onChange={(event) => setForm({ ...form, application_url: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="m-status">Status</label>
            <select
              id="m-status"
              value={form.status}
              onChange={(event) => setForm({ ...form, status: event.target.value })}
            >
              {APPLICATION_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {titleCase(status)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field">
          <label htmlFor="m-notes">Notes</label>
          <textarea
            id="m-notes"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </div>
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Saving…" : "Save application"}
        </button>
      </form>
    </div>
  );
}
