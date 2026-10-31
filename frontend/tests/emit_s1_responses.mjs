import { createApiClient } from '../src/api/client.ts';
import { sessionFor } from '../src/api/session.ts';
import { createScenarioTransport } from '../src/mock/scenarioTransport.ts';

const api = createApiClient({ getSession: () => sessionFor('OPERATOR'), transport: createScenarioTransport() });
const products = await api.getProducts();
const catalog = await api.getEventCatalog();
const admitted = await api.fireEvent(catalog[0].name);
const runs = await api.getRuns();
const passport = await api.getPassport(products[0].id);
const evidence = await Promise.all(passport.fields.map((field) => api.getEvidence(products[0].id, field.field_key)));
process.stdout.write(JSON.stringify({ products, catalog, admitted, runs, passport, evidence, detail: await api.getRun(runs[0].id), metrics: await api.getMetrics(), events: await api.getEventLog(), reset: await api.resetDemo() }));
