import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, errorKey } from '../services/api';
import { useAuth } from '../features/auth/AuthContext';
import { useI18n } from '../i18n';
import { LanguageSelect } from '../components/LanguageSelect';
import type { StationChoice } from '../types/api';

export function SelectStationPage() {
  const { selectTenant, signOut, user } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [stations, setStations] = useState<StationChoice[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  async function load() {
    setLoading(true); setError(null);
    try { setStations((await api<{ results: StationChoice[] }>('/auth/memberships/')).results); }
    catch (error) { setError(error); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  async function select(id: string) {
    setBusy(true); setError(null);
    try { await selectTenant(id); navigate('/'); }
    catch (error) { setError(error); }
    finally { setBusy(false); }
  }
  return <main className="startup-page"><LanguageSelect /><h1>{t('selectStation')}</h1>
    {loading ? <p>{t('loading')}</p> : <div className="station-choices">
      {stations.map(station => <button key={station.id} disabled={busy} onClick={() => void select(station.id)}>{station.name}</button>)}
      {!stations.length && <p>{t('noStations')}</p>}
    </div>}
    {error != null && <div role="alert"><p className="error-text">{t(errorKey(error))}</p><button disabled={busy} onClick={() => void load()}>{t('retry')}</button></div>}
    <div className="form-actions">
      {(user?.tenant || user?.is_superadmin) && <button className="secondary" onClick={() => navigate('/')}>{t('cancel')}</button>}
      <button className="secondary" disabled={busy} onClick={() => { setBusy(true); void signOut().catch(setError).finally(() => setBusy(false)); }}>{t('signOut')}</button>
    </div>
  </main>;
}
