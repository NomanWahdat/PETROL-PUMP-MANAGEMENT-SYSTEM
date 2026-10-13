import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useI18n } from '../../i18n';
import { useConnection } from '../../hooks/useConnection';
import { api, errorKey } from '../../services/api';
import type { Assignment, Options, Quote, Transaction } from './types';

export function SaleEntry({ assignment, customers, onDone, onCancel }: { assignment: Assignment; customers: Options['customers']; onDone: () => Promise<void>; onCancel: () => void }) {
  const { t } = useI18n();
  const online = useConnection();
  const [closing, setClosing] = useState('');
  const [credit, setCredit] = useState('0.00');
  const [bank, setBank] = useState('0.00');
  const [customer, setCustomer] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Transaction | null>(null);
  const key = useRef(crypto.randomUUID());
  const payload = { assignment_id: assignment.id, closing_meter: closing, credit_amount: credit || '0.00', bank_amount: bank || '0.00', customer_id: customer || null };
  function edit(action: () => void) { action(); setQuote(null); setSaved(null); }
  return <section className="data-section sale-entry"><h2>{t('recordReading')} — {assignment.nozzle_label}</h2>
    <p>{assignment.product_name} · {t('currentMeter')}: <bdi>{assignment.current_meter}</bdi> · {t('sellingPrice')}: <bdi>{assignment.unit_price}</bdi></p>
    <form onSubmit={event => {
      event.preventDefault(); if (!quote || busy || !online) return;
      setBusy(true); setError(null);
      void api<Transaction>('/sales/', { method: 'POST', headers: { 'Idempotency-Key': key.current }, body: JSON.stringify(payload) }).then(async result => {
        key.current = crypto.randomUUID(); setSaved(result); setQuote(null); setClosing(''); setCredit('0.00'); setBank('0.00'); setCustomer(''); await onDone();
      }).catch(setError).finally(() => setBusy(false));
    }}>
      <label className="meter-input"><span>{t('closingMeter')}</span><input id="sale-closing-meter" type="number" step="0.001" min="0" required value={closing} disabled={busy} onChange={event => edit(() => setClosing(event.target.value))} /></label>
      <details><summary>{t('paymentSplit')}</summary><div className="form-grid">
        <label><span>{t('customer')}</span><select id="sale-customer" value={customer} disabled={busy} onChange={event => edit(() => setCustomer(event.target.value))}><option value="">{t('choose')}</option>{customers.map(customer => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></label>
        <label><span>{t('creditAmount')}</span><input id="sale-credit" type="number" min="0" step="0.01" value={credit} disabled={busy} onChange={event => edit(() => setCredit(event.target.value))} /></label>
        <label><span>{t('bankAmount')}</span><input id="sale-bank" type="number" min="0" step="0.01" value={bank} disabled={busy} onChange={event => edit(() => setBank(event.target.value))} /></label>
      </div></details>
      {quote && <dl className="sale-quote detail-list"><div><dt>{t('litersSold')}</dt><dd><bdi>{quote.liters}</bdi></dd></div><div><dt>{t('subtotal')}</dt><dd><bdi>{quote.subtotal}</bdi></dd></div><div><dt>{t('taxAmount')}</dt><dd><bdi>{quote.tax_amount}</bdi></dd></div><div><dt>{t('totalAmount')}</dt><dd><strong><bdi>{quote.total}</bdi></strong></dd></div><div><dt>{t('cashAmount')}</dt><dd><bdi>{quote.cash_amount}</bdi></dd></div></dl>}
      {error != null && <p className="error-message" role="alert">{t(errorKey(error))}</p>}
      {!online && <p className="notice">{t('offlineHelp')}</p>}
      {saved && <p className="success-message" role="status">{t('transactionSaved')} <Link to={'/receipts/'+saved.id}>{t('receipt')} {String(saved.reference)}</Link></p>}
      <div className="form-actions"><button type="button" className="secondary" disabled={!closing || busy || !online} onClick={() => {
        setBusy(true); setError(null);
        void api<Quote>('/sales/quote/', { method: 'POST', body: JSON.stringify(payload) }).then(setQuote).catch(setError).finally(() => setBusy(false));
      }}>{t('calculate')}</button><button type="submit" disabled={!quote || busy || !online}>{t(busy ? 'saving' : 'confirmSale')}</button><button type="button" className="secondary" disabled={busy} onClick={onCancel}>{t('cancel')}</button></div>
    </form>
  </section>;
}

