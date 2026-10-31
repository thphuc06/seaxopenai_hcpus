// Documented contract baseline; reconcile optional extensions with P4 at Sync 0.
export type FieldKey = 'volume' | 'skin_type' | 'key_ingredients' | 'notification_number' | 'responsible_company';
export type Verdict = 'CONSISTENT' | 'CONFLICTING' | 'SINGLE_SOURCE' | 'INSUFFICIENT' | 'UNCERTAIN' | 'NOT_APPLICABLE';
export type ConflictLocus = 'WITHIN_SOURCE' | 'ACROSS_SOURCES' | 'LISTING_VS_SOURCE';
export type Freshness = 'CURRENT' | 'STALE' | 'UNKNOWN';
export type ReviewState = 'AUTO_DRAFT' | 'NEEDS_REVIEW' | 'REVIEWED' | 'SUPERSEDED';
export type ScopeMatch = 'MATCH' | 'MISMATCH' | 'UNKNOWN';
export type Readability = 'READABLE' | 'PARTIAL' | 'UNREADABLE';
export type EvidenceLevel = 'LISTING' | 'PRODUCT_VERSION' | 'BATCH' | 'UNIT';
export type DatasetOrigin = 'REAL' | 'SYNTHETIC';
export type ExecutionMode = 'LIVE' | 'REPLAY' | 'FALLBACK';
export type SourceKind = 'LISTING' | 'BRAND_PAGE' | 'NOTIFICATION_DOC' | 'PACKAGING_IMAGE' | 'SELLER_UPLOAD' | 'REGISTRY_RECORD' | 'WEB_PAGE';
export type SourceStatus = 'ACTIVE' | 'SUPERSEDED' | 'REVOKED' | 'UNAVAILABLE';
export type RunStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'PARTIAL' | 'WAITING_EVIDENCE' | 'WAITING_REVIEW' | 'FAILED' | 'CANCELLED';
export type Role = 'BUYER' | 'SELLER' | 'REVIEWER' | 'OPERATOR' | 'SYSTEM';
export type DemoRole = Exclude<Role, 'SYSTEM'>;
export type Visibility = 'PUBLIC' | 'PRIVATE';
export type SkinType = 'DRY' | 'NORMAL' | 'OILY' | 'COMBINATION' | 'SENSITIVE' | 'ACNE_PRONE' | 'ALL';
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface Citation {
  passage_id: string;
  source_kind: SourceKind;
  source_version: number;
  locator: string;
  excerpt: string;
}

export interface PassportField {
  field_key: FieldKey;
  label: string;
  public_text: string;
  verdict: Verdict | null;
  conflict_locus: ConflictLocus | null;
  freshness: Freshness;
  review_state: ReviewState;
  checked_at: string | null;
  citations: Citation[];
  hidden_citations?: number;
  claims_under_review?: number;
}

export interface PassportResponse {
  product_id: string;
  dataset_origin: DatasetOrigin;
  last_checked_at: string | null;
  run_status: RunStatus | null;
  fields: PassportField[];
  disclaimer: string;
  llm_mode?: ExecutionMode;
}

export interface ClaimFinding {
  field_key: `claim:${string}:${string}`;
  verdict: Verdict;
  conflict_locus: ConflictLocus | null;
  review_state: ReviewState;
  seller_attributable: boolean;
  public_text: string;
  citations: Citation[];
}

export type EventType = 'BOOTSTRAP' | 'LISTING_CHANGED' | 'SOURCE_CHANGED' | 'EVIDENCE_ADDED' | 'SOURCE_REVOKED' | 'WEB_SEARCH_REQUESTED';
export interface EventEnvelope {
  event_id: string;
  idempotency_key: string;
  type: EventType;
  schema_version: string;
  producer: string;
  resource: { kind: 'LISTING' | 'SOURCE' | 'CASE'; id: string; version: number };
  changed_fields: string[];
  payload: Record<string, JsonValue>;
  occurred_at: string;
  correlation_id: string;
}
export interface AdmitResult {
  event_id: string;
  outcome: 'ADMITTED' | 'NOOP' | 'DUPLICATE' | 'REJECTED';
  reason: string;
  job_id: string | null;
  stale_fields: FieldKey[];
}
export interface BudgetMeter { used: number; cap: number }
export interface TraceDetail {
  replayed?: boolean;
  model?: string;
  prompt_version?: string;
  stop_reason?: string | null;
  budget?: { model_calls?: BudgetMeter; tool_calls?: BudgetMeter; seconds?: BudgetMeter };
  before?: JsonValue;
  after?: JsonValue;
}
export interface TraceStep {
  id: string;
  run_id: string;
  seq: number;
  step: string;
  actor: 'code' | 'llm' | 'human';
  input_refs: string[];
  output_refs: string[];
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  error: string | null;
  detail: TraceDetail;
  created_at: string;
  t_ms: number;
}
export interface Run {
  id: string;
  case_id: string;
  case_revision: number;
  trigger_event_id: string;
  status: RunStatus;
  stop_reason: string | null;
  llm_mode: ExecutionMode;
  started_at: string | null;
  finished_at: string | null;
  usage: { model_calls: number; tokens_in: number; tokens_out: number };
}
export interface RunDetail { run: Run; steps: TraceStep[] }

// S1 collection shapes are provisional until the backend OpenAPI is available.
export interface Product {
  id: string;
  name: string;
  brand: string;
  variant: string;
  market: string;
  dataset_origin: DatasetOrigin;
  presentation?: {
    image: string;
    image_alt: string;
    price: number;
    currency: string;
    shop: string;
    official_store: boolean;
    category: string;
  };
}
export interface EvidencePassage extends Citation {
  text: string;
  source_label: string;
  captured_at: string;
  visibility: Visibility;
}
export interface EvidenceResponse { citations: EvidencePassage[]; hidden_citations: number }
export interface EventCatalogItem { name: string; title: string; expect: string }
export interface EventLogItem extends AdmitResult { received_at: string }
export interface Metrics {
  events: Record<AdmitResult['outcome'], number>;
  runs: number;
  jobs: number;
  model_calls: { live: number; replayed: number; avoided: number };
  passport_reads: number;
}
export interface Session { role: DemoRole; actor: string }
