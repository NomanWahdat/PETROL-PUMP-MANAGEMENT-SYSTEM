import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, errorKey } from '../services/api';
import { useI18n } from '../i18n';
import type { Options } from '../features/operations/types';
import { useStation } from '../features/station/StationContext';
import { useAuth } from '../features/auth/AuthContext';

export function StockPage() {
  const { t, language } = useI18n();
  const { station } = useStation();
  const { user } = useAuth();
  const canReadInventory = user?.permissions.some(permission => ['reports.operational', 'inventory.manage'].includes(permission));
  const date = (value: unknown) => value ? new Intl.DateTimeFormat(language === 'fa' ? 'fa-AF' : language === 'ps' ? 'ps-AF' : 'en', { dateStyle: 'short', timeStyle: 'short', calendar: 'gregory', timeZone: station?.timezone || 'Asia/Kabul' }).format(new Date(String(value))) : '—';
  const [options, setOptions] = useState<Options | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { let current = true; setError(null); void api<Options>('/operations/options/').then(result => { if (current) setOptions(result); }).catch(error => { if (current) setError(error); }); return () => { current = false; }; }, [retry]);
  return <><div className="page-heading"><h1>{t('tankStock')}</h1><p>{t('stockHelp')}</p></div>{canReadInventory && <div className="form-actions"><Link to="/operations/physical-stock">{t('physicalStock')}</Link><Link to="/operations/inventory-movements">{t('inventoryMovements')}</Link></div>}
    {error != null ? <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => setRetry(value => value+1)}>{t('retry')}</button></div> : options ? <div className="table-scroll"><table><caption className="sr-only">{t('tankStock')}</caption><thead><tr>{(['tank', 'fuelProduct', 'capacity', 'bookStock', 'measuredStock', 'stockVariance', 'date'] as const).map(key => <th scope="col" key={key}>{t(key)}</th>)}</tr></thead><tbody>{options.tanks?.map(tank => <tr key={tank.id}><td>{tank.name}</td><td>{tank.product_name}</td><td><bdi>{tank.capacity}</bdi></td><td><strong><bdi>{tank.book_stock}</bdi></strong></td><td><bdi>{String(tank.latest_physical?.measured_quantity ?? '—')}</bdi></td><td><bdi>{String(tank.latest_physical?.variance ?? '—')}</bdi></td><td><bdi>{date(tank.latest_physical?.created_at)}</bdi></td></tr>)}</tbody></table></div> : <p role="status">{t('loading')}</p>}
    {options?.tanks?.length === 0 && <p className="empty-state">{t('noRecords')}</p>}
  </>;
}

