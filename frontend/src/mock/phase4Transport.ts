import type { Transport } from '../api/client.ts';
import type { PassportResponse, FieldKey } from '../types.ts';
import type { ReceiptResponse, ReceiptDiff } from '../api/phase4Types.ts';
import { reviewTransport } from './reviewTransport.ts';
import sample from './phase4.json' with { type: 'json' };

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value !== null && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}

export function receiptDiff(before: PassportResponse, after: PassportResponse): ReceiptDiff[] {
  const keys = new Set([...before.fields, ...after.fields].map((field) => field.field_key));
  return [...keys].map((key) => {
    const old = before.fields.find((field) => field.field_key === key) ?? null;
    const current = after.fields.find((field) => field.field_key === key) ?? null;
    return { field_key: key as FieldKey, before: old, after: current, changed: stableJson(old) !== stableJson(current) };
  });
}
export function createPhase4Transport(base: Transport = reviewTransport, now = () => new Date().toISOString()): Transport {
  const orders = new Map<string, ReceiptResponse>();
  return async (path, init) => {
    if (init.signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
    const role = new Headers(init.headers).get('X-Demo-Role');
    const actor = new Headers(init.headers).get('X-Demo-Actor');
    if (!actor?.trim() || !['BUYER', 'SELLER', 'REVIEWER', 'OPERATOR'].includes(role ?? '')) return new Response(null, { status: 403 });
    const expert = role === 'OPERATOR' || role === 'REVIEWER';
    const url = new URL(path, 'http://preview.local');
    const parts = url.pathname.split('/').map(decodeURIComponent);
    if (path === '/api/internal/observability' || path === '/api/internal/eval/metrics' || parts[4] === 'web-search') {
      if (!expert) return new Response(null, { status: 403 });
      if (init.method !== 'GET') return new Response(null, { status: 501 });
      if (path === '/api/internal/eval/metrics') return Response.json(null);
      if (path === '/api/internal/observability') return Response.json(sample.observability);
      return Response.json({ ...sample.audit, case_id: parts[3] });
    }
    if (path === '/api/orders' && init.method === 'POST') {
      const input = JSON.parse(String(init.body)) as { product_id: string };
      const response = await base(`/api/products/${encodeURIComponent(input.product_id)}/passport`, { ...init, method: 'GET', body: undefined });
      if (!response.ok) return response;
      const snapshot = await response.json() as PassportResponse;
      const receipt: ReceiptResponse = { id: `preview-order-${orders.size + 1}`, product_id: input.product_id, created_at: now(), snapshot: structuredClone(snapshot), snapshot_hash: null, chain_head: null, changed_since_purchase: false, diff: receiptDiff(snapshot, snapshot) };
      orders.set(receipt.id, structuredClone(receipt));
      return Response.json(receipt);
    }
    if (parts[2] === 'orders' && parts.length === 4 && init.method === 'GET') {
      const receipt = orders.get(parts[3]!);
      if (!receipt) return new Response(null, { status: 404 });
      const response = await base(`/api/products/${encodeURIComponent(receipt.product_id)}/passport`, init);
      if (!response.ok) return response;
      const diff = receiptDiff(receipt.snapshot, await response.json() as PassportResponse);
      return Response.json({ ...receipt, diff, changed_since_purchase: diff.some((row) => row.changed) });
    }
    const response = await base(path, init);
    if (path === '/api/internal/demo/reset' && init.method === 'POST' && response.ok) orders.clear();
    return response;
  };
}
export const phase4Transport = createPhase4Transport();
