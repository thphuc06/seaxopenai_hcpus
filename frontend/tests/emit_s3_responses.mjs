import './register.mjs';
import { createReviewTransport } from '../src/mock/reviewTransport.ts';
import products from '../src/mock/products.json' with { type: 'json' };
import review from '../src/mock/review.json' with { type: 'json' };
const transport = createReviewTransport();
const get = async (path, role) => { const response = await transport(path, { method: 'GET', headers: { 'X-Demo-Role': role, 'X-Demo-Actor': role } }); if (!response.ok) throw new Error(`${path}: ${response.status}`); return response.json(); };
const explain = `/api/products/${products[0].id}/fields/skin_type/explain`;
console.log(JSON.stringify({ buyer: await get(explain, 'BUYER'), expert: await get(explain, 'REVIEWER'), graph: await get(`/api/cases/${review.case_id}/graph`, 'REVIEWER'), chain: await get(`/api/cases/${review.case_id}/chain`, 'REVIEWER'), search: await get(`/api/cases/${review.case_id}/search?q=skin&mode=auto`, 'REVIEWER') }));
