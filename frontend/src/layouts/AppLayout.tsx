import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { ConnectionStatus } from '../components/ConnectionStatus';
import { LanguageSelect } from '../components/LanguageSelect';
import { useAuth } from '../features/auth/AuthContext';
import { useI18n } from '../i18n';
import { errorKey } from '../services/api';
import { useStation } from '../features/station/StationContext';
import { useNavigate } from 'react-router-dom';
import { operationReadPermissions, type OperationKind } from '../features/operations/access';
import type { TranslationKey } from '../i18n';
import { StationIdentity } from '../components/StationIdentity';

export function AppLayout() {
  const { user, signOut, platformContext } = useAuth();
  const { station } = useStation();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [navigationOpen, setNavigationOpen] = useState(() => window.matchMedia('(min-width: 721px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(min-width: 721px)');
    const update = () => setNavigationOpen(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const has = (...permissions: string[]) => permissions.some(permission => user?.permissions.includes(permission));
  const operationalLinks: [OperationKind, TranslationKey][] = [['shifts', 'shiftHistory'], ['sales', 'fuelSales'], ['purchases', 'purchases'], ['customer-payments', 'customerPayments'], ['cash-movements', 'cashMovements'], ['daily-closings', 'dailyClosing'], ['meter-readings', 'meterReadings']];
  const showOperations = has('reports.operational', 'shifts.manage', 'purchases.manage', 'customers.manage', 'inventory.manage', 'cash.manage', 'closing.manage');
  async function handleSignOut() {
    if (busy) return;
    setBusy(true); setError('');
    try { await signOut(); } catch (error) { setError(t(errorKey(error))); }
    finally { setBusy(false); }
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">{t('skipContent')}</a>
    <aside className="sidebar">
      <div className="station-brand"><StationIdentity src={station?.logo_url} name={station?.name || t('appName')} className="sidebar-logo" /><span>{station?.name || user?.tenant?.name || t('appName')}</span></div>
      <nav aria-label={t('overview')}>
        <NavLink to="/" end>{t(user?.role === 'worker' ? 'myShift' : 'overview')}</NavLink>
        <NavLink to="/account">{t('account')}</NavLink>
        {user?.tenant && <>
          {user.role !== 'worker' && (user.permissions.includes('shifts.own') || user.permissions.includes('shifts.manage')) && <NavLink to="/work">{t('myShift')}</NavLink>}
          {showOperations && <details className="nav-group" open={navigationOpen} onToggle={event => setNavigationOpen(event.currentTarget.open)}><summary>{t('fuelOperations')}</summary>
            {operationalLinks.filter(([kind]) => has(...operationReadPermissions[kind])).map(([kind, label]) => <NavLink key={kind} to={'/operations/'+kind}>{t(label)}</NavLink>)}
            {has(...operationReadPermissions.purchases) && <NavLink to="/suppliers">{t('suppliers')}</NavLink>}
            {has('reports.operational', 'inventory.manage', 'purchases.manage') && <NavLink to="/stock">{t('tankStock')}</NavLink>}
            {has('reports.operational', 'customers.manage') && <NavLink to="/customers">{t('customers')}</NavLink>}
          </details>}
          {user.permissions.includes('employees.manage') && <NavLink to="/employees">{t('employees')}</NavLink>}
          {user.role === 'owner' && user.permissions.includes('access.manage') && <NavLink to="/roles">{t('rolesPermissions')}</NavLink>}
          {user.permissions.includes('station.manage') && <><NavLink to="/station-settings">{t('stationSettings')}</NavLink><NavLink to="/compliance">{t('compliance')}</NavLink></>}
          {user.permissions.includes('fuel.view') && <><NavLink to="/products">{t('fuelProducts')}</NavLink><NavLink to="/tanks">{t('tanks')}</NavLink><NavLink to="/pumps">{t('pumps')}</NavLink><NavLink to="/nozzles">{t('nozzles')}</NavLink></>}
          {user.permissions.includes('fuel.manage') && <NavLink to="/price-history">{t('priceHistory')}</NavLink>}
        </>}
        {user?.is_superadmin && !user.tenant && <><NavLink to="/platform/tenants">{t('tenants')}</NavLink><NavLink to="/platform/users">{t('systemUsers')}</NavLink><NavLink to="/platform/audit">{t('systemAudit')}</NavLink></>}
        <NavLink to="/select-station">{t('changeStation')}</NavLink>
      </nav>
      <div className="sidebar-account">
        <span>{user?.display_name}</span>
        <button type="button" className="secondary" disabled={busy} onClick={() => void handleSignOut()}>
          {t(busy ? 'signingOut' : 'signOut')}
        </button>
        {error && <p className="error-text" role="alert">{error}</p>}
        {user?.is_superadmin && user.tenant && <button className="secondary" disabled={busy} onClick={() => {
          setBusy(true); void platformContext().then(() => navigate('/')).catch(error => setError(t(errorKey(error)))).finally(() => setBusy(false));
        }}>{t('platformArea')}</button>}
      </div>
    </aside>
    <div className="main-column">
      <header className="topbar"><ConnectionStatus /><LanguageSelect /></header>
      <main id="main-content" className="page-content"><Outlet /></main>
    </div>
  </div>;
}
