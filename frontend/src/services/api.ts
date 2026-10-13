import type { TranslationKey } from '../i18n';

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
let csrfToken: string | null = null;

export class ApiError extends Error {
  constructor(public code: string, public status = 0, public details?: Record<string, unknown>) { super(code); }
}

export function errorKey(error: unknown): TranslationKey {
  const keys: Record<string, TranslationKey> = {
    network_error: 'errorNetwork', invalid_credentials: 'errorCredentials',
    tenant_unavailable: 'errorAccess', tenant_required: 'errorAccess',
    permission_denied: 'errorAccess', tenant_selection_required: 'errorSelection',
    csrf_failed: 'errorCsrf', throttled: 'errorThrottled',
    invalid: 'errorValidation', station_missing: 'errorStation',
    payload_too_large: 'errorPayload',
    not_authenticated: 'errorSession',
    not_found: 'notFound',
    idempotency_conflict: 'errorDuplicate', stock_insufficient: 'errorStock', meter_invalid: 'errorMeter', payment_mismatch: 'errorAllocation', credit_customer: 'errorCredit', credit_limit: 'errorCredit', tank_capacity: 'errorCapacity', cash_insufficient: 'errorCash', unsettled_meters: 'errorFinalMeters', cash_difference: 'errorDrawer', day_closed: 'errorClosedDay', shift_closed: 'errorClosedShift', assignment_busy: 'errorBusy', equipment_unavailable: 'errorEquipment', latest_only: 'errorLatest', reason_required: 'errorReason', physical_required: 'errorPhysical', shifts_open: 'errorPhysical', already_reversed: 'errorAlreadyReversed', shift_required: 'errorStartShift',
  };
  return error instanceof ApiError ? keys[error.code] || 'errorGeneric' : 'errorGeneric';
}

export function updateCsrfToken(token: string) { csrfToken = token; }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method || 'GET';
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase());
  if (unsafe && !csrfToken) {
    const result = await api<{ csrf_token: string }>('/auth/csrf/');
    csrfToken = result.csrf_token;
  }
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    const headers = new Headers(options.headers);
    headers.set('Accept', 'application/json');
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    if (unsafe && csrfToken) headers.set('X-CSRFToken', csrfToken);
    const response = await fetch(`${baseUrl}${path}`, {
      ...options, headers, signal: controller.signal, credentials: 'include', cache: 'no-store',
    });
    if (response.status === 204) return undefined as T;
    const payload = await response.json();
    if (!response.ok) {
      const code = payload.error?.code || 'request_error';
      if (code === 'csrf_failed') csrfToken = null;
      throw new ApiError(code, response.status, payload.error?.details);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError('network_error');
  } finally { window.clearTimeout(timeout); }
}

export async function allRecords<T>(path: string): Promise<T[]> {
  const records: T[] = [];
  let page = 1;
  while (true) {
    const result = await api<import('../types/api').Page<T>>(`${path}${path.includes('?') ? '&' : '?'}page_size=200&page=${page}`);
    records.push(...result.results);
    if (!result.next) return records;
    page += 1;
  }
}
