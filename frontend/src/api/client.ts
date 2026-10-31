import type {
  AdmitResult, EventCatalogItem, EventEnvelope, EventLogItem, EvidenceResponse,
  FieldKey, Metrics, PassportResponse, Product, Run, RunDetail, Session,
} from '../types.ts';

export class ApiError extends Error {
  readonly path: string;
  readonly status: number;
  constructor(path: string, status: number, message: string) {
    super(`${path} · ${status || 'Network error'}: ${message}`);
    this.name = 'ApiError';
    this.path = path;
    this.status = status;
  }
}
export type Transport = (path: string, init: RequestInit) => Promise<Response>;
export interface ClientOptions { getSession: () => Session; transport?: Transport }

export function createApiClient({ getSession, transport = (path, init) => fetch(path, init) }: ClientOptions) {
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
      // Do not echo arbitrary backend bodies into buyer-facing text.
      throw new ApiError(path, response.status, response.statusText || 'Request could not be completed.');
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
    getEvidence: (id: string, field: FieldKey, signal?: AbortSignal) => request<EvidenceResponse>(`/products/${segment(id)}/fields/${segment(field)}/evidence`, 'GET', undefined, signal),
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
