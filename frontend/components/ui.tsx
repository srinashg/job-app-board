"use client";

import type { ReactNode } from "react";

import { scoreTone, skillLabel, titleCase } from "@/lib/format";
import type { MatchResult, Qualification } from "@/lib/types";

export function Alert({
  kind = "info",
  children,
}: {
  kind?: "info" | "error" | "success";
  children: ReactNode;
}) {
  if (!children) return null;
  return <div className={`alert alert-${kind}`} role={kind === "error" ? "alert" : undefined}>{children}</div>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="stack-sm" aria-live="polite" aria-busy="true">
      <span className="subtle">{label}</span>
      <div className="skeleton" style={{ width: "70%" }} />
      <div className="skeleton" style={{ width: "90%" }} />
      <div className="skeleton" style={{ width: "55%" }} />
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children ? <p className="muted">{children}</p> : null}
      {action}
    </div>
  );
}

export function ScoreBadge({ score }: { score: number }) {
  return (
    <div className={`score score-${scoreTone(score)}`} title={`Match score ${score} out of 100`}>
      {score}
      <span>match</span>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "offer" || status === "active"
      ? "badge-strong"
      : status === "interview" || status === "applied"
        ? "badge-accent"
        : status === "rejected" || status === "scam" || status === "disabled"
          ? "badge-missing"
          : status === "stale" || status === "duplicate" || status === "closed"
            ? "badge-partial"
            : "";
  return <span className={`badge ${tone}`}>{titleCase(status)}</span>;
}

const MARKS: Record<string, string> = { strong: "✓", partial: "~", missing: "✕" };

export function QualificationList({ items }: { items: Qualification[] }) {
  if (!items.length) return <p className="subtle">Nothing here.</p>;
  return (
    <ul className="qual-list">
      {items.map((item, index) => (
        <li key={`${item.category}-${item.label}-${index}`} className={`qual qual-${item.kind}`}>
          <span className="qual-mark" aria-hidden="true">
            {MARKS[item.kind]}
          </span>
          <span>
            <strong>{skillLabel(item.label)}</strong>
            {item.detail ? <span className="qual-detail"> — {item.detail}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The full match explanation: score, gates, and the three qualification groups. */
export function MatchExplanation({ match }: { match: MatchResult }) {
  return (
    <div className="stack">
      <div className="row">
        <ScoreBadge score={match.score} />
        <div>
          <strong>{match.summary}</strong>
          <div className="subtle">
            {match.strong.length} strong · {match.partial.length} partial ·{" "}
            {match.missing.length} missing
          </div>
        </div>
      </div>

      {match.blocking_reasons.length > 0 && (
        <Alert kind="error">
          <strong>Not eligible</strong>
          <ul style={{ margin: "0.35rem 0 0 1rem", padding: 0 }}>
            {match.blocking_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </Alert>
      )}

      <div>
        <h4 className="muted" style={{ fontSize: "0.8rem", textTransform: "uppercase" }}>
          Strong qualifications
        </h4>
        <QualificationList items={match.strong} />
      </div>

      {match.partial.length > 0 && (
        <div>
          <h4 className="muted" style={{ fontSize: "0.8rem", textTransform: "uppercase" }}>
            Partial qualifications
          </h4>
          <QualificationList items={match.partial} />
        </div>
      )}

      <div>
        <h4 className="muted" style={{ fontSize: "0.8rem", textTransform: "uppercase" }}>
          Missing qualifications
        </h4>
        <QualificationList items={match.missing} />
      </div>

      <details>
        <summary className="subtle" style={{ cursor: "pointer" }}>
          How this score was calculated
        </summary>
        <div className="table-wrap" style={{ marginTop: "0.5rem" }}>
          <table>
            <thead>
              <tr>
                <th>Signal</th>
                <th>Score</th>
                <th>Weight</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {match.components.map((component) => (
                <tr key={component.name}>
                  <td>{titleCase(component.name)}</td>
                  <td>{Math.round(component.score * 100)}%</td>
                  <td>{component.weight === 0 ? "—" : `${Math.round(component.weight * 100)}%`}</td>
                  <td className="subtle">
                    {component.detail === "no-signal" ? "Not enough data" : component.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

/** Editable list of free-text values, rendered as removable chips. */
export function TagInput({
  label,
  values,
  onChange,
  placeholder,
  hint,
}: {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  hint?: string;
}) {
  const add = (raw: string) => {
    const value = raw.trim();
    if (!value || values.some((item) => item.toLowerCase() === value.toLowerCase())) return;
    onChange([...values, value]);
  };

  return (
    <div className="field">
      <label htmlFor={`tag-${label}`}>{label}</label>
      <input
        id={`tag-${label}`}
        type="text"
        placeholder={placeholder ?? "Type and press Enter"}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            add(event.currentTarget.value);
            event.currentTarget.value = "";
          }
        }}
        onBlur={(event) => {
          add(event.currentTarget.value);
          event.currentTarget.value = "";
        }}
      />
      {hint ? <div className="field-hint">{hint}</div> : null}
      {values.length > 0 && (
        <div className="chip-list" style={{ marginTop: "0.45rem" }}>
          {values.map((value) => (
            <span key={value} className="chip">
              {value}
              <button
                type="button"
                aria-label={`Remove ${value}`}
                onClick={() => onChange(values.filter((item) => item !== value))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function CheckboxGroup({
  label,
  options,
  values,
  onChange,
}: {
  label: string;
  options: Array<{ value: string; label: string }>;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <fieldset className="field" style={{ border: 0, margin: 0, padding: 0 }}>
      <legend style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-muted)", padding: 0 }}>
        {label}
      </legend>
      <div style={{ marginTop: "0.4rem" }}>
        {options.map((option) => (
          <div className="checkbox-row" key={option.value}>
            <input
              type="checkbox"
              id={`${label}-${option.value}`}
              checked={values.includes(option.value)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...values, option.value]
                    : values.filter((item) => item !== option.value),
                )
              }
            />
            <label htmlFor={`${label}-${option.value}`}>{option.label}</label>
          </div>
        ))}
      </div>
    </fieldset>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="modal">
        <div className="card-header">
          <h3>{title}</h3>
          <button type="button" className="ghost small" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
