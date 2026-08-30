"use client";

import { useState } from "react";

import { Modal } from "@/components/ui";
import { SKIP_REASONS } from "@/lib/format";
import type { SkipReason } from "@/lib/types";

export function SkipDialog({
  jobTitle,
  onCancel,
  onConfirm,
}: {
  jobTitle: string;
  onCancel: () => void;
  onConfirm: (reason: SkipReason, note: string) => void;
}) {
  const [reason, setReason] = useState<SkipReason>("not_interested");
  const [note, setNote] = useState("");

  return (
    <Modal title={`Skip “${jobTitle}”`} onClose={onCancel}>
      <p className="subtle">
        Telling us why keeps the rest of your recommendations honest. Skipping as already applied
        or closed pulls a replacement job into this batch.
      </p>
      <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
        <legend className="sr-only" style={{ position: "absolute", left: "-9999px" }}>
          Skip reason
        </legend>
        {SKIP_REASONS.map((option) => (
          <div className="checkbox-row" key={option.value}>
            <input
              type="radio"
              id={`skip-${option.value}`}
              name="skip-reason"
              value={option.value}
              checked={reason === option.value}
              onChange={() => setReason(option.value as SkipReason)}
            />
            <label htmlFor={`skip-${option.value}`}>
              {option.label}
              <span className="subtle"> — {option.helper}</span>
            </label>
          </div>
        ))}
      </fieldset>

      <div className="field" style={{ marginTop: "0.75rem" }}>
        <label htmlFor="skip-note">Note (optional)</label>
        <textarea
          id="skip-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Anything you want to remember about this one"
        />
      </div>

      <div className="row-between">
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="primary" onClick={() => onConfirm(reason, note)}>
          Skip this job
        </button>
      </div>
    </Modal>
  );
}
