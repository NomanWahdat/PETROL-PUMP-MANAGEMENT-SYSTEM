import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, errorKey } from '../services/api';
import { useI18n } from '../i18n';
import { useStation } from '../features/station/StationContext';
import type { Transaction } from '../features/operations/types';
import { useAuth } from '../features/auth/AuthContext';

export function ReceiptPage({ payment = false }: { payment?: boolean }) {
  const { id } = useParams();
  const { t, language } = useI18n();
  const { station } = useStation();
  const { user } = useAuth();
  const canWork = user?.permissions.some(permission => ['shifts.own', 'shifts.manage'].includes(permission));
  const [record, setRecord] = useState<Transaction | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => { let current = true; setRecord(null); setError(null); void api<Transaction>((payment ? '/customer-payments/' : '/sales/')+id+'/receipt/').then(value => { if (current) setRecord(value); }).catch(error => { if (current) setError(error); }); return () => { current = false; }; }, [id, retry, payment]);
  const snapshot = record?.receipt_snapshot as Record<string, string> | undefined;
  return <><div className="page-heading page-heading-actions no-print"><h1>{t('receipt')}</h1><button disabled={!record} onClick={() => window.print()}>{t('printReceipt')}</button></div>
    {error != null ? <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => setRetry(value => value+1)}>{t('retry')}</button></div> : record && snapshot ?
      <article className="receipt-paper" style={{ maxWidth: (snapshot.width === '58' ? '58' : '80')+'mm' }}>
        {station?.logo_url && <img className="receipt-logo" src={station.logo_url} alt="" />}
        <h2>{snapshot.station_name}</h2><p>{snapshot.address}</p><p><bdi>{snapshot.phone}</bdi></p><p className="receipt-text">{snapshot.header}</p>
        <p><strong>{record.reference as string}</strong> · {t(record.status === 'reversed' ? 'reversed' : 'posted')}</p>
        <p>{new Intl.DateTimeFormat(language === 'fa' ? 'fa-AF' : language === 'ps' ? 'ps-AF' : 'en', { dateStyle: 'short', timeStyle: 'short', calendar: 'gregory', timeZone: station?.timezone || 'Asia/Kabul' }).format(new Date(String(record.created_at)))}</p>
        {!payment && <p>{snapshot.product_name} · {snapshot.pump_name} / {snapshot.nozzle_number}</p>}
        {snapshot.customer_name && <p>{t('customer')}: {snapshot.customer_name}</p>}
        {payment ? <dl><div><dt>{t('paidAmount')}</dt><dd><bdi>{String(record.amount)}</bdi></dd></div><div><dt>{t('paymentMethod')}</dt><dd>{t(record.method === 'bank' ? 'bank' : 'cash')}</dd></div></dl> : <dl>{(['opening_meter', 'closing_meter', 'liters', 'unit_price', 'subtotal', 'tax_amount', 'total', 'cash_amount', 'bank_amount', 'credit_amount'] as const).map((key, index) => <div key={key}><dt>{t((['openingMeter', 'closingMeter', 'litersSold', 'sellingPrice', 'subtotal', 'taxAmount', 'totalAmount', 'cashAmount', 'bankAmount', 'creditAmount'] as const)[index])}</dt><dd><bdi>{String(record[key])}</bdi></dd></div>)}</dl>}
        <p><strong>{String(record.currency)}</strong></p><p className="receipt-text">{snapshot.footer}</p>
        {record.status === 'reversed' && <p>{String(record.reversal_reason)}</p>}
      </article> : <p role="status">{t('loading')}</p>}
    <p className="no-print">{canWork && <><Link to="/work">{t('myShift')}</Link> · </>}<Link to={payment ? '/operations/customer-payments' : '/operations/sales'}>{t(payment ? 'customerPayments' : 'fuelSales')}</Link></p>
  </>;
}

