"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Alert, Loading, TagInput } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import type {
  CertificationEntry,
  EducationEntry,
  ExperienceEntry,
  ResumeContent,
  ResumeDetail,
} from "@/lib/types";

const EMPTY_EXPERIENCE: ExperienceEntry = {
  company: "",
  title: "",
  start_date: "",
  end_date: "",
  location: "",
  description: "",
  is_current: false,
};

const EMPTY_EDUCATION: EducationEntry = {
  institution: "",
  degree: "",
  field_of_study: "",
  start_date: "",
  end_date: "",
  gpa: "",
};

const EMPTY_CERTIFICATION: CertificationEntry = {
  name: "",
  issuer: "",
  issued_date: "",
  expires_date: "",
  credential_id: "",
};

export default function ResumeEditorPage() {
  const { loading } = useRequireAuth();
  const params = useParams<{ id: string }>();
  const [resume, setResume] = useState<ResumeDetail | null>(null);
  const [content, setContent] = useState<ResumeContent | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const detail = await api.resume(params.id);
      setResume(detail);
      setContent(detail.content);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this resume");
    }
  }, [params.id]);

  useEffect(() => {
    if (loading) return;
    void load();
  }, [loading, load]);

  const save = async () => {
    if (!content) return;
    setBusy(true);
    setError("");
    try {
      const detail = await api.saveResumeContent(params.id, content as unknown as Record<string, unknown>);
      setResume(detail);
      setContent(detail.content);
      setNotice("Saved. Matching now uses these values.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save your edits");
    } finally {
      setBusy(false);
    }
  };

  const reparse = async () => {
    setBusy(true);
    setError("");
    try {
      const detail = await api.reparseResume(params.id);
      setResume(detail);
      setContent(detail.content);
      setNotice("Re-parsed the original file. Your edits were kept on top.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not re-parse this resume");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !content || !resume) {
    return (
      <div className="page medium">
        {error ? <Alert kind="error">{error}</Alert> : <Loading />}
      </div>
    );
  }

  const set = <K extends keyof ResumeContent>(key: K, value: ResumeContent[K]) =>
    setContent({ ...content, [key]: value });

  return (
    <div className="page medium">
      <div className="page-header">
        <Link href="/resumes" className="subtle">
          ← Back to resumes
        </Link>
        <h1 style={{ marginTop: "0.5rem" }}>{resume.label}</h1>
        <p>
          Everything we extracted, ready to correct. What you save here is what matching reads —
          the original parse is kept separately, so re-parsing never loses your edits.
        </p>
      </div>

      <Alert kind="error">{error}</Alert>
      <Alert kind="success">{notice}</Alert>
      {resume.parse_status === "failed" && (
        <Alert kind="info">
          We could not read this file ({resume.parse_error}). Fill in the fields below by hand.
        </Alert>
      )}

      <div className="card">
        <h2>Basics</h2>
        <div className="divider" />
        <div className="grid-2">
          <div className="field">
            <label htmlFor="full_name">Full name</label>
            <input
              id="full_name"
              type="text"
              value={content.full_name ?? ""}
              onChange={(event) => set("full_name", event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="location">Location</label>
            <input
              id="location"
              type="text"
              value={content.location ?? ""}
              onChange={(event) => set("location", event.target.value)}
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="years">Years of experience</label>
          <input
            id="years"
            type="number"
            min={0}
            max={70}
            step={0.5}
            value={content.years_of_experience ?? ""}
            onChange={(event) =>
              set("years_of_experience", event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </div>
        <div className="field">
          <label htmlFor="summary">Summary</label>
          <textarea
            id="summary"
            value={content.summary ?? ""}
            onChange={(event) => set("summary", event.target.value)}
          />
        </div>
      </div>

      <div className="card">
        <h2>Skills and titles</h2>
        <p className="subtle">These drive the skills and title parts of your match score.</p>
        <div className="divider" />
        <TagInput label="Skills" values={content.skills} onChange={(next) => set("skills", next)} />
        <TagInput
          label="Job titles"
          values={content.job_titles}
          onChange={(next) => set("job_titles", next)}
        />
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Experience</h2>
          <button
            type="button"
            className="small"
            onClick={() => set("experience", [...content.experience, { ...EMPTY_EXPERIENCE }])}
          >
            Add role
          </button>
        </div>
        {content.experience.length === 0 && <p className="subtle">No roles extracted.</p>}
        {content.experience.map((entry, index) => (
          <div key={index} className="stack-sm" style={{ marginBottom: "1rem" }}>
            <div className="grid-2">
              <div className="field">
                <label htmlFor={`exp-title-${index}`}>Title</label>
                <input
                  id={`exp-title-${index}`}
                  type="text"
                  value={entry.title ?? ""}
                  onChange={(event) =>
                    set(
                      "experience",
                      content.experience.map((item, position) =>
                        position === index ? { ...item, title: event.target.value } : item,
                      ),
                    )
                  }
                />
              </div>
              <div className="field">
                <label htmlFor={`exp-company-${index}`}>Company</label>
                <input
                  id={`exp-company-${index}`}
                  type="text"
                  value={entry.company ?? ""}
                  onChange={(event) =>
                    set(
                      "experience",
                      content.experience.map((item, position) =>
                        position === index ? { ...item, company: event.target.value } : item,
                      ),
                    )
                  }
                />
              </div>
            </div>
            <div className="grid-2">
              <div className="field">
                <label htmlFor={`exp-start-${index}`}>Start</label>
                <input
                  id={`exp-start-${index}`}
                  type="text"
                  value={entry.start_date ?? ""}
                  onChange={(event) =>
                    set(
                      "experience",
                      content.experience.map((item, position) =>
                        position === index ? { ...item, start_date: event.target.value } : item,
                      ),
                    )
                  }
                />
              </div>
              <div className="field">
                <label htmlFor={`exp-end-${index}`}>End</label>
                <input
                  id={`exp-end-${index}`}
                  type="text"
                  value={entry.end_date ?? ""}
                  onChange={(event) =>
                    set(
                      "experience",
                      content.experience.map((item, position) =>
                        position === index ? { ...item, end_date: event.target.value } : item,
                      ),
                    )
                  }
                />
              </div>
            </div>
            <button
              type="button"
              className="small ghost"
              onClick={() =>
                set(
                  "experience",
                  content.experience.filter((_, position) => position !== index),
                )
              }
            >
              Remove this role
            </button>
            <div className="divider" />
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Education</h2>
          <button
            type="button"
            className="small"
            onClick={() => set("education", [...content.education, { ...EMPTY_EDUCATION }])}
          >
            Add entry
          </button>
        </div>
        {content.education.length === 0 && <p className="subtle">No education extracted.</p>}
        {content.education.map((entry, index) => (
          <div key={index} className="grid-2" style={{ marginBottom: "0.75rem" }}>
            <div className="field">
              <label htmlFor={`edu-inst-${index}`}>Institution</label>
              <input
                id={`edu-inst-${index}`}
                type="text"
                value={entry.institution ?? ""}
                onChange={(event) =>
                  set(
                    "education",
                    content.education.map((item, position) =>
                      position === index ? { ...item, institution: event.target.value } : item,
                    ),
                  )
                }
              />
            </div>
            <div className="field">
              <label htmlFor={`edu-degree-${index}`}>Degree</label>
              <input
                id={`edu-degree-${index}`}
                type="text"
                value={entry.degree ?? ""}
                onChange={(event) =>
                  set(
                    "education",
                    content.education.map((item, position) =>
                      position === index ? { ...item, degree: event.target.value } : item,
                    ),
                  )
                }
              />
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Certifications</h2>
          <button
            type="button"
            className="small"
            onClick={() =>
              set("certifications", [...content.certifications, { ...EMPTY_CERTIFICATION }])
            }
          >
            Add certification
          </button>
        </div>
        {content.certifications.length === 0 && <p className="subtle">No certifications extracted.</p>}
        {content.certifications.map((entry, index) => (
          <div key={index} className="grid-2" style={{ marginBottom: "0.75rem" }}>
            <div className="field">
              <label htmlFor={`cert-name-${index}`}>Name</label>
              <input
                id={`cert-name-${index}`}
                type="text"
                value={entry.name}
                onChange={(event) =>
                  set(
                    "certifications",
                    content.certifications.map((item, position) =>
                      position === index ? { ...item, name: event.target.value } : item,
                    ),
                  )
                }
              />
            </div>
            <div className="field">
              <label htmlFor={`cert-issuer-${index}`}>Issuer</label>
              <input
                id={`cert-issuer-${index}`}
                type="text"
                value={entry.issuer ?? ""}
                onChange={(event) =>
                  set(
                    "certifications",
                    content.certifications.map((item, position) =>
                      position === index ? { ...item, issuer: event.target.value } : item,
                    ),
                  )
                }
              />
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="row">
          <button type="button" className="primary" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save changes"}
          </button>
          <button type="button" onClick={reparse} disabled={busy}>
            Re-parse the original file
          </button>
        </div>
      </div>
    </div>
  );
}
