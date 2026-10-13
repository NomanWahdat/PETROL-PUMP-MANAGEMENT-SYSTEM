import { Link } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { useI18n, type TranslationKey } from '../i18n';

type Step = { title: TranslationKey; text: TranslationKey; path?: string; permission?: string };
const steps: Record<string, Step[]> = {
  owner: [
    { title: 'guideSetup', text: 'guideOwnerSetup', path: '/station-settings', permission: 'station.manage' },
    { title: 'guideTeam', text: 'guideOwnerTeam', path: '/employees', permission: 'employees.manage' },
    { title: 'guideOperations', text: 'guideManagerOperations', path: '/operations/shifts', permission: 'shifts.manage' },
    { title: 'guideReview', text: 'guideOwnerReview', path: '/operations/daily-closings', permission: 'closing.manage' },
  ],
  manager: [
    { title: 'guideOperations', text: 'guideManagerOperations', path: '/operations/shifts', permission: 'shifts.manage' },
    { title: 'guideStock', text: 'guideManagerStock', path: '/stock', permission: 'inventory.manage' },
    { title: 'guideReview', text: 'guideManagerClose', path: '/operations/daily-closings', permission: 'closing.manage' },
  ],
  worker: [
    { title: 'startShift', text: 'guideWorkerStart' },
    { title: 'recordReading', text: 'guideWorkerSale' },
    { title: 'closeShift', text: 'guideWorkerClose' },
  ],
  accountant: [
    { title: 'guideReview', text: 'guideAccountantReview', path: '/operations/sales', permission: 'reports.operational' },
    { title: 'guidePayments', text: 'guideAccountantPayments', path: '/customers', permission: 'customers.manage' },
    { title: 'guideCash', text: 'guideAccountantCash', path: '/operations/cash-movements', permission: 'cash.manage' },
  ],
  superadmin: [
    { title: 'guideStations', text: 'guideAdminStations', path: '/platform/tenants' },
    { title: 'guideTeam', text: 'guideAdminUsers', path: '/platform/users' },
    { title: 'guideReview', text: 'guideAdminAudit', path: '/platform/audit' },
  ],
};

export function DashboardGuide() {
  const { user } = useAuth();
  const { t } = useI18n();
  const role = user?.tenant ? user.role : 'superadmin';
  const visible = (steps[role] || []).filter(step => !step.permission || user?.permissions.includes(step.permission));
  return <details className="dashboard-guide no-print" open={role !== 'worker'}><summary>{t('dashboardGuide')}</summary>
    <p className="muted">{t('dashboardGuideIntro')}</p>
    <ol>{visible.map(step => <li key={step.text}><strong>{step.path ? <Link to={step.path}>{t(step.title)}</Link> : t(step.title)}</strong><p>{t(step.text)}</p></li>)}</ol>
    <p className="guide-note">{t('guideSafePosting')}</p>
  </details>;
}
