import type { components } from './api/schema.d.ts';

type Schema = components['schemas'];
export type ExplanationResponse = Schema['BuyerExplanation'] | Schema['ExpertExplanation'];
export type BuyerExplanation = Schema['BuyerExplanation'];
export type ExpertExplanation = Schema['ExpertExplanation'];
export type SearchResponse = Schema['SearchResponse'];
export type GraphResponse = Schema['GraphResponse'];
export type ChainResponse = Schema['ChainResponse'];
export type ObservabilityResponse = Schema['ObservabilityResponse'];
export type OtelResponse = Schema['OtelResponse'];
// Wire DTOs come from the checked-out backend, including nullable metadata.
export type Citation = Schema['Citation'];
export type PassportField = Schema['PassportField'];
export type PassportResponse = Schema['PassportResponse'];
// Display-only metadata for explicit callers; contract-4 does not supply web provenance.
export interface WebSourceMetadata { source_version_id: string; url: string; captured_at: string; origin: DatasetOrigin; visibility: 'PUBLIC' | 'PRIVATE' }
export type PassportMetadata = Schema['PassportMetadata'];
export type Product = Schema['ProductResponse'];
export type EvidencePassage = Schema['EvidencePassage'] & { source_url?: string };
export type EvidenceResponse = Schema['EvidenceResponse'];
export type EventCatalogItem = Schema['EventCatalogItem'];
export type EventLogItem = Schema['EventLogItem'];
export type AdmitResult = Schema['AdmitResult'];
export type Metrics = Schema['MetricsResponse'];
export type Run = Schema['RunResponse'];
export type RunDetail = Schema['RunDetailResponse'];
export type TraceStep = Schema['TraceStepResponse'];
export type Verdict = Schema['Verdict'];
export type ConflictLocus = Schema['ConflictLocus'];
export type Freshness = Schema['Freshness'];
export type ReviewState = Schema['ReviewState'];
export type DatasetOrigin = Schema['DatasetOrigin'];
export type SourceKind = Schema['SourceKind'];
export type RunStatus = Schema['RunStatus'];
export type EventType = Schema['EventType'];
export type ExecutionMode = Run['llm_mode'];
export type Visibility = EvidencePassage['visibility'];
export type FieldKey = 'volume' | 'skin_type' | 'key_ingredients' | 'notification_number' | 'responsible_company';
export type ScopeMatch = 'MATCH' | 'MISMATCH' | 'UNKNOWN' | 'AGENT';
export type Readability = 'READABLE' | 'PARTIAL' | 'UNREADABLE';
export type EvidenceLevel = 'LISTING' | 'PRODUCT_VERSION' | 'BATCH' | 'UNIT';
export type SourceStatus = 'ACTIVE' | 'SUPERSEDED' | 'REVOKED' | 'UNAVAILABLE';
export type Role = 'BUYER' | 'SELLER' | 'REVIEWER' | 'OPERATOR' | 'SYSTEM';
export type DemoRole = Exclude<Role, 'SYSTEM'>;
export type SkinType = 'DRY' | 'NORMAL' | 'OILY' | 'COMBINATION' | 'SENSITIVE' | 'ACNE_PRONE' | 'ALL';
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type EventEnvelope = Omit<Schema['EventEnvelope'], 'payload'> & { payload: Record<string, JsonValue> };
export interface Session { role: DemoRole; actor: string }

// Pending rows and display metadata are not published findings.
export interface PassportViewField extends Omit<PassportField, 'verdict'> {
  verdict: Verdict | null;
  hidden_citations?: number;
  claims_under_review?: number;
}
export interface PassportView extends Omit<PassportResponse, 'fields'> {
  fields: PassportViewField[];
  llm_mode?: ExecutionMode;
  web_sources?: WebSourceMetadata[];
}
// Later-phase models are not in S1's OpenAPI; retain their shared S0 mirrors.
export interface RuleStep { rule: string; outcome: string; detail: string }
export interface DependsOn { source_id: string; source_version_id: string }
export interface Gap { field_key: string; missing_kind: string; needed_doc: string; known_ids: string[]; reason: string }
export interface FieldDecision {
  field_key: string;
  verdict: Verdict;
  conflict_locus: ConflictLocus | null;
  scope_match: ScopeMatch;
  review_state: ReviewState;
  evidence_level: EvidenceLevel;
  seller_attributable: boolean;
  public_text: string;
  citations: Citation[];
  depends_on: DependsOn[];
  notes: string[];
  explain: RuleStep[];
  gap: Gap | null;
  needs_scope_resolution: boolean;
}
export type ClaimFinding = FieldDecision;
