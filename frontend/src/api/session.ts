import type { DemoRole, Session } from '../types.ts';

export const DEMO_ROLES: DemoRole[] = ['BUYER', 'SELLER', 'REVIEWER', 'OPERATOR'];
const ROLE_KEY = 'ptp.demo-role';
export function sessionFor(role: DemoRole): Session {
  return { role, actor: `demo-${role.toLowerCase()}` };
}
export function readSession(storage: Pick<Storage, 'getItem'>): Session {
  const stored = storage.getItem(ROLE_KEY);
  return sessionFor(DEMO_ROLES.find((role) => role === stored) ?? 'BUYER');
}
export function saveRole(storage: Pick<Storage, 'setItem'>, role: DemoRole): void {
  storage.setItem(ROLE_KEY, role);
}
