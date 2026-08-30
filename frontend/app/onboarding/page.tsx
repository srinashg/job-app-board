"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EligibilityFields, PreferenceFields } from "@/components/PreferenceFields";
import { Alert, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth, useRequireAuth } from "@/lib/auth";
import type { Eligibility, Preferences, Profile } from "@/lib/types";

const STEPS = ["Profile", "Eligibility", "Preferences", "Resume"] as const;

export default function OnboardingPage() {
  const { loading } = useRequireAuth();
  const { refreshUser } = useAuth();
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<Partial<Profile>>({});
  const [eligibility, setEligibility] = useState<Partial<Eligibility>>({});
  const [preferences, setPreferences] = useState<Partial<Preferences>>({});
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (loading) return;
    void (async () => {
      try {
        const [existingProfile, existingEligibility, existingPreferences] = await Promise.all([
          api.profile(),
          api.eligibility(),
          api.preferences(),
        ]);
        setProfile(existingProfile);
        setEligibility(existingEligibility);
        setPreferences(existingPreferences);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not load your details");
      } finally {
        setReady(true);
      }
    })();
  }, [loading]);

  const finish = async () => {
    setError("");
    setBusy(true);
    try {
      if (resumeFile) {
        await api.uploadResume(resumeFile, resumeFile.name, true);
      }
      await api.completeOnboarding({
        profile,
        eligibility,
        preferences,
        consents: [{ consent_type: "resume_processing", granted: true }],
      });
      await refreshUser();
      router.push("/jobs");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save your setup");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !ready) {
    return (
      <div className="page medium">
        <Loading />
      </div>
    );
  }

  return (
    <div className="page medium">
      <div className="page-header">
        <h1>Set up your search</h1>
        <p>
          These answers decide which jobs you are ever shown. Eligibility rules filter roles out
          entirely; preferences change how they rank.
        </p>
      </div>

      <div className="row" style={{ marginBottom: "1rem" }}>
        {STEPS.map((label, index) => (
          <span key={label} className={`badge ${index === step ? "badge-accent" : ""}`}>
            {index + 1}. {label}
          </span>
        ))}
      </div>

      <div className="card">
        <Alert kind="error">{error}</Alert>

        {step === 0 && (
          <>
            <h2>About you</h2>
            <p className="subtle">Used to rank roles by location and seniority.</p>
            <div className="field">
              <label htmlFor="current-title">Current or target job title</label>
              <input
                id="current-title"
                type="text"
                value={profile.current_title ?? ""}
                onChange={(event) => setProfile({ ...profile, current_title: event.target.value })}
              />
            </div>
            <div className="grid-2">
              <div className="field">
                <label htmlFor="city">City</label>
                <input
                  id="city"
                  type="text"
                  value={profile.city ?? ""}
                  onChange={(event) => setProfile({ ...profile, city: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="region">State or region</label>
                <input
                  id="region"
                  type="text"
                  value={profile.region ?? ""}
                  onChange={(event) => setProfile({ ...profile, region: event.target.value })}
                />
              </div>
            </div>
            <div className="grid-2">
              <div className="field">
                <label htmlFor="postal">Postal code</label>
                <input
                  id="postal"
                  type="text"
                  value={profile.postal_code ?? ""}
                  onChange={(event) => setProfile({ ...profile, postal_code: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="country">Country code</label>
                <input
                  id="country"
                  type="text"
                  maxLength={2}
                  value={profile.country ?? ""}
                  onChange={(event) =>
                    setProfile({ ...profile, country: event.target.value.toUpperCase() })
                  }
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="phone">Phone (stored encrypted)</label>
              <input
                id="phone"
                type="text"
                value={profile.phone ?? ""}
                onChange={(event) => setProfile({ ...profile, phone: event.target.value })}
              />
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <h2>Eligibility rules</h2>
            <p className="subtle">
              A job that fails any of these is never recommended, whatever its match score.
            </p>
            <EligibilityFields value={eligibility} onChange={setEligibility} />
          </>
        )}

        {step === 2 && (
          <>
            <h2>What you are looking for</h2>
            <p className="subtle">You can change all of this later from the Filters page.</p>
            <PreferenceFields value={preferences} onChange={setPreferences} />
          </>
        )}

        {step === 3 && (
          <>
            <h2>Upload your resume</h2>
            <p className="subtle">
              We extract your skills, experience, education, certifications and job titles. You can
              correct anything we get wrong before it is used for matching.
            </p>
            <div className="field">
              <label htmlFor="resume">Resume file (PDF, DOCX or text)</label>
              <input
                id="resume"
                type="file"
                accept=".pdf,.docx,.txt,.md"
                onChange={(event) => setResumeFile(event.target.files?.[0] ?? null)}
              />
              <div className="field-hint">
                Optional — you can add one later, but matching is much better with it.
              </div>
            </div>
          </>
        )}

        <div className="divider" />
        <div className="row-between">
          <button type="button" onClick={() => setStep((current) => current - 1)} disabled={step === 0}>
            Back
          </button>
          {step < STEPS.length - 1 ? (
            <button type="button" className="primary" onClick={() => setStep((current) => current + 1)}>
              Continue
            </button>
          ) : (
            <button type="button" className="primary" onClick={finish} disabled={busy}>
              {busy ? "Saving…" : "Finish setup"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
