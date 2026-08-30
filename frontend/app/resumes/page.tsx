"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, EmptyState, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import type { ResumeSummary } from "@/lib/types";

export default function ResumesPage() {
  const { loading } = useRequireAuth();
  const [resumes, setResumes] = useState<ResumeSummary[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setResumes(await api.resumes());
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load your resumes");
      setResumes([]);
    }
  }, []);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  const upload = async (file: File) => {
    setBusy(true);
    setError("");
    try {
      const uploaded = await api.uploadResume(file, file.name);
      setNotice(
        uploaded.parse_status === "parsed"
          ? "Uploaded and parsed. Review the extracted details before matching uses them."
          : "Uploaded, but we could not read it. You can fill in the details by hand.",
      );
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not upload that file");
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const act = async (action: () => Promise<unknown>, message: string) => {
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

  if (loading || resumes === null) {
    return (
      <div className="page medium">
        <Loading />
      </div>
    );
  }

  return (
    <div className="page medium">
      <div className="page-header">
        <h1>Resumes</h1>
        <p>
          Upload as many versions as you like. The default one is used for matching and is
          pre-selected when you log an application.
        </p>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{notice}</Alert>

      <div className="card">
        <h3>Upload a new version</h3>
        <div className="field" style={{ marginTop: "0.6rem", marginBottom: 0 }}>
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <div className="field-hint">PDF, DOCX or plain text, up to 5MB.</div>
        </div>
      </div>

      {resumes.length === 0 ? (
        <EmptyState title="No resumes yet">
          Upload one above and we will extract your skills, experience, education, certifications
          and job titles.
        </EmptyState>
      ) : (
        <div className="stack">
          {resumes.map((resume) => (
            <div className="card" key={resume.id}>
              <div className="card-header">
                <div>
                  <h3>
                    <Link href={`/resumes/${resume.id}`}>{resume.label}</Link>{" "}
                    {resume.is_default && <span className="badge badge-accent">Default</span>}
                  </h3>
                  <div className="subtle">
                    Version {resume.version} · {resume.original_filename} ·{" "}
                    {Math.max(1, Math.round(resume.file_size / 1024))} KB · uploaded{" "}
                    {formatDate(resume.created_at)}
                  </div>
                  {resume.parse_status === "failed" && (
                    <div className="subtle" style={{ color: "var(--missing)" }}>
                      Could not parse: {resume.parse_error}
                    </div>
                  )}
                </div>
              </div>
              <div className="row">
                <Link href={`/resumes/${resume.id}`} className="button small">
                  Review extracted details
                </Link>
                {!resume.is_default && (
                  <button
                    type="button"
                    className="small"
                    disabled={busy}
                    onClick={() =>
                      act(() => api.setDefaultResume(resume.id), "Default resume updated.")
                    }
                  >
                    Make default
                  </button>
                )}
                <button
                  type="button"
                  className="small"
                  disabled={busy}
                  onClick={() => {
                    const label = window.prompt("New name for this version", resume.label);
                    if (label && label.trim()) {
                      void act(() => api.renameResume(resume.id, label.trim()), "Renamed.");
                    }
                  }}
                >
                  Rename
                </button>
                <button
                  type="button"
                  className="small danger"
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete “${resume.label}”? The stored file is removed permanently.`,
                      )
                    ) {
                      void act(() => api.deleteResume(resume.id), "Resume deleted.");
                    }
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
