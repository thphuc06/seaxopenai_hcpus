import { ApiError } from '../api/client.ts';

export function ErrorNotice({ error, technical = false }: { error: Error; technical?: boolean }) {
  return <div className="error-notice" role="alert">
    <strong>We couldn’t load this information.</strong>
    <p>{technical ? error.message : error instanceof ApiError
      ? `Please try again. ${error.status ? `Response status: ${error.status}.` : 'Check your connection.'}`
      : 'Please try again or reload the page.'}</p>
  </div>;
}
export function LoadingNotice() {
  return <div className="loading-notice" role="status"><span className="loading-dot" />Loading information…</div>;
}
export function EmptyPanel({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return <section className="empty-panel"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{children}</section>;
}
