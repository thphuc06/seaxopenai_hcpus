import { createReviewTransport } from '../src/mock/reviewTransport.ts';
import { sessionFor } from '../src/api/session.ts';

const transport = createReviewTransport();
const session = sessionFor('REVIEWER');
const headers = { 'X-Demo-Role': session.role, 'X-Demo-Actor': session.actor, 'Content-Type': 'application/json' };
async function request(path, method = 'GET', body) {
  const response = await transport(path, { method, headers, ...(body ? { body: JSON.stringify(body) } : {}) });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}
const queue = await request('/api/review/queue');
const first = queue[0];
const reviewRequest = { result_id: first.result_id, case_revision: first.case_revision, decision: 'APPROVE', reason: 'Read the stored passages' };
const review = await request(`/api/cases/${first.case_id}/reviews`, 'POST', reviewRequest);
const history = await request(`/api/cases/${first.case_id}/history`);
const uploadRequest = { idempotency_key: 'other-upload', field_keys: ['volume'], content: { kind: 'TEXT', text: 'Volume: 73 ml.' } };
const uploaded = await request(`/api/cases/${first.case_id}/evidence`, 'POST', uploadRequest);
process.stdout.write(JSON.stringify({ queue, reviewRequest, review, history, uploadRequest, uploaded }));
