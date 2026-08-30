"use client";

/**
 * Typed client for the backend REST API.
 *
 * Tokens live in localStorage. When an access token expires the client
 * transparently refreshes once and replays the request; if that fails the
 * session is cleared and the caller sees an `UnauthorizedError`.
 */

import type {
  AdminJobRow,
  AdminStats,
  Application,
  ApplicationDetail,
  ApplicationStatus,
  BatchState,
  BlacklistEntry,
  Contact,
  DashboardStats,
  Eligibility,
  JobDetailResponse,
  JobSource,
  JobSummary,
  OnboardingStatus,
  Page,
  Preferences,
  PrivacySummary,
  Profile,
  Recommendation,
  ResumeDetail,
  ResumeSummary,
  SkipReason,
  TokenPair,
  User,
} from "./types";

/**
 * Base URL of the backend. `NEXT_PUBLIC_*` values are inlined at build time,
 * so this must be set when the frontend is built (see the Docker build arg).
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ACCESS_TOKEN_KEY = "jab.access_token";
const REFRESH_TOKEN_KEY = "jab.refresh_token";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class UnauthorizedError extends ApiError {
  constructor(message = "Your session has expired. Please sign in again.") {
    super(message, 401);
    this.name = "UnauthorizedError";
  }
}

export const tokens = {
  get access(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  get refresh(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  save(pair: TokenPair) {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACCESS_TOKEN_KEY, pair.access_token);
    window.localStorage.setItem(REFRESH_TOKEN_KEY, pair.refresh_token);
  },
  clear() {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

/** Turn a FastAPI error body into a single readable sentence. */
function readDetail(body: unknown, fallback: string): string {
  if (typeof body === "string" && body) return body;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            const location = Array.isArray((item as { loc?: unknown[] }).loc)
              ? ((item as { loc: unknown[] }).loc.slice(-1)[0] as string)
              : null;
            const message = String((item as { msg: unknown }).msg);
            return location ? `${location}: ${message}` : message;
          }
          return String(item);
        })
        .filter(Boolean);
      if (messages.length) return messages.join("; ");
    }
  }
  return fallback;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Set for endpoints that must not trigger the refresh-and-replay path. */
  skipAuth?: boolean;
}

async function refreshSession(): Promise<boolean> {
  const refreshToken = tokens.refresh;
  if (!refreshToken) return false;
  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;
  tokens.save((await response.json()) as TokenPair);
  return true;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuth, headers, ...rest } = options;

  const send = async (): Promise<Response> => {
    const finalHeaders = new Headers(headers);
    const isFormData = body instanceof FormData;
    if (body !== undefined && !isFormData) {
      finalHeaders.set("Content-Type", "application/json");
    }
    if (!skipAuth) {
      const accessToken = tokens.access;
      if (accessToken) finalHeaders.set("Authorization", `Bearer ${accessToken}`);
    }
    return fetch(`${API_URL}${path}`, {
      ...rest,
      headers: finalHeaders,
      body: isFormData ? body : body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let response = await send();

  if (response.status === 401 && !skipAuth && tokens.refresh) {
    if (await refreshSession()) {
      response = await send();
    }
  }

  if (response.status === 401) {
    if (!skipAuth) tokens.clear();
    throw new UnauthorizedError();
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text();

  if (!response.ok) {
    throw new ApiError(
      readDetail(payload, `Request failed (${response.status})`),
      response.status,
      payload,
    );
  }
  return payload as T;
}

const query = (params: Record<string, unknown>): string => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      value.forEach((item) => search.append(key, String(item)));
    } else {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
};

export const api = {
  // --- Auth (feature 1) -------------------------------------------------
  register: (payload: {
    email: string;
    password: string;
    full_name?: string;
    accepted_terms: boolean;
  }) =>
    request<TokenPair>("/api/v1/auth/register", {
      method: "POST",
      body: payload,
      skipAuth: true,
    }),

  login: (email: string, password: string) =>
    request<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      skipAuth: true,
    }),

  oauthAuthorize: (provider: string) =>
    request<{ authorization_url: string; state: string }>(
      `/api/v1/auth/oauth/${provider}/authorize`,
      { skipAuth: true },
    ),

  oauthCallback: (provider: string, code: string, state?: string) =>
    request<TokenPair>(`/api/v1/auth/oauth/${provider}/callback`, {
      method: "POST",
      body: { code, state },
      skipAuth: true,
    }),

  changePassword: (current_password: string, new_password: string) =>
    request<{ detail: string }>("/api/v1/auth/password", {
      method: "POST",
      body: { current_password, new_password },
    }),

  me: () => request<User>("/api/v1/me"),
  updateAccount: (payload: { full_name?: string }) =>
    request<User>("/api/v1/me", { method: "PATCH", body: payload }),

  profile: () => request<Profile>("/api/v1/me/profile"),
  saveProfile: (payload: Partial<Profile>) =>
    request<Profile>("/api/v1/me/profile", { method: "PUT", body: payload }),

  eligibility: () => request<Eligibility>("/api/v1/me/eligibility"),
  saveEligibility: (payload: Partial<Eligibility>) =>
    request<Eligibility>("/api/v1/me/eligibility", { method: "PUT", body: payload }),

  preferences: () => request<Preferences>("/api/v1/me/preferences"),
  savePreferences: (payload: Partial<Preferences>) =>
    request<Preferences>("/api/v1/me/preferences", { method: "PUT", body: payload }),

  consents: () =>
    request<Array<{ id: string; consent_type: string; granted: boolean; recorded_at: string }>>(
      "/api/v1/me/consents",
    ),
  recordConsent: (consent_type: string, granted: boolean) =>
    request<unknown>("/api/v1/me/consents", {
      method: "POST",
      body: { consent_type, granted },
    }),

  onboardingStatus: () => request<OnboardingStatus>("/api/v1/me/onboarding"),
  completeOnboarding: (payload: {
    profile?: Partial<Profile>;
    eligibility?: Partial<Eligibility>;
    preferences?: Partial<Preferences>;
    consents?: Array<{ consent_type: string; granted: boolean }>;
  }) => request<OnboardingStatus>("/api/v1/me/onboarding", { method: "POST", body: payload }),

  // --- Resumes (features 2, 3) -----------------------------------------
  resumes: () => request<ResumeSummary[]>("/api/v1/resumes"),
  resume: (id: string) => request<ResumeDetail>(`/api/v1/resumes/${id}`),
  uploadResume: (file: File, label?: string, makeDefault = false) => {
    const form = new FormData();
    form.append("file", file);
    if (label) form.append("label", label);
    form.append("make_default", String(makeDefault));
    return request<ResumeDetail>("/api/v1/resumes", { method: "POST", body: form });
  },
  renameResume: (id: string, label: string) =>
    request<ResumeDetail>(`/api/v1/resumes/${id}`, { method: "PATCH", body: { label } }),
  saveResumeContent: (id: string, content: Record<string, unknown>) =>
    request<ResumeDetail>(`/api/v1/resumes/${id}/content`, { method: "PUT", body: content }),
  reparseResume: (id: string) =>
    request<ResumeDetail>(`/api/v1/resumes/${id}/reparse`, { method: "POST" }),
  setDefaultResume: (id: string) =>
    request<ResumeDetail>(`/api/v1/resumes/${id}/default`, { method: "POST" }),
  deleteResume: (id: string) =>
    request<{ detail: string }>(`/api/v1/resumes/${id}`, { method: "DELETE" }),

  // --- Jobs (features 4, 10) -------------------------------------------
  jobs: (params: {
    q?: string;
    company?: string;
    work_arrangement?: string;
    min_salary?: number;
    status?: string;
    limit?: number;
    offset?: number;
  } = {}) => request<Page<JobSummary>>(`/api/v1/jobs${query(params)}`),
  job: (id: string) => request<JobDetailResponse>(`/api/v1/jobs/${id}`),

  // --- Batches and skips (features 7, 8) -------------------------------
  currentBatch: () => request<BatchState>("/api/v1/batches/current"),
  nextBatch: () => request<BatchState>("/api/v1/batches/next", { method: "POST" }),
  rebuildBatch: () => request<BatchState>("/api/v1/batches/current", { method: "DELETE" }),
  batchHistory: () => request<import("./types").Batch[]>("/api/v1/batches/history"),
  previewMatches: () => request<Recommendation[]>("/api/v1/batches/preview"),
  savedJobs: () => request<Recommendation[]>("/api/v1/batches/saved"),

  applyToRecommendation: (
    id: string,
    payload: { resume_id?: string; application_url?: string; notes?: string } = {},
  ) =>
    request<Application>(`/api/v1/batches/recommendations/${id}/apply`, {
      method: "POST",
      body: payload,
    }),
  skipRecommendation: (id: string, reason: SkipReason, note?: string) =>
    request<BatchState>(`/api/v1/batches/recommendations/${id}/skip`, {
      method: "POST",
      body: { reason, note },
    }),
  saveRecommendation: (id: string) =>
    request<Recommendation>(`/api/v1/batches/recommendations/${id}/save`, { method: "POST" }),
  unsaveRecommendation: (id: string) =>
    request<Recommendation>(`/api/v1/batches/recommendations/${id}/unsave`, { method: "POST" }),

  // --- Applications (features 11, 12, 13) ------------------------------
  applications: (params: { status?: string[]; q?: string; limit?: number; offset?: number } = {}) =>
    request<Page<Application>>(`/api/v1/applications${query(params)}`),
  application: (id: string) => request<ApplicationDetail>(`/api/v1/applications/${id}`),
  createApplication: (payload: Record<string, unknown>) =>
    request<ApplicationDetail>("/api/v1/applications", { method: "POST", body: payload }),
  updateApplication: (id: string, payload: Record<string, unknown>) =>
    request<ApplicationDetail>(`/api/v1/applications/${id}`, { method: "PATCH", body: payload }),
  setApplicationStatus: (id: string, status: ApplicationStatus, note?: string) =>
    request<ApplicationDetail>(`/api/v1/applications/${id}/status`, {
      method: "POST",
      body: { status, note },
    }),
  deleteApplication: (id: string) =>
    request<{ detail: string }>(`/api/v1/applications/${id}`, { method: "DELETE" }),

  contacts: () => request<Contact[]>("/api/v1/contacts"),
  createContact: (payload: Partial<Contact>) =>
    request<Contact>("/api/v1/contacts", { method: "POST", body: payload }),
  deleteContact: (id: string) =>
    request<{ detail: string }>(`/api/v1/contacts/${id}`, { method: "DELETE" }),

  dashboard: () => request<DashboardStats>("/api/v1/dashboard"),

  // --- Privacy (feature 15) --------------------------------------------
  privacySummary: () => request<PrivacySummary>("/api/v1/privacy/summary"),
  exportData: () => request<Record<string, unknown>>("/api/v1/privacy/export"),
  deleteAllResumes: () =>
    request<{ detail: string }>("/api/v1/privacy/resumes", { method: "DELETE" }),
  deleteAccount: (confirmation: string, password?: string) =>
    request<{ detail: string }>("/api/v1/privacy/account", {
      method: "DELETE",
      body: { confirmation, password },
    }),

  // --- Admin (feature 14) ----------------------------------------------
  adminJobs: (params: { q?: string; status?: string; limit?: number; offset?: number } = {}) =>
    request<Page<AdminJobRow>>(`/api/v1/admin/jobs${query(params)}`),
  adminAction: (payload: {
    job_ids: string[];
    action: string;
    duplicate_of_id?: string;
    notes?: string;
  }) =>
    request<{ updated: number; action: string }>("/api/v1/admin/jobs/actions", {
      method: "POST",
      body: payload,
    }),
  adminStats: () => request<AdminStats>("/api/v1/admin/stats"),
  blacklists: () => request<BlacklistEntry[]>("/api/v1/admin/blacklists"),
  addBlacklist: (payload: { scope: string; value: string; reason?: string }) =>
    request<BlacklistEntry>("/api/v1/admin/blacklists", { method: "POST", body: payload }),
  removeBlacklist: (id: string) =>
    request<{ detail: string }>(`/api/v1/admin/blacklists/${id}`, { method: "DELETE" }),
  sources: () => request<JobSource[]>("/api/v1/admin/sources"),
  seedSources: () =>
    request<{ detail: string }>("/api/v1/admin/sources/seed", { method: "POST" }),
  runIngest: (limit_per_source = 100) =>
    request<{
      sources_run: number;
      jobs_fetched: number;
      jobs_created: number;
      jobs_updated: number;
      duplicates_detected: number;
      errors: string[];
    }>("/api/v1/admin/ingest", { method: "POST", body: { limit_per_source } }),
  runFreshness: (limit = 50) =>
    request<{
      checked: number;
      still_open: number;
      marked_closed: number;
      marked_stale: number;
      errors: string[];
    }>("/api/v1/admin/freshness", { method: "POST", body: { limit } }),
};
