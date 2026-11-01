import type { components } from './schema.d.ts';
import type { EvidenceResponse, DatasetOrigin, ExecutionMode } from '../types.ts';

type Schema = components['schemas'];
// Wire DTOs generated from the merged contract-2 OpenAPI.
export type ReviewQueueItem = Schema['ReviewQueueItem'];
export type ReviewSubmission = Schema['ReviewRequest'];
export type ReviewOverride = Schema['ReviewOverride'];
export type ReviewDecision = ReviewSubmission['decision'];
export type ReviewRecord = Schema['ReviewResponse'];
export type EvidenceUpload = Schema['EvidenceUploadRequest'];
export type CaseHistory = Schema['CaseHistoryResponse'];
export type ReviewResult = Schema['ResultVersionResponse'];

// Joined view, not a second wire schema. Absent expert metadata remains unknown.
export interface ReviewTask {
  id: string;
  case_id: string;
  case_revision: number;
  result: ReviewResult;
  reason_code: string;
  evidence: EvidenceResponse | null;
  evidence_error?: Error | null;
  seller_attributable?: boolean;
  dataset_origin?: DatasetOrigin | null;
  llm_mode?: ExecutionMode | null;
}
