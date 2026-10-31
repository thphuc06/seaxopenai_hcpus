import { useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import type { ApiClient } from '../api/client.ts';
import type { PassportResponse, Product } from '../types.ts';
import { usePoll } from '../usePoll.ts';
import { PassportCard } from '../components/PassportCard.tsx';
import { ErrorNotice, LoadingNotice } from '../components/Feedback.tsx';

export function BuyerPassportView({ product, passport }: { product: Product | undefined; passport: PassportResponse }) {
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
      <PassportCard passport={passport} />
    </div>
  </>;
}

export function BuyerPassport({ api, products }: { api: ApiClient; products: Product[] }) {
  const { productId = '' } = useParams();
  const load = useCallback((signal: AbortSignal) => api.getPassport(productId, signal), [api, productId]);
  const { data, error, loading } = usePoll(load);
  return <>
    {error && <ErrorNotice error={error} />}
    {loading && <LoadingNotice />}
    {data && <BuyerPassportView product={products.find((item) => item.id === productId)} passport={data} />}
  </>;
}
