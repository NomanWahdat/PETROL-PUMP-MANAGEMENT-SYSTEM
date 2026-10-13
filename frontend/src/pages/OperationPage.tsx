import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { useStation } from '../features/station/StationContext';
import { useI18n, type TranslationKey } from '../i18n';
import { api, errorKey } from '../services/api';
import type { Page } from '../types/api';
import type { FieldSpec } from '../components/RecordForm';
import { OperationForm } from '../features/operations/OperationForm';
import type { Options, Transaction } from '../features/operations/types';

type Kind = 'sales' | 'shifts' | 'purchases' | 'customer-payments' | 'meter-readings' | 'inventory-movements' | 'physical-stock' | 'cash-movements' | 'daily-closings';
const specs: Record<Kind, { title: TranslationKey; columns: [string, TranslationKey][]; createPermission?: string; reversePermission?: string }> = {
  sales: { title: 'fuelSales', columns: [['reference', 'reference'], ['created_at', 'date'], ['liters', 'litersSold'], ['total', 'totalAmount'], ['cash_amount', 'cashAmount'], ['credit_amount', 'creditAmount'], ['status', 'status']], reversePermission: 'shifts.manage' },
  shifts: { title: 'shiftHistory', columns: [['reference', 'reference'], ['business_date', 'businessDate'], ['attendant_name', 'attendant'], ['status', 'status'], ['opening_cash', 'openingCash'], ['counted_cash', 'countedCash'], ['cash_difference', 'cashDifference']] },
  purchases: { title: 'purchases', columns: [['reference', 'reference'], ['supplier_name', 'supplier'], ['tank_name', 'tank'], ['quantity', 'quantity'], ['unit_cost', 'unitCost'], ['total', 'totalAmount'], ['paid_amount', 'paidAmount'], ['status', 'status']], createPermission: 'purchases.manage', reversePermission: 'purchases.manage' },
  'customer-payments': { title: 'customerPayments', columns: [['reference', 'reference'], ['customer_name', 'customer'], ['amount', 'paidAmount'], ['method', 'paymentMethod'], ['status', 'status'], ['created_at', 'date']], createPermission: 'customers.manage', reversePermission: 'customers.manage' },
  'meter-readings': { title: 'meterReadings', columns: [['created_at', 'date'], ['nozzle_label', 'nozzles'], ['opening_meter', 'openingMeter'], ['closing_meter', 'closingMeter'], ['liters', 'litersSold'], ['kind', 'action']] },
  'inventory-movements': { title: 'inventoryMovements', columns: [['created_at', 'date'], ['tank_name', 'tank'], ['quantity', 'quantity'], ['kind', 'action'], ['notes', 'reason']] },
  'physical-stock': { title: 'physicalStock', columns: [['created_at', 'date'], ['tank_name', 'tank'], ['expected_quantity', 'bookStock'], ['measured_quantity', 'measuredStock'], ['variance', 'stockVariance'], ['adjustment_applied', 'applyAdjustment']], createPermission: 'inventory.manage' },
  'cash-movements': { title: 'cashMovements', columns: [['created_at', 'date'], ['kind', 'action'], ['amount', 'totalAmount'], ['notes', 'reason']], createPermission: 'cash.manage' },
  'daily-closings': { title: 'dailyClosing', columns: [['business_date', 'businessDate'], ['status', 'status'], ['opening_cash', 'openingStationCash'], ['expected_cash', 'expectedCash'], ['counted_cash', 'countedCash'], ['cash_difference', 'cashDifference']] },
};
const labelKeys: Record<string, TranslationKey> = { posted: 'posted', reversed: 'reversed', open: 'open', closed: 'closed', cash: 'cash', bank: 'bank', sale: 'fuelSales', purchase: 'purchases', customer_payment: 'customerPayments', deposit: 'deposit', withdrawal: 'withdrawal', reversal: 'reversed', correction: 'stockAdjustment', adjustment: 'stockAdjustment', reconciliation: 'cashReconciliation' };

export function OperationPage({ kind }: { kind: Kind }) {
  const spec = specs[kind];
  const { user } = useAuth();
  const { station } = useStation();
  const { t, language } = useI18n();
  const [records, setRecords] = useState<Page<Transaction> | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [modal, setModal] = useState<{ path: string; action: 'create' | 'reverse' | 'reopen' | 'close'; record?: Transaction } | null>(null);
  const [detail, setDetail] = useState<Transaction | null>(null);
  const requestSequence = useRef(0);
  const allowed = (permission?: string) => Boolean(permission && user?.permissions.includes(permission));
  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setError(null);
    try {
      const [list, choices] = await Promise.all([api<Page<Transaction>>('/'+kind+'/?page='+page+'&search='+encodeURIComponent(query)+'&status='+status), api<Options>('/operations/options/')]);
      if (sequence === requestSequence.current) { setRecords(list); setOptions(choices); }
    } catch (error) { if (sequence === requestSequence.current) setError(error); }
  }, [kind, page, query, status]);
  useEffect(() => { setRecords(null); void load(); return () => { requestSequence.current += 1; }; }, [load]);
  const fields = useMemo<FieldSpec[]>(() => {
    if (!modal) return [];
    if (modal.action === 'reverse' || modal.action === 'reopen') return [{ key: 'reason', label: 'reason', type: 'textarea', required: true }];
    if (modal.action === 'close') return [{ key: 'counted_cash', label: 'countedCash', type: 'decimal', step: '0.01', required: true }, { key: 'reason', label: 'reason', type: 'textarea' }];
    const methods: FieldSpec = { key: 'method', label: 'paymentMethod', type: 'select', defaultValue: 'cash', choices: [{ value: 'cash', label: t('cash') }, { value: 'bank', label: t('bank') }] };
    const tank: FieldSpec = { key: 'tank_id', label: 'tank', type: 'select', required: true, choices: options?.tanks?.map(tank => ({ value: tank.id, label: tank.name })) };
    const shift: FieldSpec = { key: 'shift_id', label: 'myShift', type: 'select', choices: options?.open_shifts?.map(shift => ({ value: shift.id, label: shift.label })) };
    if (kind === 'purchases') return [
      { key: 'supplier_id', label: 'supplier', type: 'select', required: true, choices: options?.suppliers?.map(supplier => ({ value: supplier.id, label: supplier.name })) }, tank,
      { key: 'quantity', label: 'quantity', type: 'decimal', required: true }, { key: 'unit_cost', label: 'unitCost', type: 'decimal', step: '0.0001', required: true },
      { key: 'paid_amount', label: 'paidAmount', type: 'decimal', step: '0.01', defaultValue: '0.00' }, methods,
      { key: 'invoice_number', label: 'invoiceNumber' }, { key: 'notes', label: 'notes', type: 'textarea' },
    ];
    if (kind === 'customer-payments') return [
      shift,
      { key: 'customer_id', label: 'customer', type: 'select', required: true, choices: options?.customers.map(customer => ({ value: customer.id, label: customer.name })) },
      { key: 'amount', label: 'paidAmount', type: 'decimal', step: '0.01', required: true }, methods, { key: 'notes', label: 'notes', type: 'textarea' },
    ];
    if (kind === 'physical-stock') return [tank, { key: 'measured_quantity', label: 'measuredStock', type: 'decimal', required: true }, { key: 'apply_adjustment', label: 'applyAdjustment', type: 'checkbox' }, { key: 'reason', label: 'reason', type: 'textarea' }];
    if (kind === 'cash-movements') return [
      shift,
      { key: 'kind', label: 'action', type: 'select', required: true, defaultValue: 'deposit', choices: [{ value: 'deposit', label: t('deposit') }, { value: 'withdrawal', label: t('withdrawal') }] },
      { key: 'amount', label: 'totalAmount', type: 'decimal', step: '0.01', required: true }, { key: 'reason', label: 'reason', type: 'textarea', required: true },
    ];
    return [];
  }, [kind, modal, options, language]);
  function display(key: string, value: unknown) {
    if (value == null || value === '') return '—';
    if (typeof value === 'boolean') return t(value ? 'yes' : 'no');
    if (labelKeys[String(value)] && ['status', 'kind', 'method'].includes(key)) return t(labelKeys[String(value)]);
    if (key === 'created_at') return new Intl.DateTimeFormat(language === 'fa' ? 'fa-AF' : language === 'ps' ? 'ps-AF' : 'en', { dateStyle: 'short', timeStyle: 'short', calendar: 'gregory', timeZone: station?.timezone || 'Asia/Kabul' }).format(new Date(String(value)));
    return String(value);
  }
  const snapshot = detail?.snapshot as Record<string, unknown> | undefined;
  return <><div className="page-heading page-heading-actions"><h1>{t(spec.title)}</h1>
    {allowed(spec.createPermission) && !modal && <button onClick={() => setModal({ path: '/'+kind+'/', action: 'create' })}>{t('addNew')}</button>}
    {kind === 'shifts' && allowed('shifts.manage') && <Link className="button-link" to="/work">{t('myShift')}</Link>}
  </div>
  {kind === 'daily-closings' && <p>{t('dailyClosingHelp')}</p>}
  {kind === 'physical-stock' && <p>{t('stockHelp')}</p>}
  {kind === 'cash-movements' && options?.cash_balance != null && <p className="ledger-balance">{t('expectedCash')}: <strong><bdi>{options.cash_balance}</bdi> {station?.currency}</strong></p>}
  {modal && <section className="data-section"><h2>{t(modal.action === 'reverse' ? 'reverseTransaction' : modal.action === 'reopen' ? kind === 'shifts' ? 'reopenShift' : 'reopenDay' : modal.action === 'close' ? 'closeDay' : 'addNew')}</h2>
    {modal.action === 'reverse' && <p>{t(kind === 'sales' ? 'reverseMeterHelp' : 'reversalHelp')}</p>}
    <OperationForm key={modal.path} path={modal.path} fields={fields} onCancel={() => setModal(null)} onDone={async () => { setModal(null); await load(); }} />
  </section>}
  {error != null && <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => void load()}>{t('retry')}</button></div>}
  {detail && <section className="data-section"><div className="page-heading-actions"><h2>{t('dailyClosing')} · {String(detail.business_date)}</h2><button className="secondary" onClick={() => setDetail(null)}>{t('cancel')}</button></div>
    {snapshot && <><dl className="detail-list">{([['sales_total', 'totalAmount'], ['liters_sold', 'litersSold'], ['credit_sales', 'creditAmount'], ['customer_payments', 'customerPayments'], ['purchase_total', 'purchases'], ['cash_in', 'deposit'], ['cash_out', 'withdrawal']] as [string, TranslationKey][]).map(([key,label]) => <div key={key}><dt>{t(label)}</dt><dd><bdi>{String(snapshot[key] ?? '—')}</bdi></dd></div>)}</dl>
    <div className="table-scroll"><table><thead><tr>{(['tank', 'bookStock', 'measuredStock', 'stockVariance'] as const).map(key => <th key={key}>{t(key)}</th>)}</tr></thead><tbody>{(snapshot.tanks as Record<string, unknown>[] || []).map(tank => <tr key={String(tank.tank_id)}><td>{String(tank.name)}</td><td><bdi>{String(tank.book_stock)}</bdi></td><td><bdi>{String(tank.physical_stock)}</bdi></td><td><bdi>{String(tank.variance)}</bdi></td></tr>)}</tbody></table></div></>}
  </section>}
  <form className="table-tools" onSubmit={event => { event.preventDefault(); setPage(1); setQuery(search); }}>
    {!['daily-closings', 'meter-readings'].includes(kind) && <><label><span>{t('search')}</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} /></label><button className="secondary">{t('search')}</button></>}
    {['sales', 'shifts', 'purchases', 'customer-payments'].includes(kind) && <label><span>{t('status')}</span><select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">{t('all')}</option>{(kind === 'shifts' ? ['open', 'closed'] : ['posted', 'reversed']).map(value => <option key={value} value={value}>{t(labelKeys[value])}</option>)}</select></label>}
  </form>
  {!records ? error == null && <p role="status">{t('loading')}</p> : <><div className="table-scroll"><table><caption className="sr-only">{t(spec.title)}</caption><thead><tr>{spec.columns.map(([key,label]) => <th scope="col" key={key}>{t(label)}</th>)}<th scope="col">{t('actions')}</th></tr></thead><tbody>{records.results.map(record => <tr key={record.id}>{spec.columns.map(([key]) => <td key={key}><bdi>{display(key,record[key])}</bdi></td>)}<td><div className="row-actions">
    {kind === 'sales' && <Link to={'/receipts/'+record.id}>{t('receipt')}</Link>}
    {kind === 'customer-payments' && <Link to={'/payment-receipts/'+record.id}>{t('receipt')}</Link>}
    {kind === 'shifts' && record.status === 'open' && <Link to={'/work?shift='+record.id}>{t('continueShift')}</Link>}
    {kind === 'shifts' && record.status === 'closed' && allowed('shifts.manage') && <button className="secondary compact" onClick={() => setModal({ path: '/shifts/'+record.id+'/reopen/', action: 'reopen', record })}>{t('reopenShift')}</button>}
    {record.status === 'posted' && allowed(spec.reversePermission) && <button className="secondary compact" onClick={() => setModal({ path: '/'+kind+'/'+record.id+'/reverse/', action: 'reverse', record })}>{t('reverseTransaction')}</button>}
    {kind === 'daily-closings' && <><button className="secondary compact" onClick={() => setDetail(record)}>{t('overview')}</button>{allowed('closing.manage') && <button className="secondary compact" onClick={() => setModal({ path: '/daily-closings/'+record.id+'/'+(record.status === 'open' ? 'close' : 'reopen')+'/', action: record.status === 'open' ? 'close' : 'reopen', record })}>{t(record.status === 'open' ? 'closeDay' : 'reopenDay')}</button>}</>}
  </div></td></tr>)}</tbody></table></div>{records.count === 0 && <p>{t('noRecords')}</p>}
  <div className="pagination"><span>{t('records')}: {records.count}</span><button className="secondary" disabled={!records.previous} onClick={() => setPage(value => value-1)}>{t('previous')}</button><span>{page}</span><button className="secondary" disabled={!records.next} onClick={() => setPage(value => value+1)}>{t('next')}</button></div></>}
  </>;
}

