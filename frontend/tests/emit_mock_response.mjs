import { createApiClient } from '../src/api/client.ts';
import { mockTransport } from '../src/mock/transport.ts';
import { sessionFor } from '../src/api/session.ts';

const api = createApiClient({ getSession: () => sessionFor('BUYER'), transport: mockTransport });
const [product] = await api.getProducts();
process.stdout.write(JSON.stringify(await api.getPassport(product.id)));
