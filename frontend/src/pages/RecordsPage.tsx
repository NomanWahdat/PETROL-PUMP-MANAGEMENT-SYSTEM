import { useCallback, useEffect, useRef, useState } from 'react';
import { api, allRecords, errorKey } from '../services/api';
import { useAuth } from '../features/auth/AuthContext';
import { useI18n, type TranslationKey } from '../i18n';
import { RecordForm, type Choice, type FieldSpec, type RecordValues } from '../components/RecordForm';
import type { Page } from '../types/api';
import { UserMemberships } from './UserMemberships';
import { useStation } from '../features/station/StationContext';
import { LogoUpload } from '../components/LogoUpload';

export interface ResourceSpec {
  title: TranslationKey; path: string; fields: FieldSpec[];
  columns: { key: string; label: TranslationKey }[];
  canWrite: boolean; canEdit?: (record: RecordValues) => boolean;
}

export function RecordsPage({ spec }: { spec: ResourceSpec }) {
  const { t } = useI18n();
  const { language } = useI18n();
  const { station } = useStation();
  const { reloadIdentity } = useAuth();
  const [rows, setRows] = useState<RecordValues[]>([]);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [active, setActive] = useState('');
  const [count, setCount] = useState(0);
  const [next, setNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [form, setForm] = useState<RecordValues | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice[]>>({});
  const requestSequence = useRef(0);
  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true); setError(null);
    try {
      const result = await api<Page<RecordValues>>(`${spec.path}?page=${page}&search=${encodeURIComponent(query)}&is_active=${active}`);
      if (sequence === requestSequence.current) { setRows(result.results); setCount(result.count); setNext(Boolean(result.next)); }
    } catch (error) { if (sequence === requestSequence.current) setError(error); }
    finally { if (sequence === requestSequence.current) setLoading(false); }
  }, [spec.path, page, query, active]);
  useEffect(() => { void load(); return () => { requestSequence.current += 1; }; }, [load]);
  useEffect(() => {
    const referenceFields = spec.fields.filter(field => field.reference);
    if (!referenceFields.length) return;
    let current = true;
    void Promise.all(referenceFields.map(async field => {
      const records = await allRecords<RecordValues>(field.reference!);
      return [field.key, records.map(record => ({ value: String(record.id), label: String(record.name || record.number || record.username) }))] as const;
    })).then(entries => { if (current) setChoices(Object.fromEntries(entries)); }).catch(error => { if (current) setError(error); });
    return () => { current = false; };
  }, [spec.fields]);
  function display(key: string, value: unknown) {
    if (typeof value === 'boolean') return t(key === 'is_active' ? value ? 'active' : 'inactive' : value ? 'yes' : 'no');
    if (key === 'created_at' && value) return new Intl.DateTimeFormat(language === 'fa' ? 'fa-AF' : language === 'ps' ? 'ps-AF' : 'en', { dateStyle: 'short', timeStyle: 'short', calendar: 'gregory', timeZone: station?.timezone || 'Asia/Kabul' }).format(new Date(String(value)));
    if (key === 'action') {
      const actions: Record<string, TranslationKey> = { created_tenant: 'createdTenant', updated_tenant: 'updatedTenant', created_user: 'createdUser', updated_user: 'updatedUser', membership_changed: 'membershipChanged', password_changed: 'passwordChanged', login: 'signIn', logout: 'signOut' };
      return t(actions[String(value)] || 'action');
    }
    const field = spec.fields.find(field => field.key === key);
    const option = field?.choices?.find(option => option.value === value) || choices[key]?.find(option => option.value === value);
    if (option) return option.label;
    return String(value ?? t('notProvided'));
  }
  return <>
    <div className="page-heading page-heading-actions"><h1>{t(spec.title)}</h1>{spec.canWrite && form === null && <button onClick={() => setForm({})}>{t('addNew')}</button>}</div>
    {form !== null && <section className="data-section"><h2>{t(form.id ? 'editRecord' : 'addNew')}</h2>
      <RecordForm fields={spec.fields} choices={choices} initial={form} editing={Boolean(form.id)} key={String(form.id || 'new')}
        onCancel={() => setForm(null)} onSave={async values => {
          await api(`${spec.path}${form.id ? `${form.id}/` : ''}`, { method: form.id ? 'PATCH' : 'POST', body: JSON.stringify(values) });
          setForm(null); await load(); await reloadIdentity();
        }} />
      {Boolean(form.id) && spec.path === '/platform/users/' && <UserMemberships userId={String(form.id)} />}
      {Boolean(form.id) && spec.path === '/platform/tenants/' && <>
        <LogoUpload key={String(form.id)} endpoint={`/platform/tenants/${form.id}/logo/`} src={`/api/v1/platform/tenants/${form.id}/logo/`} name={String(form.name)} />
        <p className="station-login-link">{t('stationLoginLink')}: <a href={'/login?station='+encodeURIComponent(String(form.slug))}>{location.origin+'/login?station='+String(form.slug)}</a></p>
      </>}
    </section>}
    <form className="table-tools" onSubmit={event => { event.preventDefault(); setPage(1); setQuery(search); }}>
      <label><span>{t('search')}</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <button type="submit" className="secondary">{t('search')}</button>
      {spec.fields.some(field => field.key === 'is_active') && <label><span>{t('status')}</span><select value={active} onChange={event => { setActive(event.target.value); setPage(1); }}>
        <option value="">{t('all')}</option><option value="true">{t('active')}</option><option value="false">{t('inactive')}</option>
      </select></label>}
    </form>
    {error != null && <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => void load()}>{t('retry')}</button></div>}
    {loading ? <p role="status">{t('loading')}</p> : !rows.length ? <p className="empty-state">{t('noRecords')}</p> : <div className="table-scroll"><table>
      <caption className="sr-only">{t(spec.title)}</caption>
      <thead><tr>{spec.columns.map(column => <th key={column.key} scope="col">{t(column.label)}</th>)}{spec.canWrite && <th scope="col">{t('actions')}</th>}</tr></thead>
      <tbody>{rows.map(record => <tr key={String(record.id)}>{spec.columns.map(column => <td key={column.key}><bdi>{display(column.key, record[column.key])}</bdi></td>)}
        {spec.canWrite && <td><button className="secondary compact" disabled={spec.canEdit && !spec.canEdit(record)} onClick={() => setForm(record)}>{t('edit')}</button></td>}
      </tr>)}</tbody>
    </table></div>}
    <div className="pagination"><span>{t('records')}: {count}</span><button className="secondary" disabled={page <= 1 || loading} onClick={() => setPage(value => value - 1)}>{t('previous')}</button>
      <span>{page}</span><button className="secondary" disabled={!next || loading} onClick={() => setPage(value => value + 1)}>{t('next')}</button></div>
  </>;
}
