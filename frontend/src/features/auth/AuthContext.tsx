import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, ApiError, updateCsrfToken } from '../../services/api';
import type { User } from '../../types/api';

interface AuthContextValue {
  user: User | null;
  status: 'loading' | 'ready' | 'error';
  refresh: () => Promise<void>;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  selectTenant: (id: string) => Promise<void>;
  platformContext: () => Promise<void>;
  reloadIdentity: () => Promise<void>;
}
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthContextValue['status']>('loading');
  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const result = await api<{ user: User }>('/auth/me/');
      setUser(result.user);
      setStatus('ready');
    } catch (error) {
      if (error instanceof ApiError && [401, 403].includes(error.status)) {
        setUser(null);
        setStatus('ready');
      } else { setStatus('error'); }
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  async function signIn(username: string, password: string) {
    const result = await api<{ user: User; csrf_token: string }>('/auth/login/', {
      method: 'POST', body: JSON.stringify({ username, password }),
    });
    updateCsrfToken(result.csrf_token);
    setUser(result.user);
    setStatus('ready');
  }
  async function signOut() {
    await api<void>('/auth/logout/', { method: 'POST' });
    setUser(null);
  }
  async function changeContext(path: string, body?: object) {
    const result = await api<{ user: User; csrf_token: string }>(path, { method: 'POST', body: JSON.stringify(body || {}) });
    updateCsrfToken(result.csrf_token);
    setUser(result.user);
  }
  async function reloadIdentity() {
    const result = await api<{ user: User }>('/auth/me/');
    setUser(result.user);
  }
  return <AuthContext.Provider value={{ user, status, refresh, signIn, signOut, reloadIdentity,
    selectTenant: id => changeContext('/auth/select-tenant/', { tenant_id: id }),
    platformContext: () => changeContext('/auth/platform/'),
  }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider is required');
  return value;
}
