const API_TOKEN_STORAGE_KEY = 'poly.operatorToken';

export function getApiToken(): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.sessionStorage.getItem(API_TOKEN_STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setApiToken(token: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(API_TOKEN_STORAGE_KEY, token);
  } catch {
    // A locked-down browser may disable sessionStorage; verification will fail
    // cleanly and the sign-in form remains available.
  }
}

export function clearApiToken(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(API_TOKEN_STORAGE_KEY);
  } catch {
    // Nothing else to clear.
  }
}

export function authorizationHeaders(): Record<string, string> {
  const token = getApiToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
