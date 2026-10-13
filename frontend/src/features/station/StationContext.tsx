import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { api } from '../../services/api';
import type { Station } from '../../types/api';
import { useI18n } from '../../i18n';

interface StationState { station: Station | null; loading: boolean; error: unknown; reloadStation: () => Promise<void> }
const StationContext = createContext<StationState | null>(null);

export function StationProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { setLanguage } = useI18n();
  const [savedStation, setStation] = useState<Station | null>(null);
  const [stationTenantId, setStationTenantId] = useState<string | undefined>();
  const [loading, setLoading] = useState(Boolean(user?.tenant));
  const [error, setError] = useState<unknown>(null);
  const tenantId = user?.tenant?.id;
  const sequence = useRef(0);
  const station = stationTenantId === tenantId ? savedStation : null;
  const reloadStation = useCallback(async () => {
    const current = ++sequence.current;
    if (!tenantId) { setStation(null); setLoading(false); return; }
    setLoading(true); setError(null);
    try { const value = await api<Station>('/station/'); if (current === sequence.current) { setStation(value); setStationTenantId(tenantId); } }
    catch (error) { if (current === sequence.current) setError(error); }
    finally { if (current === sequence.current) setLoading(false); }
  }, [tenantId]);
  useEffect(() => { void reloadStation(); return () => { sequence.current += 1; }; }, [reloadStation]);
  useEffect(() => {
    if (station) {
      try { localStorage.setItem('login-station', station.slug); } catch { /* Branding remains available through the station link. */ }
      try { if (localStorage.getItem('station-language-explicit') !== 'true') setLanguage(station.language); } catch { /* Keep the selected language without storage. */ }
      document.documentElement.style.setProperty('--primary', station.primary_color);
      document.documentElement.style.setProperty('--secondary', station.secondary_color);
      const channels = [1, 3, 5].map(start => parseInt(station.primary_color.slice(start, start + 2), 16) / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
      const luminance = channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
      document.documentElement.style.setProperty('--on-primary', luminance > .179 ? '#111111' : '#ffffff');
      document.documentElement.style.setProperty('--primary-text', luminance > .179 ? '#25332c' : station.primary_color);
    }
    return () => { for (const key of ['--primary', '--secondary', '--on-primary', '--primary-text']) document.documentElement.style.removeProperty(key); };
  }, [station]);
  return <StationContext.Provider value={{ station, loading, error, reloadStation }}>{children}</StationContext.Provider>;
}

export function useStation() {
  const context = useContext(StationContext);
  if (!context) throw new Error('StationProvider is required');
  return context;
}
