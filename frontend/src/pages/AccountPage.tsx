import { useAuth } from '../features/auth/AuthContext';
import { useI18n, type TranslationKey } from '../i18n';
import type { User } from '../types/api';
import { RecordForm } from '../components/RecordForm';
import { api, updateCsrfToken } from '../services/api';

const roleKeys: Record<User['role'], TranslationKey> = {
  owner: 'roleOwner', manager: 'roleManager', worker: 'roleWorker', accountant: 'roleAccountant', superadmin: 'roleSuperadmin', unassigned: 'roleUnassigned',
};
export function AccountPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  if (!user) return null;
  return <>
    <div className="page-heading"><h1>{t('account')}</h1><p>{t('accountIntro')}</p></div>
    <section className="data-section"><dl className="detail-list">
      <div><dt>{t('displayName')}</dt><dd>{user.display_name}</dd></div>
      <div><dt>{t('username')}</dt><dd><bdi>{user.username}</bdi></dd></div>
      <div><dt>{t('role')}</dt><dd>{t(roleKeys[user.role])}</dd></div>
      {user.tenant && <div><dt>{t('stationName')}</dt><dd>{user.tenant.name}</dd></div>}
    </dl></section>
    <section className="data-section"><h2>{t('changePassword')}</h2><p>{t('passwordHelp')}</p><RecordForm
      fields={[{ key: 'current_password', label: 'currentPassword', type: 'password', required: true }, { key: 'new_password', label: 'newPassword', type: 'password', required: true }]}
      onSave={async values => {
        const result = await api<{ csrf_token: string }>('/auth/password/', { method: 'POST', body: JSON.stringify(values) });
        updateCsrfToken(result.csrf_token);
      }} />
    </section>
  </>;
}
