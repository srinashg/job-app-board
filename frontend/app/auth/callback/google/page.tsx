"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert, Loading } from "@/components/ui";
import { api, tokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function Callback() {
  const params = useSearchParams();
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");
    const denied = params.get("error");

    if (denied) {
      setError(`Google sign-in was cancelled (${denied}).`);
      return;
    }
    if (!code) {
      setError("Google did not return an authorization code.");
      return;
    }

    const expected = window.sessionStorage.getItem("jab.oauth_state");
    if (expected && state && expected !== state) {
      // A mismatched state means the response did not come from the request
      // this browser started, so it must not be exchanged.
      setError("The sign-in response could not be verified. Please try again.");
      return;
    }

    void (async () => {
      try {
        tokens.save(await api.oauthCallback("google", code, state ?? undefined));
        window.sessionStorage.removeItem("jab.oauth_state");
        await refreshUser();
        router.replace("/dashboard");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Google sign-in failed");
      }
    })();
  }, [params, router, refreshUser]);

  return (
    <div className="page narrow" style={{ paddingTop: "4rem" }}>
      <div className="card">
        {error ? (
          <>
            <Alert kind="error">{error}</Alert>
            <button type="button" onClick={() => router.push("/login")}>
              Back to sign in
            </button>
          </>
        ) : (
          <Loading label="Completing sign-in…" />
        )}
      </div>
    </div>
  );
}

export default function GoogleCallbackPage() {
  return (
    <Suspense fallback={<div className="page narrow" style={{ paddingTop: "4rem" }}><Loading /></div>}>
      <Callback />
    </Suspense>
  );
}
