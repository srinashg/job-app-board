"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Alert, Loading, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { APPLICATION_STATUSES, formatDate, titleCase } from "@/lib/format";
import type { ApplicationDetail, ApplicationStatus, Contact, ResumeSummary } from "@/lib/types";

export default function ApplicationDetailPage() {
  const { loading } = useRequireAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [detail, resumeList, contactList] = await Promise.all([
        api.application(params.id),
        api.resumes(),
        api.contacts(),
      ]);
      setApplication(detail);
      setNotes(detail.notes ?? "");
      setResumes(resumeList);
      setContacts(contactList);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this application");
    }
  }, [params.id]);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  const run = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError("");
    try {
      await action();
      setNotice(message);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "That did not work");
    } finally {
      setBusy(false);
    }
  };

  if (loading || (!application && !error)) {
    return (
      <div className="page medium">
        <Loading />
      </div>
    );
  }

  if (!application) {
    return (
      <div className="page medium">
        <Alert kind="error">{error}</Alert>
        <Link href="/applications" className="button">
          Back to applications
        </Link>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <Link href="/applications" className="subtle">
          ← Back to applications
        </Link>
        <div className="row-between" style={{ marginTop: "0.5rem" }}>
          <div>
            <h1>{application.position_title}</h1>
            <p className="muted" style={{ margin: "0.3rem 0 0" }}>
              {application.company_name} · {application.location ?? "—"}
            </p>
          </div>
          <StatusBadge status={application.status} />
        </div>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{notice}</Alert>

      <div className="grid-sidebar">
        <div>
          <div className="card">
            <h2>Job description snapshot</h2>
            <p className="subtle">
              Captured when you applied, so it survives the listing being edited or taken down.
            </p>
            <div className="divider" />
            <div className="job-description">
              {application.job_description_snapshot || "No snapshot was stored for this application."}
            </div>
          </div>

          <div className="card">
            <h2>Notes</h2>
            <div className="field" style={{ marginTop: "0.5rem" }}>
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={() => run(() => api.updateApplication(application.id, { notes }), "Notes saved.")}
            >
              Save notes
            </button>
          </div>

          <div className="card">
            <h2>History</h2>
            <div className="divider" />
            {application.events.length === 0 ? (
              <p className="subtle">No status changes recorded yet.</p>
            ) : (
              <ul className="qual-list">
                {application.events.map((event) => (
                  <li key={event.id} className="qual">
                    <span className="qual-mark" aria-hidden="true">
                      •
                    </span>
                    <span>
                      <strong>
                        {event.from_status ? `${titleCase(event.from_status)} → ` : ""}
                        {titleCase(event.to_status)}
                      </strong>
                      <span className="qual-detail"> — {formatDate(event.occurred_at)}</span>
                      {event.note ? <div className="subtle">{event.note}</div> : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div>
          <div className="card">
            <h3>Move to</h3>
            <div className="row" style={{ marginTop: "0.5rem" }}>
              {APPLICATION_STATUSES.filter((status) => status !== application.status).map((status) => (
                <button
                  key={status}
                  type="button"
                  className="small"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => api.setApplicationStatus(application.id, status as ApplicationStatus),
                      `Moved to ${titleCase(status)}.`,
                    )
                  }
                >
                  {titleCase(status)}
                </button>
              ))}
            </div>
            <p className="subtle" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
              Transitions that do not make sense (an offer after a rejection, say) are refused.
            </p>
          </div>

          <div className="card">
            <h3>Details</h3>
            <dl style={{ margin: 0 }}>
              <Row label="Applied" value={formatDate(application.applied_at)} />
              <Row label="First response" value={formatDate(application.first_response_at)} />
              <Row
                label="Work setup"
                value={
                  application.work_arrangement === "remote"
                    ? "Remote"
                    : titleCase(application.work_arrangement)
                }
              />
              <Row
                label="Address"
                value={
                  application.work_arrangement === "remote"
                    ? "Remote — no office"
                    : application.work_address
                }
              />
              <Row label="Match score" value={application.match_score?.toString()} />
            </dl>
            {application.application_url && (
              <>
                <div className="divider" />
                <a
                  href={application.application_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="subtle"
                >
                  Application link ↗
                </a>
              </>
            )}
          </div>

          <div className="card">
            <h3>Resume used</h3>
            <select
              value={application.resume_id ?? ""}
              disabled={busy}
              onChange={(event) =>
                run(
                  () =>
                    api.updateApplication(application.id, {
                      resume_id: event.target.value || null,
                    }),
                  "Resume updated.",
                )
              }
            >
              <option value="">None recorded</option>
              {resumes.map((resume) => (
                <option key={resume.id} value={resume.id}>
                  {resume.label}
                </option>
              ))}
            </select>
          </div>

          <div className="card">
            <h3>Recruiter contact</h3>
            <select
              value={application.contact_id ?? ""}
              disabled={busy}
              onChange={(event) =>
                run(
                  () =>
                    api.updateApplication(application.id, {
                      contact_id: event.target.value || null,
                    }),
                  "Contact updated.",
                )
              }
            >
              <option value="">No contact</option>
              {contacts.map((contact) => (
                <option key={contact.id} value={contact.id}>
                  {contact.name}
                  {contact.company_name ? ` · ${contact.company_name}` : ""}
                </option>
              ))}
            </select>
            {application.contact && (
              <div className="subtle" style={{ marginTop: "0.5rem" }}>
                {application.contact.email ?? "No email"} · {application.contact.phone ?? "No phone"}
              </div>
            )}
            <div className="divider" />
            <NewContactForm onCreated={() => void load()} />
          </div>

          <div className="card">
            <button
              type="button"
              className="danger small"
              disabled={busy}
              onClick={() => {
                if (window.confirm("Delete this application and its history?")) {
                  void api
                    .deleteApplication(application.id)
                    .then(() => router.push("/applications"))
                    .catch((caught: unknown) =>
                      setError(caught instanceof Error ? caught.message : "Could not delete it"),
                    );
                }
              }}
            >
              Delete this application
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function NewContactForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", company_name: "" });
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <button type="button" className="small ghost" onClick={() => setOpen(true)}>
        + Add a contact
      </button>
    );
  }

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        try {
          await api.createContact(form);
          setForm({ name: "", email: "", phone: "", company_name: "" });
          setOpen(false);
          onCreated();
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="field">
        <label htmlFor="c-name">Name</label>
        <input
          id="c-name"
          type="text"
          required
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="c-email">Email</label>
        <input
          id="c-email"
          type="email"
          value={form.email}
          onChange={(event) => setForm({ ...form, email: event.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="c-phone">Phone</label>
        <input
          id="c-phone"
          type="text"
          value={form.phone}
          onChange={(event) => setForm({ ...form, phone: event.target.value })}
        />
      </div>
      <div className="row">
        <button type="submit" className="small primary" disabled={busy}>
          Save contact
        </button>
        <button type="button" className="small ghost" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
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
