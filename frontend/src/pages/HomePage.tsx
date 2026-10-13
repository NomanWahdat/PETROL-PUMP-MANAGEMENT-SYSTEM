import { useEffect, useState } from 'react';
import { useAuth } from '../features/auth/AuthContext';
import { useI18n } from '../i18n';
import { api, errorKey } from '../services/api';
import { useStation } from '../features/station/StationContext';
import { Link } from 'react-router-dom';
import { WorkPage } from './WorkPage';
import type { Options } from '../features/operations/types';
import { DashboardGuide } from '../components/DashboardGuide';
import { FuelMark, StationIdentity } from '../components/StationIdentity';

function OperationsSummary() {
  const { t } = useI18n();
  const [data, setData] = useState<Options | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { let current = true; void api<Options>('/operations/options/').then(result => { if (current) setData(result); }).catch(error => { if (current) setError(error); }); return () => { current = false; }; }, [retry]);
  return <section className="data-section operations-overview"><div className="section-heading"><FuelMark /><div><h2>{t('fuelOperations')}</h2><p className="muted">{t('fuelOperationsHelp')}</p></div></div>
    {error != null ? <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => { setError(null); setRetry(value => value+1); }}>{t('retry')}</button></div> : data ? <>
      <dl className="overview-strip"><div><dt>{t('businessDate')}</dt><dd><bdi>{data.day?.business_date || '—'}</bdi><span className="status-label">{data.day ? t(data.day.status === 'open' ? 'open' : 'closed') : '—'}</span></dd></div><div><dt>{t('expectedCash')}</dt><dd><bdi>{data.cash_balance}</bdi></dd></div></dl>
      <div className="table-scroll"><table><thead><tr><th>{t('tank')}</th><th>{t('fuelProduct')}</th><th>{t('bookStock')}</th></tr></thead><tbody>{data.tanks?.map(tank => <tr key={tank.id}><td>{tank.name}</td><td>{tank.product_name}</td><td><bdi>{tank.book_stock}</bdi></td></tr>)}</tbody></table></div>
      {data.tanks?.length === 0 && <p className="empty-state">{t('noRecords')}</p>}
      <div className="form-actions"><Link to="/stock">{t('tankStock')}</Link><Link to="/operations/sales">{t('fuelSales')}</Link><Link to="/operations/daily-closings">{t('dailyClosing')}</Link></div>
    </> : <p role="status">{t('loading')}</p>}
  </section>;
}

function PlatformSummary() {
  const { t } = useI18n();
  const [status, setStatus] = useState<{ tenants: number; active_tenants: number; users: number } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { void api<{ tenants: number; active_tenants: number; users: number }>('/platform/status/').then(setStatus).catch(setError); }, [retry]);
  return <section className="data-section"><h2>{t('superadminTitle')}</h2><p className="muted">{t('superadminBody')}</p>
    {error != null ? <div role="alert"><p>{t(errorKey(error))}</p><button onClick={() => { setError(null); setRetry(value => value + 1); }}>{t('retry')}</button></div>
      : status ? <dl className="overview-strip"><div><dt>{t('tenants')}</dt><dd>{status.tenants}</dd></div><div><dt>{t('activeStations')}</dt><dd>{status.active_tenants}</dd></div><div><dt>{t('registeredUsers')}</dt><dd>{status.users}</dd></div></dl>
      : <p role="status">{t('loading')}</p>}
  </section>;
}

export function HomePage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const { station, error, loading, reloadStation } = useStation();
  const worker = user?.role === 'worker';
  const roles = { owner: 'roleOwner', manager: 'roleManager', worker: 'roleWorker', accountant: 'roleAccountant', superadmin: 'superadminTitle', unassigned: 'account' } as const;
  return <div className="dashboard-page">
    {station?.logo_url && <img className="dashboard-watermark" src={station.logo_url} alt="" aria-hidden="true" />}
    <div className="dashboard-content">
    <div className="dashboard-heading"><div><p className="eyebrow">{t(user?.tenant ? 'stationWorkspace' : 'superadminTitle')} · {user && t(roles[user.role])}</p><h1>{station?.name || user?.tenant?.name || t('appName')}</h1><p className="muted">{t('dashboardWelcome')}{user?.display_name ? '، '+user.display_name : ''}</p></div><StationIdentity src={station?.logo_url} name={station?.name || t('appName')} className="dashboard-logo" /></div>
    {worker && user?.tenant && user.permissions.includes('shifts.own') ? <WorkPage embedded /> : <>
    {user?.tenant ? <>
      <section className="data-section" aria-labelledby="station-heading">
        <h2 id="station-heading">{t('stationDetails')}</h2>
        {loading ? <p role="status">{t('loading')}</p> : error ? <div role="alert">
          <p className="error-text">{t(errorKey(error))}</p><button className="secondary" onClick={() => void reloadStation()}>{t('retry')}</button>
        </div> : station && <dl className="detail-list">
          <div><dt>{t('stationName')}</dt><dd>{station.name}</dd></div>
          <div><dt>{t('address')}</dt><dd>{station.address || t('notProvided')}</dd></div>
          <div><dt>{t('phone')}</dt><dd><bdi>{station.phone || t('notProvided')}</bdi></dd></div>
          <div><dt>{t('currency')}</dt><dd><bdi>{station.currency}</bdi></dd></div>
          <div><dt>{t('timezone')}</dt><dd><bdi>{station.timezone}</bdi></dd></div>
        </dl>}
      </section>
      {user.permissions.includes('reports.operational') && <OperationsSummary />}
    </> : <PlatformSummary />}
    </>}
    <DashboardGuide />
    </div>
  </div>;
}
