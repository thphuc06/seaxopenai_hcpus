import { StrictMode, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App.tsx';
import { createApiClient } from './api/client.ts';
import type { Transport } from './api/client.ts';
import { readSession, saveRole, sessionFor } from './api/session.ts';
import type { DemoRole } from './types.ts';
import './styles.css';

const useMock = import.meta.env.VITE_USE_MOCK === '1';
const transport: Transport | undefined = useMock
  ? async (path, init) => (await import('./mock/scenarioTransport.ts')).scenarioTransport(path, init)
  : undefined;

function Root() {
  const [initial] = useState(() => {
    try { return { session: readSession(window.localStorage), error: null }; }
    catch { return { session: sessionFor('BUYER'), error: new Error('Role preferences could not be restored.') }; }
  });
  const [session, setSession] = useState(initial.session);
  const [sessionError, setSessionError] = useState<Error | null>(initial.error);
  const api = useMemo(() => createApiClient({ getSession: () => session, transport }), [session]);
  function changeRole(role: DemoRole) {
    setSession(sessionFor(role));
    try { saveRole(window.localStorage, role); setSessionError(null); }
    catch { setSessionError(new Error('The selected role could not be saved for your next visit.')); }
  }
  return <App api={api} role={session.role} onRoleChange={changeRole} useMock={useMock} sessionError={sessionError} />;
}

const root = document.getElementById('root');
if (!root) throw new Error('The application root is missing.');
createRoot(root).render(<StrictMode><BrowserRouter><Root /></BrowserRouter></StrictMode>);
