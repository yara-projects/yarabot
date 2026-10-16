export type Field = { key: string; label: string; kind: string; required: boolean; options: string[] | null };
export type Resource = { title: string; pk: string; editable: boolean; fields: Field[] };
export type Row = Record<string, string | number | null> & { _revision: string };
export type Session = { authenticated: boolean; username: string | null; csrf: string; idle_minutes: number };

let csrf = '';
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
export function setCsrf(value: string) { csrf = value; }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options, credentials: 'same-origin', cache: 'no-store',
    headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), 'X-CSRF-Token': csrf, ...options.headers },
  });
  const data = await response.json().catch(() => ({ error: 'The service returned an unreadable response. Please retry.' }));
  if (!response.ok) {
    if (response.status === 401 && path !== '/login') window.dispatchEvent(new Event('admin:expired'));
    throw new ApiError(data.error || 'The request could not be completed.', response.status);
  }
  return data as T;
}
