import { useMemo } from 'react';
import { useAuth } from '../features/auth/AuthContext';
import { useI18n } from '../i18n';
import { resourceSpec } from '../features/configuration/resources';
import { RecordsPage } from './RecordsPage';

export function ConfigurationPage({ kind }: { kind: string }) {
  const { user } = useAuth();
  const { t, language } = useI18n();
  const spec = useMemo(() => user ? resourceSpec(kind, user, t) : null, [kind, user, language]);
  return spec ? <>{kind === 'customers' && <p className="notice">{t('creditLimitHelp')}</p>}<RecordsPage spec={spec} key={`${kind}-${user?.tenant?.id || 'platform'}`} /></> : null;
}
