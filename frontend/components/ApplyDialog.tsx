"use client";

import { useEffect, useState } from "react";

import { Alert, Modal } from "@/components/ui";
import { api } from "@/lib/api";
import type { ResumeSummary } from "@/lib/types";

export function ApplyDialog({
  jobTitle,
  applyUrl,
  onCancel,
  onConfirm,
}: {
  jobTitle: string;
  applyUrl: string | null;
  onCancel: () => void;
  onConfirm: (payload: { resume_id?: string; application_url?: string; notes?: string }) => void;
}) {
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [resumeId, setResumeId] = useState("");
  const [url, setUrl] = useState(applyUrl ?? "");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.resumes();
        setResumes(list);
        setResumeId(list.find((item) => item.is_default)?.id ?? list[0]?.id ?? "");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not load your resumes");
      }
    })();
  }, []);

  return (
    <Modal title={`Log your application to “${jobTitle}”`} onClose={onCancel}>
      <Alert kind="error">{error}</Alert>
      <p className="subtle">
        Apply on the company&apos;s own site, then record it here. We keep a snapshot of the job
        description with the application.
      </p>

      <div className="field">
        <label htmlFor="apply-resume">Resume used</label>
        <select
          id="apply-resume"
          value={resumeId}
          onChange={(event) => setResumeId(event.target.value)}
        >
          {resumes.length === 0 && <option value="">No resumes uploaded</option>}
          {resumes.map((resume) => (
            <option key={resume.id} value={resume.id}>
              {resume.label}
              {resume.is_default ? " (default)" : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="apply-url">Application URL</label>
        <input
          id="apply-url"
          type="url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="apply-notes">Notes</label>
        <textarea
          id="apply-notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Referral, cover letter angle, anything to remember"
        />
      </div>

      <div className="row-between">
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="button"
          className="primary"
          onClick={() =>
            onConfirm({
              resume_id: resumeId || undefined,
              application_url: url || undefined,
              notes: notes || undefined,
            })
          }
        >
          Mark as applied
        </button>
      </div>
    </Modal>
  );
}
