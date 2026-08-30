/** Presentation helpers shared across pages. */

export function formatSalary(
  min: number | null | undefined,
  max: number | null | undefined,
  currency: string | null = "USD",
): string {
  if (!min && !max) return "Not published";
  const symbol = currency === "USD" || !currency ? "$" : `${currency} `;
  const format = (value: number) =>
    value >= 1000 ? `${symbol}${Math.round(value / 1000)}k` : `${symbol}${value}`;
  if (min && max && min !== max) return `${format(min)} – ${format(max)}`;
  return format((max ?? min) as number);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function relativeDays(value: string | null | undefined): string {
  if (!value) return "Date unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unknown";
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days <= 0) return "Posted today";
  if (days === 1) return "Posted yesterday";
  if (days < 30) return `Posted ${days} days ago`;
  const months = Math.floor(days / 30);
  return `Posted ${months} month${months === 1 ? "" : "s"} ago`;
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatLocation(job: {
  work_arrangement?: string | null;
  location?: string | null;
}): string {
  if (job.work_arrangement === "remote") return "Remote";
  if (!job.location) return titleCase(job.work_arrangement ?? null);
  return job.location;
}

/**
 * Location plus work setup, without repeating itself: a remote role reads
 * "Remote", not "Remote · Remote".
 */
export function formatPlace(job: {
  work_arrangement?: string | null;
  location?: string | null;
}): string {
  const place = formatLocation(job);
  const setup = titleCase(job.work_arrangement ?? null);
  return setup === "—" || setup === place ? place : `${place} · ${setup}`;
}

/**
 * Canonical skill names are stored lowercase; these keep the conventional
 * capitalisation when they are shown to a person.
 */
const SKILL_DISPLAY_NAMES: Record<string, string> = {
  aws: "AWS",
  gcp: "GCP",
  sql: "SQL",
  html: "HTML",
  css: "CSS",
  api: "API",
  rest: "REST",
  grpc: "gRPC",
  graphql: "GraphQL",
  postgresql: "PostgreSQL",
  mysql: "MySQL",
  sqlite: "SQLite",
  mongodb: "MongoDB",
  dynamodb: "DynamoDB",
  bigquery: "BigQuery",
  rabbitmq: "RabbitMQ",
  elasticsearch: "Elasticsearch",
  javascript: "JavaScript",
  typescript: "TypeScript",
  "node.js": "Node.js",
  "next.js": "Next.js",
  "c#": "C#",
  "c++": "C++",
  php: "PHP",
  dbt: "dbt",
  pytorch: "PyTorch",
  tensorflow: "TensorFlow",
  "scikit-learn": "scikit-learn",
  numpy: "NumPy",
  fastapi: "FastAPI",
  sqlalchemy: "SQLAlchemy",
  "github actions": "GitHub Actions",
  "gitlab ci": "GitLab CI",
  circleci: "CircleCI",
  jira: "Jira",
  sap: "SAP",
  "power bi": "Power BI",
  ios: "iOS",
};

export function skillLabel(value: string): string {
  const key = value.trim().toLowerCase();
  return SKILL_DISPLAY_NAMES[key] ?? titleCase(value);
}

export function scoreTone(score: number): "strong" | "good" | "fair" | "weak" {
  if (score >= 80) return "strong";
  if (score >= 60) return "good";
  if (score >= 40) return "fair";
  return "weak";
}

export const SKIP_REASONS: Array<{ value: string; label: string; helper: string }> = [
  { value: "not_qualified", label: "Not qualified", helper: "I don't meet the requirements" },
  { value: "already_applied", label: "Already applied", helper: "I applied to this elsewhere" },
  { value: "closed", label: "Listing is closed", helper: "The posting is gone or filled" },
  { value: "location", label: "Location", helper: "The place doesn't work for me" },
  { value: "salary", label: "Salary", helper: "Compensation is too low" },
  { value: "sponsorship", label: "Sponsorship", helper: "They won't sponsor my visa" },
  { value: "clearance", label: "Clearance", helper: "I don't hold the clearance" },
  { value: "experience_level", label: "Experience level", helper: "Wrong seniority for me" },
  { value: "not_interested", label: "Not interested", helper: "Not the work I want" },
];

export const APPLICATION_STATUSES = [
  "todo",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
  "skipped",
  "closed",
] as const;
