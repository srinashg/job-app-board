"use client";

import { CheckboxGroup, TagInput } from "@/components/ui";
import type { Eligibility, Preferences } from "@/lib/types";

export const WORK_ARRANGEMENTS = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
];

export const EXPERIENCE_LEVELS = [
  { value: "intern", label: "Intern" },
  { value: "entry", label: "Entry" },
  { value: "junior", label: "Junior" },
  { value: "mid", label: "Mid" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
  { value: "principal", label: "Principal" },
  { value: "executive", label: "Executive" },
];

export const WORK_AUTHORIZATIONS = [
  { value: "citizen", label: "Citizen" },
  { value: "permanent_resident", label: "Permanent resident" },
  { value: "visa_holder", label: "Visa holder" },
  { value: "needs_sponsorship", label: "Needs sponsorship" },
  { value: "other", label: "Other" },
];

export const CLEARANCES = [
  { value: "none", label: "None" },
  { value: "public_trust", label: "Public trust" },
  { value: "confidential", label: "Confidential" },
  { value: "secret", label: "Secret" },
  { value: "top_secret", label: "Top secret" },
  { value: "ts_sci", label: "TS/SCI" },
];

type PreferencesDraft = Partial<Preferences>;
type EligibilityDraft = Partial<Eligibility>;

/** The filter panel: every field from the preference feature, in one place. */
export function PreferenceFields({
  value,
  onChange,
}: {
  value: PreferencesDraft;
  onChange: (next: PreferencesDraft) => void;
}) {
  const set = <K extends keyof Preferences>(key: K, next: Preferences[K]) =>
    onChange({ ...value, [key]: next });

  return (
    <>
      <CheckboxGroup
        label="Work setup"
        options={WORK_ARRANGEMENTS}
        values={value.work_arrangements ?? []}
        onChange={(next) => set("work_arrangements", next as Preferences["work_arrangements"])}
      />

      <TagInput
        label="Locations"
        values={value.preferred_locations ?? []}
        onChange={(next) => set("preferred_locations", next)}
        placeholder="San Francisco, CA"
        hint="Cities or regions you would work in."
      />

      <div className="field">
        <label htmlFor="radius">Search radius (miles)</label>
        <input
          id="radius"
          type="number"
          min={0}
          max={500}
          value={value.location_radius_miles ?? ""}
          onChange={(event) =>
            set(
              "location_radius_miles",
              event.target.value === "" ? null : Number(event.target.value),
            )
          }
        />
      </div>

      <TagInput
        label="Job titles I want"
        values={value.desired_titles ?? []}
        onChange={(next) => set("desired_titles", next)}
        placeholder="Backend Engineer"
      />

      <TagInput
        label="Title words to exclude"
        values={value.excluded_titles ?? []}
        onChange={(next) => set("excluded_titles", next)}
        placeholder="Manager"
        hint="Any listing whose title contains one of these is filtered out."
      />

      <CheckboxGroup
        label="Experience level"
        options={EXPERIENCE_LEVELS}
        values={value.experience_levels ?? []}
        onChange={(next) => set("experience_levels", next as Preferences["experience_levels"])}
      />

      <TagInput
        label="Technologies"
        values={value.technologies ?? []}
        onChange={(next) => set("technologies", next)}
        placeholder="python"
      />

      <TagInput
        label="Industries"
        values={value.industries ?? []}
        onChange={(next) => set("industries", next)}
        placeholder="fintech"
      />

      <TagInput
        label="Companies to exclude"
        values={value.excluded_companies ?? []}
        onChange={(next) => set("excluded_companies", next)}
        placeholder="Acme Corp"
      />

      <div className="grid-2">
        <div className="field">
          <label htmlFor="min-salary">Minimum salary</label>
          <input
            id="min-salary"
            type="number"
            min={0}
            step={1000}
            value={value.minimum_salary ?? ""}
            onChange={(event) =>
              set("minimum_salary", event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </div>
        <div className="field">
          <label htmlFor="max-age">Posted within (days)</label>
          <input
            id="max-age"
            type="number"
            min={1}
            max={365}
            value={value.max_days_since_posted ?? ""}
            onChange={(event) =>
              set(
                "max_days_since_posted",
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="threshold">
          Minimum match score: {value.match_threshold ?? 0}
        </label>
        <input
          id="threshold"
          type="range"
          min={0}
          max={100}
          step={5}
          value={value.match_threshold ?? 0}
          onChange={(event) => set("match_threshold", Number(event.target.value))}
          style={{ width: "100%" }}
        />
        <div className="field-hint">Jobs scoring below this never enter a batch.</div>
      </div>
    </>
  );
}

/** Hard eligibility rules — these gate a job entirely rather than scoring it. */
export function EligibilityFields({
  value,
  onChange,
}: {
  value: EligibilityDraft;
  onChange: (next: EligibilityDraft) => void;
}) {
  const set = <K extends keyof Eligibility>(key: K, next: Eligibility[K]) =>
    onChange({ ...value, [key]: next });

  return (
    <>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="work-auth">Work authorization</label>
          <select
            id="work-auth"
            value={value.work_authorization ?? "citizen"}
            onChange={(event) =>
              set("work_authorization", event.target.value as Eligibility["work_authorization"])
            }
          >
            {WORK_AUTHORIZATIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="clearance">Security clearance</label>
          <select
            id="clearance"
            value={value.security_clearance ?? "none"}
            onChange={(event) =>
              set("security_clearance", event.target.value as Eligibility["security_clearance"])
            }
          >
            {CLEARANCES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="checkbox-row">
        <input
          id="sponsorship"
          type="checkbox"
          checked={value.requires_sponsorship ?? false}
          onChange={(event) => set("requires_sponsorship", event.target.checked)}
        />
        <label htmlFor="sponsorship">
          I need visa sponsorship — hide roles that state they do not sponsor
        </label>
      </div>

      <div className="checkbox-row">
        <input
          id="relocate"
          type="checkbox"
          checked={value.willing_to_relocate ?? false}
          onChange={(event) => set("willing_to_relocate", event.target.checked)}
        />
        <label htmlFor="relocate">I am willing to relocate</label>
      </div>

      <TagInput
        label="Countries I can work in"
        values={value.authorized_countries ?? []}
        onChange={(next) => set("authorized_countries", next.map((item) => item.toUpperCase()))}
        placeholder="US"
        hint="Two-letter country codes. Leave empty to skip this check."
      />

      <div className="grid-2">
        <div className="field">
          <label htmlFor="elig-salary">Absolute salary floor</label>
          <input
            id="elig-salary"
            type="number"
            min={0}
            step={1000}
            value={value.minimum_salary ?? ""}
            onChange={(event) =>
              set("minimum_salary", event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </div>
        <div className="field">
          <label htmlFor="years">Total years of experience</label>
          <input
            id="years"
            type="number"
            min={0}
            max={70}
            step={0.5}
            value={value.total_years_experience ?? ""}
            onChange={(event) =>
              set(
                "total_years_experience",
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
          />
        </div>
      </div>
    </>
  );
}
