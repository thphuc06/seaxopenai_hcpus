import type { EventCatalogItem, RunDetail } from './types.ts';

/** Story order is catalog name order unless P4 provides an explicit sequence. */
export function scenarioEvents(catalog: EventCatalogItem[], productId: string, order: readonly string[] = []): EventCatalogItem[] {
  const events = catalog.filter((event) => event.product_id === productId);
  if (order.length) return order.flatMap((name) => events.filter((event) => event.name === name));
  return [...events].sort((a, b) => a.name.localeCompare(b.name, 'en', { numeric: true }));
}

export function markedStaleWithoutModel(detail: RunDetail): boolean {
  return detail.run.usage.model_calls === 0 && detail.steps.some((step) => step.step === 'stale:mark');
}
