import { useCallback, useEffect, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation, useMatch, useNavigate } from 'react-router-dom';
import type { ApiClient } from './api/client.ts';
import { DEMO_ROLES } from './api/session.ts';
import type { DemoRole } from './types.ts';
import { usePoll } from './usePoll.ts';
import { ErrorNotice } from './components/Feedback.tsx';
import { BuyerPassport } from './pages/BuyerPassport.tsx';
import { Operator } from './pages/Operator.tsx';
import { NotFound, Observe, Receipt } from './pages/Shells.tsx';
import { Reviewer } from './pages/Reviewer.tsx';

interface AppProps { api: ApiClient; role: DemoRole; onRoleChange: (role: DemoRole) => void; useMock: boolean; sessionError: Error | null }
const ROLE_TITLES: Record<DemoRole, string> = { BUYER: 'Buyer', SELLER: 'Seller', REVIEWER: 'Reviewer', OPERATOR: 'Operator' };

export function App({ api, role, onRoleChange, useMock, sessionError }: AppProps) {
  const loadProducts = useCallback((signal: AbortSignal) => api.getProducts(signal), [api]);
  const products = usePoll(loadProducts, 30_000);
  const [selectedId, setSelectedId] = useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const routeProduct = useMatch('/buyer/:productId')?.params.productId ?? '';
  const activeId = routeProduct || selectedId || products.data?.[0]?.id || '';
  const buyerPath = activeId ? `/buyer/${encodeURIComponent(activeId)}` : null;
  useEffect(() => { if (routeProduct) setSelectedId(routeProduct); }, [routeProduct]);
  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="site-header">
      <div className="header-inner">
        <Link className="wordmark" to="/" aria-label="Product Truth Passport home"><span className="brand-symbol" aria-hidden="true">p<span>↗</span></span><span>product truth<span className="wordmark-sub">PASSPORT</span></span></Link>
        <nav className="main-nav" aria-label="Workspaces">
          <NavLink to="/" end>Operator</NavLink>
          {buyerPath && <NavLink to={buyerPath}>Buyer Passport</NavLink>}
          <NavLink to="/reviewer">Reviewer</NavLink>
          <NavLink to="/observe">Observe</NavLink>
        </nav>
        <label className="role-picker"><span>View as</span><select aria-label="Demo role" value={role} onChange={(event) => { const value = DEMO_ROLES.find((item) => item === event.target.value); if (value) onRoleChange(value); }}>{DEMO_ROLES.map((item) => <option key={item} value={item}>{ROLE_TITLES[item]}</option>)}</select></label>
      </div>
    </header>
    <div className="context-bar"><div className="context-inner">
      <p><span className={`connection-dot ${useMock ? 'is-preview' : ''}`} />{useMock ? 'UI preview · sample states, no live comparisons' : 'Connected to stored results'}</p>
      <label className="product-picker"><span>Product</span><select aria-label="Selected product" value={activeId} disabled={!products.data?.length} onChange={(event) => { setSelectedId(event.target.value); navigate(`/buyer/${encodeURIComponent(event.target.value)}`); }}>
        {!products.data?.some((item) => item.id === activeId) && <option value={activeId}>{activeId ? 'Product unavailable' : 'Loading products…'}</option>}
        {products.data?.map((product) => <option key={product.id} value={product.id}>{product.name} · {product.variant}</option>)}
      </select></label>
    </div></div>
    <main id="main-content" className="page-container">
      {sessionError && <ErrorNotice error={sessionError} />}
      {products.error && <ErrorNotice error={products.error} technical={role === 'OPERATOR' || role === 'REVIEWER'} />}
      <Routes>
        <Route path="/" element={<Operator api={api} role={role} buyerPath={buyerPath} productId={activeId} product={products.data?.find((product) => product.id === activeId)} />} />
        <Route path="/buyer/:productId" element={<BuyerPassport key={`${location.pathname}:${role}`} api={api} products={products.data ?? []} role={role} />} />
        <Route path="/reviewer" element={<Reviewer api={api} role={role} />} />
        <Route path="/observe" element={<Observe />} />
        <Route path="/orders/:orderId" element={<Receipt />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </main>
    <footer className="site-footer"><span>Product Truth Passport</span><span>Source by source. Detail by detail.</span></footer>
  </>;
}
