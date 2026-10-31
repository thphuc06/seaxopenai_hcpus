import { useEffect, useState } from 'react';
import { startPolling } from './polling.ts';
import type { PollInterval } from './polling.ts';

export function usePoll<T>(load: (signal: AbortSignal) => Promise<T>, intervalMs: PollInterval<T> = 10_000) {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({ data: null, error: null, loading: true });
  useEffect(() => {
    setState({ data: null, error: null, loading: true });
    return startPolling(load, intervalMs,
      (data) => setState({ data, error: null, loading: false }),
      (error) => setState((previous) => ({ ...previous, error, loading: false })),
      {
        visible: () => document.visibilityState !== 'hidden',
        subscribe: (listener) => {
          document.addEventListener('visibilitychange', listener);
          return () => document.removeEventListener('visibilitychange', listener);
        },
        schedule: (listener, delay) => {
          const timer = window.setTimeout(listener, delay);
          return () => window.clearTimeout(timer);
        },
      },
    );
  }, [load, intervalMs]);
  return state;
}
