import { useEffect, useState } from 'react';
import { api, errorKey } from '../services/api';
import { useI18n } from '../i18n';
import { useAuth } from '../features/auth/AuthContext';
import { permissionLabel } from '../components/RecordForm';
import { roleChoices } from '../features/configuration/resources';

interface Policy { role: string; permissions: string[] }
export function RolesPage() {
  const { t } = useI18n();
  const { reloadIdentity } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [role, setRole] = useState('worker');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  async function load() {
    setError(null);
    try {
      const result = await api<{ results: Policy[]; known_permissions: string[] }>('/roles/');
      setPolicies(result.results); setPermissions(result.known_permissions);
    } catch (error) { setError(error); }
  }
  useEffect(() => { void load(); }, []);
  const selected = policies.find(policy => policy.role === role);
  return <><div className="page-heading"><h1>{t('rolesPermissions')}</h1><p>{t('rolesHelp')}</p></div>
    {error != null && <p role="alert" className="error-message">{t(errorKey(error))}</p>}
    {!selected ? <button onClick={() => void load()}>{t('retry')}</button> : <section className="data-section">
      <label className="role-select"><span>{t('role')}</span><select value={role} onChange={event => { setRole(event.target.value); setSaved(false); }}>
        {roleChoices(t).map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
      </select></label>
      <fieldset><legend>{t('permissions')}</legend><div className="permission-grid">
        {permissions.map(permission => <label className="checkbox-field" key={permission}><input type="checkbox" disabled={busy}
          checked={selected.permissions.includes(permission)} onChange={event => {
            setSaved(false); setPolicies(previous => previous.map(policy => policy.role === role ? { ...policy, permissions: event.target.checked ? [...policy.permissions, permission] : policy.permissions.filter(value => value !== permission) } : policy));
          }} />{t(permissionLabel(permission))}</label>)}
      </div></fieldset>
      {saved && <p role="status" className="success-message">{t('saved')}</p>}
      <button disabled={busy} onClick={() => {
        setBusy(true); setError(null); setSaved(false);
        void api('/roles/', { method: 'POST', body: JSON.stringify(selected) }).then(async () => { await reloadIdentity(); setSaved(true); }).catch(setError).finally(() => setBusy(false));
      }}>{t(busy ? 'saving' : 'save')}</button>
    </section>}
  </>;
}
