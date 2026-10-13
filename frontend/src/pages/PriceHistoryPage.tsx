import { useEffect, useState } from 'react';
import { api, allRecords, errorKey } from '../services/api';
import { useI18n } from '../i18n';
import { useStation } from '../features/station/StationContext';
import type { Page } from '../types/api';

interface Price { id: string; product: string; purchase_price: string; selling_price: string; reason: string; created_at: string }
export function PriceHistoryPage() {
  const { t, language } = useI18n();
  const { station } = useStation();
  const [products, setProducts] = useState<{ id: string; name: string }[]>([]);
  const [prices, setPrices] = useState<Page<Price> | null>(null);
  const [product, setProduct] = useState('');
  const [page, setPage] = useState(1);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { void allRecords<{ id: string; name: string }>('/fuel/products/').then(setProducts).catch(setError); }, []);
  useEffect(() => {
    setError(null); setPrices(null);
    void api<Page<Price>>(`/fuel/price-history/?page=${page}${product ? `&product=${product}` : ''}`).then(setPrices).catch(setError);
  }, [page, product, retry]);
  return <><div className="page-heading"><h1>{t('priceHistory')}</h1><p>{t('priceHistoryHelp')}</p></div>
    <label className="role-select"><span>{t('fuelProduct')}</span><select value={product} onChange={event => { setProduct(event.target.value); setPage(1); }}>
      <option value="">{t('all')}</option>{products.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label>
    {error != null ? <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => setRetry(value => value + 1)}>{t('retry')}</button></div>
      : prices ? <div className="table-scroll"><table><caption className="sr-only">{t('priceHistory')}</caption><thead><tr>
        {(['date', 'fuelProduct', 'purchasePrice', 'sellingPrice', 'priceReason'] as const).map(key => <th scope="col" key={key}>{t(key)}</th>)}
      </tr></thead><tbody>{prices.results.map(price => <tr key={price.id}>
        <td>{new Intl.DateTimeFormat(language === 'fa' ? 'fa-AF' : language === 'ps' ? 'ps-AF' : 'en', { dateStyle: 'short', timeStyle: 'short', calendar: 'gregory', timeZone: station?.timezone || 'Asia/Kabul' }).format(new Date(price.created_at))}</td>
        <td>{products.find(item => item.id === price.product)?.name || t('notProvided')}</td><td><bdi>{price.purchase_price}</bdi></td><td><bdi>{price.selling_price}</bdi></td><td>{price.reason || t('notProvided')}</td>
      </tr>)}</tbody></table>{!prices.results.length && <p>{t('noRecords')}</p>}</div> : <p role="status">{t('loading')}</p>}
    <div className="pagination"><button className="secondary" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>{t('previous')}</button><span>{page}</span>
      <button className="secondary" disabled={!prices?.next} onClick={() => setPage(value => value + 1)}>{t('next')}</button></div>
  </>;
}
