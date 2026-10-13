import { useConnection } from '../hooks/useConnection';
import { useI18n } from '../i18n';

export function ConnectionStatus() {
  const online = useConnection();
  const { t } = useI18n();
  return <span className={`connection-status ${online ? '' : 'offline'}`} role="status">
    <span className="status-dot" aria-hidden="true" />
    {t(online ? 'networkAvailable' : 'offline')}
  </span>;
}
