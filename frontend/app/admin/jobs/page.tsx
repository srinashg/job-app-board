"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert, EmptyState, Loading, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { formatDate, titleCase } from "@/lib/format";
import type { AdminJobRow, AdminStats, BlacklistEntry, JobSource } from "@/lib/types";

const ACTIONS = [
  { value: "disable", label: "Disable" },
  { value: "enable", label: "Re-enable" },
  { value: "mark_stale", label: "Mark stale" },
  { value: "mark_duplicate", label: "Mark duplicate" },
  { value: "mark_scam", label: "Mark scam" },
  { value: "mark_closed", label: "Mark closed" },
];

const STATUSES = ["active", "closed", "stale", "duplicate", "disabled", "scam"];

export default function AdminJobsPage() {
  const { loading } = useRequireAuth({ adminOnly: true });
  const [rows, setRows] = useState<AdminJobRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [blacklists, setBlacklists] = useState<BlacklistEntry[]>([]);
  const [sources, setSources] = useState<JobSource[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [action, setAction] = useState("disable");
  const [duplicateOf, setDuplicateOf] = useState("");
  const [actionNotes, setActionNotes] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [page, adminStats, entries, sourceList] = await Promise.all([
        api.adminJobs({ q: search || undefined, status: statusFilter || undefined, limit: 100 }),
        api.adminStats(),
        api.blacklists(),
        api.sources(),
      ]);
      setRows(page.items);
      setTotal(page.total);
      setStats(adminStats);
      setBlacklists(entries);
      setSources(sourceList);
      setSelected(new Set());
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the admin data");
      setRows([]);
    }
  }, [search, statusFilter]);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  const run = async (task: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError("");
    try {
      await task();
      setNotice(message);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That did not work");
    } finally {
      setBusy(false);
    }
  };

  const applyAction = () =>
    run(
      () =>
        api.adminAction({
          job_ids: [...selected],
          action,
          duplicate_of_id: action === "mark_duplicate" ? duplicateOf || undefined : undefined,
          notes: actionNotes || undefined,
        }),
      `Applied “${action}” to ${selected.size} job(s).`,
    );

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
        <h1>Job moderation</h1>
        <p>
          Inspect the pool, take listings out of circulation, and blacklist companies or domains
          that keep posting bad jobs.
        </p>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{notice}</Alert>

      {stats && (
        <div className="grid-3">
          <Stat label="Active" value={stats.active_jobs} />
          <Stat label="Closed" value={stats.closed_jobs} />
          <Stat label="Stale" value={stats.stale_jobs} />
          <Stat label="Duplicates" value={stats.duplicate_jobs} />
          <Stat label="Disabled" value={stats.disabled_jobs} />
          <Stat label="Scam" value={stats.scam_jobs} />
          <Stat label="Companies" value={stats.total_companies} />
          <Stat label="Sources enabled" value={`${stats.enabled_sources}/${stats.total_sources}`} />
        </div>
      )}

      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>Fetch and verify</h3>
        <div className="row" style={{ marginTop: "0.5rem" }}>
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => api.seedSources(), "Default sources registered.")}
          >
            Register default sources
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const result = await api.runIngest();
                setNotice(
                  `Fetched ${result.jobs_fetched} listing(s): ${result.jobs_created} new, ` +
                    `${result.jobs_updated} updated, ${result.duplicates_detected} duplicate(s).` +
                    (result.errors.length ? ` ${result.errors.length} source error(s).` : ""),
                );
              }, "Ingestion finished.")
            }
          >
            Fetch jobs now
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const result = await api.runFreshness();
                setNotice(
                  `Checked ${result.checked}: ${result.still_open} still open, ` +
                    `${result.marked_closed} closed, ${result.marked_stale} stale.`,
                );
              }, "Freshness check finished.")
            }
          >
            Re-verify listings
          </button>
        </div>
        {sources.length > 0 && (
          <div className="table-wrap" style={{ marginTop: "0.75rem" }}>
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Enabled</th>
                  <th>Last fetch</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr key={source.id}>
                    <td>{source.name}</td>
                    <td>{titleCase(source.source_type)}</td>
                    <td>{source.is_enabled ? "Yes" : "No"}</td>
                    <td>{formatDate(source.last_fetched_at)}</td>
                    <td className="subtle">
                      {source.last_fetch_status ?? "never run"}
                      {source.last_fetch_error ? ` — ${source.last_fetch_error}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <div className="row">
          <div style={{ flex: 1, minWidth: "200px" }}>
            <input
              type="search"
              placeholder="Search title, company or URL"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {titleCase(status)}
              </option>
            ))}
          </select>
          <span className="subtle">{total} jobs</span>
        </div>

        {selected.size > 0 && (
          <>
            <div className="divider" />
            <div className="row">
              <strong>{selected.size} selected</strong>
              <select value={action} onChange={(event) => setAction(event.target.value)}>
                {ACTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              {action === "mark_duplicate" && (
                <input
                  type="text"
                  placeholder="Canonical job id"
                  value={duplicateOf}
                  onChange={(event) => setDuplicateOf(event.target.value)}
                  style={{ maxWidth: "320px" }}
                />
              )}
              <input
                type="text"
                placeholder="Moderation note"
                value={actionNotes}
                onChange={(event) => setActionNotes(event.target.value)}
                style={{ maxWidth: "260px" }}
              />
              <button type="button" className="primary" onClick={applyAction} disabled={busy}>
                Apply
              </button>
            </div>
          </>
        )}
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No jobs match">Fetch from a source or clear your filters.</EmptyState>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={selected.size === rows.length && rows.length > 0}
                      onChange={(event) =>
                        setSelected(event.target.checked ? new Set(rows.map((row) => row.id)) : new Set())
                      }
                    />
                  </th>
                  <th>Title</th>
                  <th>Company</th>
                  <th>Status</th>
                  <th>Source</th>
                  <th>Verified</th>
                  <th>Shown</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select ${row.title}`}
                        checked={selected.has(row.id)}
                        onChange={(event) => {
                          const next = new Set(selected);
                          if (event.target.checked) next.add(row.id);
                          else next.delete(row.id);
                          setSelected(next);
                        }}
                      />
                    </td>
                    <td>
                      {row.title}
                      <div className="mono subtle">{row.id}</div>
                      {row.moderation_notes && (
                        <div className="subtle">{row.moderation_notes}</div>
                      )}
                    </td>
                    <td>
                      {row.company_name}
                      <div className="subtle">{row.company_domain ?? "—"}</div>
                    </td>
                    <td>
                      <StatusBadge status={row.status} />
                      {row.verification_failures > 0 && (
                        <div className="subtle">{row.verification_failures} failed checks</div>
                      )}
                    </td>
                    <td className="subtle">
                      {titleCase(row.source_type ?? "manual")}
                      <div>
                        <a href={row.source_url} target="_blank" rel="noreferrer noopener">
                          posting ↗
                        </a>
                      </div>
                    </td>
                    <td className="subtle">{formatDate(row.last_verified_at)}</td>
                    <td>{row.recommendation_count}</td>
                    <td>
                      <button
                        type="button"
                        className="small"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () =>
                              api.addBlacklist({
                                scope: "company",
                                value: row.company_slug,
                                reason: `Blacklisted from job ${row.id}`,
                              }),
                            `Blacklisted ${row.company_name}.`,
                          )
                        }
                      >
                        Blacklist company
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <h2>Blacklists</h2>
        <BlacklistForm onDone={(message) => run(async () => undefined, message)} />
        <div className="divider" />
        {blacklists.length === 0 ? (
          <p className="subtle">Nothing is blacklisted.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Scope</th>
                  <th>Value</th>
                  <th>Reason</th>
                  <th>Added</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {blacklists.map((entry) => (
                  <tr key={entry.id}>
                    <td>{titleCase(entry.scope)}</td>
                    <td className="mono">{entry.value}</td>
                    <td className="subtle">{entry.reason ?? "—"}</td>
                    <td className="subtle">{formatDate(entry.created_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="small"
                        disabled={busy}
                        onClick={() =>
                          run(() => api.removeBlacklist(entry.id), "Blacklist entry removed.")
                        }
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function BlacklistForm({ onDone }: { onDone: (message: string) => void }) {
  const [scope, setScope] = useState("company");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
          await api.addBlacklist({ scope, value, reason: reason || undefined });
          setValue("");
          setReason("");
          onDone(`Blacklisted ${scope} “${value}”.`);
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "Could not add that entry");
        } finally {
          setBusy(false);
        }
      }}
    >
      <Alert kind="error">{error}</Alert>
      <div className="row">
        <select value={scope} onChange={(event) => setScope(event.target.value)} aria-label="Scope">
          <option value="company">Company</option>
          <option value="domain">Domain</option>
          <option value="job">Job id</option>
        </select>
        <input
          type="text"
          required
          placeholder={scope === "domain" ? "spam.example" : "Acme Corp"}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          style={{ maxWidth: "260px" }}
        />
        <input
          type="text"
          placeholder="Reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          style={{ maxWidth: "260px" }}
        />
        <button type="submit" className="primary" disabled={busy}>
          Add
        </button>
      </div>
    </form>
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
