import rawPassport from './passport.json' with { type: 'json' };
import rawProducts from './products.json' with { type: 'json' };
import catalog from './catalog.json' with { type: 'json' };
import passages from './passages.json' with { type: 'json' };
import type { PassportView, Product, ExplanationResponse } from '../types.ts';
import { toPassportResponse } from '../passportView.ts';
import type { Transport } from '../api/client.ts';

// JSON import literal widening is checked by the offline contract tests as well.
const passport = rawPassport as PassportView;
const products = rawProducts as Product[];
const respond = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

export const mockTransport: Transport = async (path, init) => {
  if (init.signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
  if (init.method !== 'GET') return new Response(null, { status: 501, statusText: 'Event execution is available when connected to the backend' });
  if (path === '/api/products') return respond(products.map((product) => ({
    ...product,
    presentation: product.presentation && {
      ...product.presentation, image: new URL('./product.svg', import.meta.url).href,
      ...(product.id === passport.product_id ? { passport_metadata: {
        llm_mode: passport.llm_mode,
        hidden_citations: Object.fromEntries(passport.fields.map((field) => [field.field_key, field.hidden_citations ?? 0])),
      } } : {}),
    },
  })));
  if (path === '/api/internal/events/catalog') return respond(catalog);
  if (path === '/api/internal/runs' || path === '/api/internal/events/log') return respond([]);
  if (path === '/api/internal/metrics') return respond({ events: { ADMITTED: 0, NOOP: 0, DUPLICATE: 0, REJECTED: 0 }, runs: 0, jobs: 0, model_calls: { live: 0, replayed: 0, avoided: 0 }, passport_reads: 0 });
  const parts = path.split('/').map(decodeURIComponent);
  if (parts[2] === 'products' && parts[3] === passport.product_id) {
    if (parts.length === 7 && parts[4] === 'fields' && parts[6] === 'explain') {
      const field = passport.fields.find((item) => item.field_key === parts[5]);
      if (!field) return respond({ detail: 'Field unavailable' }, 404);
      const expert = ['OPERATOR', 'REVIEWER'].includes(new Headers(init.headers).get('X-Demo-Role') ?? 'BUYER');
      const response: ExplanationResponse = expert ? {
        audience: 'EXPERT', product_id: passport.product_id, field_key: field.field_key, result_id: `preview-${field.field_key}`, trigger_event_id: 'preview-event',
        sources: [], claims: field.citations.map((c) => ({ source_version_id: `preview-version-${c.source_version}`, passage_id: c.passage_id, quote: c.excerpt, extractor: 'FALLBACK', prompt_version: 'preview', mapped_by: null })),
        rules: [], publish_checks: ['UI preview only; publication checks not recorded.'], chain_head: null, reviews: [],
      } : { audience: 'BUYER', product_id: passport.product_id, field_key: field.field_key, public_text: field.public_text,
        summaries: [field.public_text, 'This preview describes only the source passages shown.', 'Seller attribution is not provided in this preview.'], citations: [], hidden_citations: field.hidden_citations ?? 0 };
      return respond(response);
    }
    if (parts.length === 5 && parts[4] === 'passport') return respond(toPassportResponse(passport));
    if (parts.length === 7 && parts[4] === 'fields' && parts[6] === 'evidence') {
      const field = passport.fields.find((item) => item.field_key === parts[5]);
      if (field) return respond({
        citations: field.citations.map((citation) => {
          const passage = passages.find((item) => item.passage_id === citation.passage_id);
          if (!passage) throw new Error('Preview passage is missing.');
          return { ...citation, ...passage };
        }),
        hidden_citations: field.hidden_citations ?? 0,
      });
    }
  }
  return new Response(null, { status: 404, statusText: 'No matching preview resource' });
};
