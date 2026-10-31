import type {
  AdmitResult, EventCatalogItem, EventEnvelope, EventLogItem, EvidenceResponse,
  FieldKey, Metrics, PassportResponse, Product, Run, RunDetail, Session,
} from '../types.ts';
import type { CaseHistory, EvidenceUpload, ReviewQueueItem, ReviewRecord, ReviewSubmission, ReviewTask } from './reviewTypes.ts';
import { matchingReviewEvidence } from './reviewEvidence.ts';

export interface ReviewErrorDetail { code?: string; current_revision?: number }

export class ApiError extends Error {
  readonly path: string;
  readonly status: number;
  readonly detail: ReviewErrorDetail | null;
  constructor(path: string, status: number, message: string, detail: ReviewErrorDetail | null = null) {
    super(`${path} · ${status || 'Network error'}: ${message}`);
    this.name = 'ApiError';
    this.path = path;
    this.status = status;
    this.detail = detail;
  }
}
export type Transport = (path: string, init: RequestInit) => Promise<Response>;
export interface ClientOptions { getSession: () => Session; transport?: Transport }

export function createApiClient({ getSession, transport = (path, init) => fetch(path, init) }: ClientOptions) {
  const pendingReviews = new Set<string>();
  function optionalEvidenceError(error: unknown, signal?: AbortSignal): Error {
    if (signal?.aborted || (error instanceof Error && error.name === 'AbortError') || (error instanceof ApiError && [401, 403].includes(error.status))) throw error;
    return error instanceof Error ? error : new Error('The full evidence could not be loaded.');
  }
  async function request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    const session = getSession();
    const headers: Record<string, string> = { 'X-Demo-Role': session.role, 'X-Demo-Actor': session.actor };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let response: Response;
    try {
      response = await transport(`/api${path}`, { method, headers, signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new ApiError(path, 0, error instanceof Error ? error.message : 'Request could not be completed.');
    }
    if (!response.ok) {
      // Only the review form consumes these bounded protocol fields. Never echo source text.
      let detail: ReviewErrorDetail | null = null;
      if (method === 'POST' && path.endsWith('/reviews') && [409, 422].includes(response.status)) {
        const payload: unknown = await response.json().catch(() => null);
        if (payload && typeof payload === 'object' && 'detail' in payload) {
          const value = payload.detail;
          const code = typeof value === 'string' ? value : value && typeof value === 'object' && 'code' in value ? value.code : undefined;
          const revision = value && typeof value === 'object' && 'current_revision' in value ? value.current_revision : undefined;
          detail = {
            ...(typeof code === 'string' && /^[A-Z][A-Z_]{0,63}$/.test(code) ? { code } : {}),
            ...(typeof revision === 'number' && Number.isInteger(revision) && revision >= 0 ? { current_revision: revision } : {}),
          };
        }
      }
      // Do not echo arbitrary backend bodies into buyer-facing text.
      throw new ApiError(path, response.status, response.statusText || 'Request could not be completed.', detail);
    }
    if (response.status === 204) return undefined as T;
    try {
      return await response.json() as T;
    } catch {
      throw new ApiError(path, response.status, 'The response could not be read.');
    }
  }
  const segment = encodeURIComponent;
  return {
    getProducts: (signal?: AbortSignal) => request<Product[]>('/products', 'GET', undefined, signal),
    getPassport: (id: string, signal?: AbortSignal) => request<PassportResponse>(`/products/${segment(id)}/passport`, 'GET', undefined, signal),
    getEvidence: (id: string, field: FieldKey | `claim:${string}`, signal?: AbortSignal) => request<EvidenceResponse>(`/products/${segment(id)}/fields/${segment(field)}/evidence`, 'GET', undefined, signal),
    getReviewQueue: async (signal?: AbortSignal): Promise<ReviewTask[]> => {
      const queue = await request<ReviewQueueItem[]>('/review/queue', 'GET', undefined, signal);
      const histories = new Map<string, Promise<CaseHistory>>();
      let products: Promise<Product[]> | undefined;
      return Promise.all(queue.map(async (item) => {
        if (!histories.has(item.case_id)) histories.set(item.case_id, request<CaseHistory>(`/cases/${segment(item.case_id)}/history`, 'GET', undefined, signal));
        const history = await histories.get(item.case_id)!;
        const result = history.results.find((row) => row.id === item.result_id);
        if (!result) throw new ApiError('/review/queue', 0, 'The queued result is not present in case history. Reload the queue.');
        let evidence: EvidenceResponse | null = null;
        let evidenceError: Error | null = null;
        // S2 history lacks product_id. Resolve only exact stored citations; never infer a case from a name.
        if (result.citations.length) {
          try {
            products ??= request<Product[]>('/products', 'GET', undefined, signal);
            for (const product of await products) {
              let candidate: EvidenceResponse;
              try { candidate = await request<EvidenceResponse>(`/products/${segment(product.id)}/fields/${segment(result.field_key)}/evidence`, 'GET', undefined, signal); }
              catch (error) {
                if (error instanceof ApiError && error.status === 404) continue;
                const warning = optionalEvidenceError(error, signal);
                evidenceError ??= warning; continue;
              }
              evidence = matchingReviewEvidence(result.citations, candidate);
              if (evidence) break;
            }
          } catch (error) { evidenceError = optionalEvidenceError(error, signal); }
        }
        return { id: item.id, case_id: item.case_id, case_revision: item.case_revision, result, reason_code: item.reason_code, evidence, evidence_error: evidenceError };
      }));
    },
    getCaseHistory: (id: string, signal?: AbortSignal) => request<CaseHistory>(`/cases/${segment(id)}/history`, 'GET', undefined, signal),
    submitReview: async (id: string, review: ReviewSubmission): Promise<ReviewRecord> => {
      const key = JSON.stringify([id, review.result_id, review.case_revision]);
      if (pendingReviews.has(key)) throw new Error('A decision for this result and revision is already being submitted.');
      pendingReviews.add(key);
      try { return await request<ReviewRecord>(`/cases/${segment(id)}/reviews`, 'POST', review); }
      finally { pendingReviews.delete(key); }
    },
    uploadEvidence: (id: string, evidence: EvidenceUpload) => request<AdmitResult>(`/cases/${segment(id)}/evidence`, 'POST', evidence),
    submitEvent: (event: EventEnvelope) => request<AdmitResult>('/internal/events', 'POST', event),
    getEventCatalog: (signal?: AbortSignal) => request<EventCatalogItem[]>('/internal/events/catalog', 'GET', undefined, signal),
    fireEvent: (name: string) => request<AdmitResult>(`/internal/demo/fire/${segment(name)}`, 'POST'),
    getEventLog: (signal?: AbortSignal) => request<EventLogItem[]>('/internal/events/log', 'GET', undefined, signal),
    getRuns: (signal?: AbortSignal) => request<Run[]>('/internal/runs', 'GET', undefined, signal),
    getRun: (id: string, signal?: AbortSignal) => request<RunDetail>(`/internal/runs/${segment(id)}`, 'GET', undefined, signal),
    getMetrics: (signal?: AbortSignal) => request<Metrics>('/internal/metrics', 'GET', undefined, signal),
    resetDemo: () => request<{ status: string }>('/internal/demo/reset', 'POST'),
  };
}
export type ApiClient = ReturnType<typeof createApiClient>;
