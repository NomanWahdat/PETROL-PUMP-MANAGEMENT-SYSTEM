import { Link, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { useAuth } from './features/auth/AuthContext';
import { useI18n } from './i18n';
import { LanguageSelect } from './components/LanguageSelect';
import { AppLayout } from './layouts/AppLayout';
import { AccountPage } from './pages/AccountPage';
import { HomePage } from './pages/HomePage';
import { LoginPage } from './pages/LoginPage';
import { SelectStationPage } from './pages/SelectStationPage';
import { StationProvider } from './features/station/StationContext';
import { ConfigurationPage } from './pages/ConfigurationPage';
import { RolesPage } from './pages/RolesPage';
import { StationSettingsPage } from './pages/StationSettingsPage';
import { PriceHistoryPage } from './pages/PriceHistoryPage';
import { WorkPage } from './pages/WorkPage';
import { OperationPage } from './pages/OperationPage';
import { StockPage } from './pages/StockPage';
import { ReceiptPage } from './pages/ReceiptPage';
import { operationReadPermissions, type OperationKind } from './features/operations/access';
import type { ReactNode } from 'react';

function RequireAuth() {
  const { user } = useAuth();
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

function NotFound() {
  const { t } = useI18n();
  return <div className="page-heading"><h1>{t('notFound')}</h1><Link to="/">{t('returnHome')}</Link></div>;
}

function StationLayout() {
  const { user } = useAuth();
  if (!user?.tenant && !user?.is_superadmin) return <Navigate to="/select-station" replace />;
  return <StationProvider key={user?.tenant?.id || 'platform'}><AppLayout /></StationProvider>;
}

function Access({ permission, permissions, platform = false, owner = false, children }: { permission?: string; permissions?: string[]; platform?: boolean; owner?: boolean; children: ReactNode }) {
  const { user } = useAuth();
  const { t } = useI18n();
  const allowed = platform ? user?.is_superadmin && !user.tenant : user?.tenant && (!permission || user.permissions.includes(permission)) && (!permissions || permissions.some(value => user.permissions.includes(value))) && (!owner || user.role === 'owner');
  return allowed ? children : <p role="alert" className="error-message">{t('errorAccess')}</p>;
}

export default function App() {
  const { status, refresh } = useAuth();
  const { t } = useI18n();
  if (status !== 'ready') return <div className="startup-page"><LanguageSelect />
    {status === 'loading' ? <p role="status">{t('loading')}</p> : <div role="alert">
      <h1>{t('sessionError')}</h1><p>{t('errorNetwork')}</p>
      <button onClick={() => void refresh()}>{t('retry')}</button>
    </div>}
  </div>;
  return <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<RequireAuth />}>
      <Route path="/select-station" element={<SelectStationPage />} />
      <Route element={<StationLayout />}>
        <Route index element={<HomePage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/work" element={<Access permissions={['shifts.own', 'shifts.manage']}><WorkPage /></Access>} />
        <Route path="/stock" element={<Access permissions={['reports.operational', 'inventory.manage', 'purchases.manage']}><StockPage /></Access>} />
        <Route path="/receipts/:id" element={<Access permissions={operationReadPermissions.sales}><ReceiptPage /></Access>} />
        <Route path="/payment-receipts/:id" element={<Access permissions={operationReadPermissions['customer-payments']}><ReceiptPage payment /></Access>} />
        {(Object.keys(operationReadPermissions) as OperationKind[]).map(kind => <Route key={kind} path={'/operations/'+kind} element={<Access permissions={operationReadPermissions[kind]}><OperationPage key={kind} kind={kind} /></Access>} />)}
        <Route path="/customers" element={<Access permissions={['reports.operational', 'customers.manage']}><ConfigurationPage kind="customers" /></Access>} />
        <Route path="/suppliers" element={<Access permissions={operationReadPermissions.purchases}><ConfigurationPage kind="suppliers" /></Access>} />
        <Route path="/employees" element={<Access permission="employees.manage"><ConfigurationPage kind="employees" /></Access>} />
        <Route path="/roles" element={<Access permission="access.manage" owner><RolesPage /></Access>} />
        <Route path="/station-settings" element={<Access permission="station.manage"><StationSettingsPage /></Access>} />
        <Route path="/compliance" element={<Access permission="station.manage"><ConfigurationPage kind="compliance" /></Access>} />
        {['products', 'tanks', 'pumps', 'nozzles'].map(kind => <Route key={kind} path={`/${kind}`} element={<Access permission="fuel.view"><ConfigurationPage kind={kind} /></Access>} />)}
        <Route path="/price-history" element={<Access permission="fuel.manage"><PriceHistoryPage /></Access>} />
        {['tenants', 'users', 'audit'].map(kind => <Route key={kind} path={`/platform/${kind}`} element={<Access platform><ConfigurationPage kind={kind} /></Access>} />)}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Route>
  </Routes>;
}
