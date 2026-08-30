"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth";

export default function LandingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [user, loading, router]);

  return (
    <div className="page narrow" style={{ paddingTop: "4rem" }}>
      <div className="page-header">
        <h1>Five jobs at a time.</h1>
        <p>
          Endless browsing is the problem, not the solution. This board hands you five roles that
          actually match your eligibility rules and preferences. Apply, skip with a reason, or mark
          one unavailable — resolve all five and the next set unlocks.
        </p>
      </div>
      <div className="card">
        <div className="stack-sm">
          <Link href="/register" className="button button-primary">
            Create an account
          </Link>
          <Link href="/login" className="button">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
