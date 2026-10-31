import { useCallback, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import type { ApiClient } from '../api/client.ts';
import type { DemoRole, FieldKey, PassportView, Product } from '../types.ts';
import { withPassportMetadata } from '../passportView.ts';
import { usePoll } from '../usePoll.ts';
import { PassportCard } from '../components/PassportCard.tsx';
import { ErrorNotice, LoadingNotice } from '../components/Feedback.tsx';
import { EvidenceDrawer } from '../components/EvidenceDrawer.tsx';
import { passportPollInterval } from '../evidence.ts';
import { EvidenceUploadForm } from '../components/EvidenceUpload.tsx';
import { WhyDialog } from '../components/WhyDialog.tsx';

export function BuyerPassportView({ product, passport, onEvidence, onWhy }: { product: Product | undefined; passport: PassportView; onEvidence?: (key: FieldKey) => void; onWhy?: (key: FieldKey) => void }) {
  const presentation = product?.presentation;
  return <>
    <div className="breadcrumb"><Link to="/">Home</Link><span aria-hidden="true">/</span><span>{presentation?.category ?? 'Product information'}</span></div>
    <div className="buyer-layout">
      <aside className="product-panel" aria-label="Product listing">
        <div className="product-image-wrap">
          {presentation?.image ? <img className="product-image" src={presentation.image} alt={presentation.image_alt} width="640" height="560" /> : <div className="image-placeholder">Product image unavailable</div>}
          <span className="image-caption">{passport.dataset_origin === 'SYNTHETIC' ? 'Illustrative product' : 'Product listing'}</span>
        </div>
        <div className="product-info">
          <p className="eyebrow product-brand">{product?.brand ?? 'Product'}</p>
          <h1>{product?.name ?? 'Product information'}</h1>
          {product?.variant && <span className="variant-pill">{product.variant}</span>}
          {presentation && <p className="product-price">{new Intl.NumberFormat('vi-VN', { style: 'currency', currency: presentation.currency, maximumFractionDigits: 0 }).format(presentation.price)}</p>}
          {presentation && <div className="shop-row"><span className="shop-icon" aria-hidden="true">⌂</span><div><span className="shop-label">Sold by</span><strong>{presentation.shop}</strong>{presentation.official_store && <span className="store-label">Official store</span>}</div></div>}
          <div className="product-note"><span className="note-line" /><p>A little more context.<br /><strong>A clearer choice.</strong></p><p>Read each detail alongside the sources checked.</p></div>
        </div>
      </aside>
      <PassportCard passport={withPassportMetadata(passport, presentation?.passport_metadata)} onEvidence={onEvidence} onWhy={onWhy} />
    </div>
  </>;
}

export function BuyerPassport({ api, products, role = 'BUYER' }: { api: ApiClient; products: Product[]; role?: DemoRole }) {
  const { productId = '' } = useParams();
  const navigate = useNavigate();
  const orderLock = useRef(false);
  const [buying, setBuying] = useState(false);
  const [buyError, setBuyError] = useState<Error | null>(null);
  async function buy() {
    if (orderLock.current) return;
    orderLock.current = true; setBuying(true); setBuyError(null);
    try { const order = await api.createOrder(productId); navigate(`/orders/${encodeURIComponent(order.id)}`); }
    catch (error) { setBuyError(error instanceof Error ? error : new Error('The receipt could not be saved.')); }
    finally { orderLock.current = false; setBuying(false); }
  }
  const [evidenceKey, setEvidenceKey] = useState<FieldKey | null>(null);
  const [whyKey, setWhyKey] = useState<FieldKey | null>(null);
  const load = useCallback((signal: AbortSignal) => api.getPassport(productId, signal), [api, productId]);
  const { data, error, loading } = usePoll(load, passportPollInterval);
  return <>
    {error && <ErrorNotice error={error} />}
    {loading && <LoadingNotice />}
    {buyError && <ErrorNotice error={buyError} />}
    {data && <section className="purchase-bar"><div><strong>Keep the evidence you saw</strong><p>Save this Passport as an evidence receipt.</p></div><button type="button" data-testid="buy-button" disabled={buying} onClick={() => void buy()}>{buying ? 'Saving…' : 'Buy · save receipt'}</button></section>}
    {data && <BuyerPassportView product={products.find((item) => item.id === productId)} passport={data} onEvidence={setEvidenceKey} onWhy={setWhyKey} />}
    {whyKey && <WhyDialog key={`${productId}:${whyKey}:${role}`} api={api} productId={productId} fieldKey={whyKey} role={role} onClose={() => setWhyKey(null)} />}
    {role === 'SELLER' && <EvidenceUploadForm key={productId} api={api} />}
    {evidenceKey && <EvidenceDrawer key={`${productId}:${evidenceKey}`} api={api} productId={productId} fieldKey={evidenceKey} allowPrivate={role === 'REVIEWER' || role === 'OPERATOR'}
      withinSource={data?.fields.find((field) => field.field_key === evidenceKey)?.conflict_locus === 'WITHIN_SOURCE'} onClose={() => setEvidenceKey(null)} />}
  </>;
}
