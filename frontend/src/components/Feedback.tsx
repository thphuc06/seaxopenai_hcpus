import { ApiError } from '../api/client.ts';

function plainError(error: Error): string {
  if (error instanceof ApiError) {
    if (error.status === 501) return 'This information is not available yet. Please try again later.';
    if (error.status === 404) return 'This information could not be found. Check your selection or try again.';
    if (error.status === 401 || error.status === 403) return 'This information is not available with your current access.';
    if (error.status === 0) return 'We could not connect. Check your connection and try again.';
  }
  return 'Please try again or reload the page.';
}

export function ErrorNotice({ error, technical = false, plain = false }: { error: Error; technical?: boolean; plain?: boolean }) {
  return <div className="error-notice" role="alert">
    <strong>We couldn’t load this information.</strong>
    <p>{plain ? plainError(error) : technical ? error.message : error instanceof ApiError
      ? `/api${error.path} · ${error.status ? `Response status: ${error.status}.` : 'Network error. Check your connection.'} Please try again.`
      : 'Please try again or reload the page.'}</p>
  </div>;
}
export function LoadingNotice() {
  return <div className="loading-notice" role="status"><span className="loading-dot" />Loading information…</div>;
}
export function EmptyPanel({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return <section className="empty-panel"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{children}</section>;
}
