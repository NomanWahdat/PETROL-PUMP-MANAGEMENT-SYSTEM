import { useEffect, useState } from 'react';
import { api, allRecords, errorKey } from '../services/api';
import { useI18n } from '../i18n';
import { roleChoices } from '../features/configuration/resources';
import { RecordForm } from '../components/RecordForm';

interface Membership { tenant_id: string; name: string; role: string; is_active: boolean }
export function UserMemberships({ userId }: { userId: string }) {
  const { t } = useI18n();
  const [records, setRecords] = useState<Membership[]>([]);
  const [tenants, setTenants] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<Membership | null>(null);
  async function load() {
    const [memberships, tenants] = await Promise.all([
      api<{ results: Membership[] }>(`/platform/users/${userId}/memberships/`), allRecords<{ id: string; name: string }>('/platform/tenants/'),
    ]);
    setRecords(memberships.results); setTenants(tenants);
  }
  useEffect(() => { void load().catch(setError); }, [userId]);
  return <section className="membership-section"><h2>{t('stationAccess')}</h2>
    {error != null && <p className="error-message" role="alert">{t(errorKey(error))}</p>}
    <ul className="membership-list">{records.map(record => <li key={record.tenant_id}><span>{record.name} — {roleChoices(t).find(role => role.value === record.role)?.label} — {t(record.is_active ? 'active' : 'inactive')}</span><button type="button" className="secondary compact" onClick={() => setSelected(record)}>{t('edit')}</button></li>)}</ul>
    <RecordForm key={selected?.tenant_id || 'new-membership'} initial={selected ? { ...selected } : undefined}
      fields={[{ key: 'tenant_id', label: 'stationName', type: 'select', required: true, choices: tenants.map(tenant => ({ value: tenant.id, label: tenant.name })) },
        { key: 'role', label: 'role', type: 'select', required: true, choices: roleChoices(t), defaultValue: 'worker' },
        { key: 'is_active', label: 'active', type: 'checkbox', defaultValue: true }]}
      onCancel={selected ? () => setSelected(null) : undefined} onSave={async values => {
        await api(`/platform/users/${userId}/memberships/`, { method: 'POST', body: JSON.stringify(values) });
        setSelected(null); await load();
      }} />
  </section>;
}
