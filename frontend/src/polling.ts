export interface PollEnvironment {
  visible: () => boolean;
  subscribe: (listener: () => void) => () => void;
  schedule: (listener: () => void, delay: number) => () => void;
}
export type PollInterval<T> = number | ((data: T | null) => number);

/** One outstanding request, no hidden-tab traffic, abort on hide/unmount. */
export function startPolling<T>(
  load: (signal: AbortSignal) => Promise<T>,
  intervalMs: PollInterval<T>,
  receive: (data: T) => void,
  fail: (error: Error) => void,
  environment: PollEnvironment,
): () => void {
  let stopped = false;
  let controller: AbortController | undefined;
  let cancelTimer: (() => void) | undefined;
  let latest: T | null = null;
  async function tick() {
    if (stopped || !environment.visible() || controller) return;
    const active = new AbortController();
    controller = active;
    try {
      const data = await load(active.signal);
      if (!stopped && !active.signal.aborted) { latest = data; receive(data); }
    } catch (error) {
      if (!stopped && !active.signal.aborted) fail(error instanceof Error ? error : new Error('Could not load this view.'));
    } finally {
      if (controller === active) {
        controller = undefined;
        const delay = typeof intervalMs === 'function' ? intervalMs(latest) : intervalMs;
        if (!stopped && environment.visible()) cancelTimer = environment.schedule(() => { void tick(); }, delay);
      }
    }
  }
  const unsubscribe = environment.subscribe(() => {
    cancelTimer?.();
    controller?.abort();
    controller = undefined;
    if (environment.visible()) void tick();
  });
  void tick();
  return () => {
    stopped = true;
    cancelTimer?.();
    controller?.abort();
    unsubscribe();
  };
}
