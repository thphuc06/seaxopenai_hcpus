import rawPassport from './passport.json' with { type: 'json' };
import rawPreview from './review.json' with { type: 'json' };
import rawScenarios from './scenarios.json' with { type: 'json' };
import type { Transport } from '../api/client.ts';
import type { CaseHistory, EvidenceUpload, ReviewRecord, ReviewResult, ReviewSubmission, ReviewTask } from '../api/reviewTypes.ts';
import type { AdmitResult, EventCatalogItem, EvidenceResponse, PassportView, PassportViewField } from '../types.ts';
import { createScenarioTransport } from './scenarioTransport.ts';
import type { PreviewScenario } from './scenarioTransport.ts';

interface PreviewData {
  case_id: string;
  fields: string[];
  claim: { field_key: string; public_text: string; source_field: string };
  catalog: EventCatalogItem[];
  scenarios: PreviewScenario[];
  updates: { name: string; fields: (Partial<PassportViewField> & { field_key: string })[] }[];
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function uploadShape(value: unknown): value is EvidenceUpload {
  if (!record(value) || Object.keys(value).some((key) => !['idempotency_key', 'field_keys', 'content'].includes(key))) return false;
  if (typeof value.idempotency_key !== 'string' || !value.idempotency_key.length || !Array.isArray(value.field_keys) || !value.field_keys.length || !value.field_keys.every((field) => typeof field === 'string')) return false;
  const content = value.content;
  if (!record(content)) return false;
  if (content.kind === 'TEXT') return Object.keys(content).every((key) => ['kind', 'text'].includes(key)) && typeof content.text === 'string' && content.text.length > 0;
  return content.kind === 'IMAGE' && Object.keys(content).every((key) => ['kind', 'media_type', 'data_base64'].includes(key)) && ['image/png', 'image/jpeg'].includes(String(content.media_type)) && typeof content.data_base64 === 'string' && content.data_base64.length > 0;
}

/** Browser-local preview state only. Never used by the API production build. */
export function createReviewTransport({ preview = rawPreview as PreviewData, initial = rawPassport as PassportView,
  base = createScenarioTransport({ scenarios: [...rawScenarios as PreviewScenario[], ...preview.scenarios] }), now = () => new Date().toISOString(),
}: { preview?: PreviewData; initial?: PassportView; base?: Transport; now?: () => string } = {}): Transport {
  let revision = 1;
  let fields = structuredClone(initial.fields);
  let history: CaseHistory = { case_id: preview.case_id, case_revision: revision, results: [], reviews: [], events: [], requests: [] };
  let closed = new Set<string>();
  const resultFor = (field: PassportViewField): ReviewResult => ({
    id: `${preview.case_id}:${field.field_key}:${revision}`, field_key: field.field_key, case_revision: revision,
    verdict: field.verdict ?? 'INSUFFICIENT', conflict_locus: field.conflict_locus, freshness: field.freshness,
    review_state: field.review_state, label: field.label, case_id: preview.case_id, result_version: revision,
    citations: field.citations, public_text: field.public_text, checked_at: field.checked_at,
    created_at: now(), superseded_by: null,
  });
  async function tasks(init: RequestInit): Promise<ReviewTask[]> {
    const items: ReviewTask[] = [];
    for (const field of fields.filter((item) => preview.fields.includes(item.field_key) && !closed.has(item.field_key))) {
      const response = await base(`/api/products/${encodeURIComponent(initial.product_id)}/fields/${encodeURIComponent(field.field_key)}/evidence`, { ...init, method: 'GET' });
      if (!response.ok) throw new Error('Preview evidence unavailable.');
      const evidence = await response.json() as EvidenceResponse;
      items.push({ id: `${preview.case_id}:${field.field_key}`, case_id: preview.case_id, case_revision: revision, result: resultFor(field), evidence, reason_code: 'SOURCE_CHANGE' });
    }
    const source = fields.find((item) => item.field_key === preview.claim.source_field);
    if (source && !closed.has(preview.claim.field_key)) {
      const response = await base(`/api/products/${encodeURIComponent(initial.product_id)}/fields/${encodeURIComponent(source.field_key)}/evidence`, { ...init, method: 'GET' });
      if (!response.ok) throw new Error('Preview claim evidence unavailable.');
      items.push({ id: `${preview.case_id}:${preview.claim.field_key}`, case_id: preview.case_id, case_revision: revision, reason_code: 'CLAIM_REVIEW',
        result: { ...resultFor(source), id: `${preview.case_id}:${preview.claim.field_key}:${revision}`, field_key: preview.claim.field_key, verdict: 'UNCERTAIN', review_state: 'NEEDS_REVIEW', public_text: preview.claim.public_text }, evidence: await response.json() as EvidenceResponse });
    }
    return items;
  }
  return async (path, init) => {
    const role = new Headers(init.headers).get('X-Demo-Role');
    const parts = path.split('/').map(decodeURIComponent);
    const reviewRoute = path === '/api/review/queue' || parts[2] === 'cases';
    if (reviewRoute) {
      if (parts[2] === 'cases' && parts[4] === 'evidence' && init.method === 'POST') {
        if (!['SELLER', 'REVIEWER'].includes(role ?? '')) return Response.json({ detail: 'ROLE_REQUIRED' }, { status: 403 });
        if (parts[3] !== preview.case_id) return Response.json({ detail: 'NOT_FOUND' }, { status: 404 });
        const value: unknown = JSON.parse(String(init.body));
        if (!uploadShape(value)) return Response.json({ detail: 'EVIDENCE_FORMAT' }, { status: 422 });
        revision++; closed.clear();
        const admitted: AdmitResult = { event_id: `preview-upload-${revision}`, outcome: 'ADMITTED', reason: 'Seller provided preview evidence JSON.', job_id: null, stale_fields: [] };
        history.events.push({ ...admitted, received_at: now(), run_id: null });
        return Response.json(admitted, { status: 201 });
      }
      if (role !== 'REVIEWER') return Response.json({ detail: 'ROLE_REQUIRED' }, { status: 403 });
      if (path === '/api/review/queue' && init.method === 'GET') return Response.json((await tasks(init)).map((task) => ({ id: task.id, case_id: task.case_id, field_key: task.result.field_key, result_id: task.result.id, case_revision: task.case_revision, reason_code: task.reason_code, verdict: task.result.verdict })));
      if (parts[3] !== preview.case_id) return Response.json({ detail: 'NOT_FOUND' }, { status: 404 });
      if (parts[4] === 'history' && init.method === 'GET') {
        const current = (await tasks(init)).map((task) => task.result);
        return Response.json({ ...history, case_revision: revision, results: [...history.results, ...current] });
      }
      if (parts[4] === 'reviews' && init.method === 'POST') {
        const body = JSON.parse(String(init.body)) as ReviewSubmission;
        const task = (await tasks(init)).find((item) => item.result.id === body.result_id);
        if (body.case_revision !== revision || !task) return Response.json({ detail: { code: 'REVISION_CONFLICT', current_revision: revision } }, { status: 409 });
        if (!body.reason.trim()) return Response.json({ detail: 'REASON_REQUIRED' }, { status: 422 });
        if (body.decision === 'OVERRIDE' && body.override?.verdict !== 'INSUFFICIENT' && !body.override?.citations.length) return Response.json({ detail: 'NO_CITATION' }, { status: 422 });
        const review: ReviewRecord = { id: `preview-decision-${history.reviews.length + 1}`, case_id: preview.case_id, reviewer_id: new Headers(init.headers).get('X-Demo-Actor') ?? '', result_id: body.result_id, case_revision: revision, decision: body.decision, reason: body.reason, override: body.override ?? null, created_at: now(), review_state: 'REVIEWED' };
        history.reviews.push(review); history.results.push(task.result); closed.add(task.result.field_key);
        return Response.json(review);
      }
      return Response.json({ detail: 'ENDPOINT_PENDING' }, { status: 501 });
    }
    const response = await base(path, init);
    if (!response.ok) return response;
    if (path === '/api/internal/demo/reset' && init.method === 'POST') {
      revision = 1; fields = structuredClone(initial.fields); closed = new Set(); history = { case_id: preview.case_id, case_revision: revision, results: [], reviews: [], events: [], requests: [] };
    }
    if (parts[3] === 'demo' && parts[4] === 'fire' && init.method === 'POST') {
      const result = await response.clone().json() as AdmitResult;
      if (result.outcome === 'ADMITTED') {
        history.results.push(...(await tasks(init)).map((task) => task.result)); revision++; closed.clear();
        const update = preview.updates.find((item) => item.name === parts[5]);
        fields = fields.map((field) => ({ ...field, ...update?.fields.find((item) => item.field_key === field.field_key) }));
        history.events.push({ ...result, received_at: now(), run_id: null });
      }
    }
    if (path === '/api/internal/events/catalog' && init.method === 'GET') return Response.json([...(await response.json() as EventCatalogItem[]), ...preview.catalog]);
    if (parts[2] === 'products' && parts[3] === initial.product_id && parts[4] === 'passport' && init.method === 'GET') {
      const passport = await response.json() as PassportView;
      return Response.json({ ...passport, fields: fields.map((field) => ({ ...field, ...(field.field_key === preview.claim.source_field ? { claims_under_review: closed.has(preview.claim.field_key) ? 0 : 1 } : {}) })) });
    }
    return response;
  };
}

export const reviewTransport = createReviewTransport();
