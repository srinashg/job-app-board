/** Types mirroring the backend's v1 schemas. */

export type WorkArrangement = "remote" | "hybrid" | "onsite";

export type ExperienceLevel =
  | "intern"
  | "entry"
  | "junior"
  | "mid"
  | "senior"
  | "lead"
  | "principal"
  | "executive";

export type WorkAuthorization =
  | "citizen"
  | "permanent_resident"
  | "visa_holder"
  | "needs_sponsorship"
  | "other";

export type SecurityClearance =
  | "none"
  | "public_trust"
  | "confidential"
  | "secret"
  | "top_secret"
  | "ts_sci";

export type SkipReason =
  | "not_qualified"
  | "already_applied"
  | "closed"
  | "location"
  | "salary"
  | "sponsorship"
  | "clearance"
  | "experience_level"
  | "not_interested";

export type ApplicationStatus =
  | "todo"
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn"
  | "skipped"
  | "closed";

export type JobStatus = "active" | "closed" | "stale" | "duplicate" | "disabled" | "scam";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: "user" | "admin";
  is_active: boolean;
  is_email_verified: boolean;
  onboarding_completed_at: string | null;
  created_at: string;
}

export interface Profile {
  headline: string | null;
  phone: string | null;
  street_address: string | null;
  city: string | null;
  region: string | null;
  postal_code: string | null;
  country: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  years_of_experience: number | null;
  current_title: string | null;
}

export interface Eligibility {
  work_authorization: WorkAuthorization;
  requires_sponsorship: boolean;
  security_clearance: SecurityClearance;
  willing_to_relocate: boolean;
  authorized_countries: string[];
  minimum_salary: number | null;
  earliest_start_date: string | null;
  total_years_experience: number | null;
}

export interface Preferences {
  work_arrangements: WorkArrangement[];
  preferred_locations: string[];
  location_radius_miles: number | null;
  desired_titles: string[];
  excluded_titles: string[];
  technologies: string[];
  industries: string[];
  excluded_companies: string[];
  experience_levels: ExperienceLevel[];
  minimum_salary: number | null;
  max_days_since_posted: number | null;
  match_threshold: number;
}

export interface OnboardingStatus {
  completed: boolean;
  has_profile: boolean;
  has_eligibility: boolean;
  has_preferences: boolean;
  has_resume: boolean;
  next_step: string | null;
}

export interface ExperienceEntry {
  company: string | null;
  title: string | null;
  start_date: string | null;
  end_date: string | null;
  location: string | null;
  description: string | null;
  is_current: boolean;
}

export interface EducationEntry {
  institution: string | null;
  degree: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
  gpa: string | null;
}

export interface CertificationEntry {
  name: string;
  issuer: string | null;
  issued_date: string | null;
  expires_date: string | null;
  credential_id: string | null;
}

export interface ResumeContent {
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  summary: string | null;
  skills: string[];
  job_titles: string[];
  experience: ExperienceEntry[];
  education: EducationEntry[];
  certifications: CertificationEntry[];
  years_of_experience: number | null;
}

export interface ResumeSummary {
  id: string;
  label: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  version: number;
  is_default: boolean;
  parse_status: string;
  parse_error: string | null;
  parsed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResumeDetail extends ResumeSummary {
  content: ResumeContent;
  raw_text_available: boolean;
}

export interface Company {
  id: string;
  name: string;
  slug: string;
  website: string | null;
  domain: string | null;
  careers_url: string | null;
  industry: string | null;
  size: string | null;
  headquarters: string | null;
  description: string | null;
  is_blacklisted: boolean;
}

export interface JobSummary {
  id: string;
  title: string;
  location: string | null;
  work_arrangement: WorkArrangement | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  experience_level: ExperienceLevel | null;
  technologies: string[];
  date_posted: string | null;
  source_url: string;
  status: JobStatus;
  last_verified_at: string | null;
  company: Company;
}

export interface JobDetail extends JobSummary {
  description: string;
  description_snapshot: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  postal_code: string | null;
  street_address: string | null;
  min_years_experience: number | null;
  required_skills: string[];
  preferred_skills: string[];
  industry: string | null;
  requires_clearance: string | null;
  sponsorship_available: boolean | null;
  citizenship_required: boolean;
  apply_url: string | null;
  first_seen_at: string;
  last_checked_at: string | null;
  duplicate_of_id: string | null;
}

export type QualificationKind = "strong" | "partial" | "missing";

export interface Qualification {
  kind: QualificationKind;
  category: string;
  label: string;
  detail: string | null;
}

export interface ComponentScore {
  name: string;
  score: number;
  weight: number;
  detail: string | null;
}

export interface MatchResult {
  score: number;
  eligible: boolean;
  blocking_reasons: string[];
  strong: Qualification[];
  partial: Qualification[];
  missing: Qualification[];
  components: ComponentScore[];
  summary: string;
}

export interface Recommendation {
  id: string;
  job_id: string;
  batch_id: string | null;
  position: number;
  status: string;
  match_score: number;
  skip_reason: SkipReason | null;
  skip_note: string | null;
  resolved_at: string | null;
  job: JobSummary;
  match_explanation: MatchResult | null;
}

export interface Batch {
  id: string;
  sequence: number;
  size: number;
  status: string;
  completed_at: string | null;
  created_at: string;
  recommendations: Recommendation[];
  resolved_count: number;
  is_complete: boolean;
}

export interface BatchState {
  batch: Batch | null;
  can_unlock_next: boolean;
  remaining: number;
  exhausted: boolean;
  message: string | null;
}

export interface JobDetailResponse {
  job: JobDetail;
  match: MatchResult | null;
  recommendation_id: string | null;
  recommendation_status: string | null;
  is_saved: boolean;
  already_applied: boolean;
}

export interface Contact {
  id: string;
  name: string;
  title: string | null;
  company_name: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  notes: string | null;
}

export interface ApplicationEvent {
  id: string;
  from_status: ApplicationStatus | null;
  to_status: ApplicationStatus;
  note: string | null;
  occurred_at: string;
}

export interface Application {
  id: string;
  job_id: string | null;
  resume_id: string | null;
  contact_id: string | null;
  company_name: string;
  position_title: string;
  location: string | null;
  work_arrangement: WorkArrangement | null;
  work_address: string | null;
  application_url: string | null;
  status: ApplicationStatus;
  applied_at: string | null;
  first_response_at: string | null;
  closed_at: string | null;
  match_score: number | null;
  notes: string | null;
  salary_min: number | null;
  salary_max: number | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationDetail extends Application {
  job_description_snapshot: string | null;
  events: ApplicationEvent[];
  contact: Contact | null;
}

export interface StatusCount {
  status: ApplicationStatus;
  count: number;
}

export interface DashboardStats {
  total_applications: number;
  applied: number;
  responses: number;
  interviews: number;
  offers: number;
  rejections: number;
  withdrawn: number;
  closed: number;
  skipped: number;
  todo: number;
  in_pipeline: number;
  response_rate: number;
  interview_rate: number;
  offer_rate: number;
  pipeline_by_status: StatusCount[];
  applications_last_7_days: number;
  applications_last_30_days: number;
  jobs_skipped: number;
  active_batch_remaining: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminJobRow {
  id: string;
  title: string;
  company_name: string;
  company_slug: string;
  company_domain: string | null;
  location: string | null;
  status: JobStatus;
  source_type: string | null;
  source_url: string;
  date_posted: string | null;
  last_verified_at: string | null;
  verification_failures: number;
  duplicate_of_id: string | null;
  recommendation_count: number;
  moderation_notes: string | null;
}

export interface AdminStats {
  total_jobs: number;
  active_jobs: number;
  closed_jobs: number;
  stale_jobs: number;
  duplicate_jobs: number;
  disabled_jobs: number;
  scam_jobs: number;
  total_companies: number;
  blacklisted_companies: number;
  total_sources: number;
  enabled_sources: number;
  total_users: number;
}

export interface BlacklistEntry {
  id: string;
  scope: "company" | "domain" | "job";
  value: string;
  reason: string | null;
  created_at: string;
}

export interface JobSource {
  id: string;
  name: string;
  source_type: string;
  external_slug: string;
  base_url: string | null;
  is_enabled: boolean;
  last_fetched_at: string | null;
  last_fetch_status: string | null;
  last_fetch_error: string | null;
  jobs_seen: number;
}

export interface PrivacySummary {
  resume_count: number;
  stored_resume_files: number;
  application_count: number;
  contact_count: number;
  consents: Array<{ consent_type: string; granted: boolean; recorded_at: string }>;
  deletion_requested_at: string | null;
}
