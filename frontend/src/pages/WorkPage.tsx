import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { useI18n } from '../i18n';
import { api } from '../services/api';
import { errorKey } from '../services/api';
import type { Page } from '../types/api';
import type { FieldSpec } from '../components/RecordForm';
import { OperationForm } from '../features/operations/OperationForm';
import { SaleEntry } from '../features/operations/SaleEntry';
import type { Assignment, Options, Shift } from '../features/operations/types';

export function WorkPage({ embedded = false }: { embedded?: boolean }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const manager = Boolean(user?.permissions.includes('shifts.manage'));
  const [options, setOptions] = useState<Options | null>(null);
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [selected, setSelected] = useState(() => new URLSearchParams(location.search).get('shift') || '');
  const [mode, setMode] = useState<'start' | 'close' | 'payment' | null>(null);
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [paymentReceipt, setPaymentReceipt] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setError(null);
    try {
      const [choices, list] = await Promise.all([api<Options>('/operations/options/'), api<Page<Shift>>('/shifts/?status=open&page_size=200')]);
      setOptions(choices); setShifts(list.results);
    } catch (error) { setError(error); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const shift = shifts.find(shift => shift.id === selected) || shifts[0];
  const startFields: FieldSpec[] = [
    ...(manager ? [{ key: 'attendant_id', label: 'attendant', type: 'select', choices: options?.attendants?.map(employee => ({ value: employee.id, label: employee.name })) } as FieldSpec] : []),
    { key: 'nozzle_ids', label: 'availableNozzles', type: 'multiselect', required: true, defaultValue: [], choices: options?.nozzles.map(nozzle => ({ value: nozzle.id, label: nozzle.label })) || [] },
    { key: 'opening_cash', label: 'openingCash', type: 'decimal', step: '0.01', defaultValue: '0.00', required: true },
  ];
  const Heading = embedded ? 'h2' : 'h1';
  return <><div className="page-heading page-heading-actions"><Heading>{t('myShift')}</Heading>{manager && shift && mode !== 'start' && <button onClick={() => { setMode('start'); setAssignment(null); }}>{t('startShift')}</button>}</div>
    {error != null && <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => void load()}>{t('retry')}</button></div>}
    {loading ? <p role="status">{t('loading')}</p> : options && <>
      {paymentReceipt && <p className="success-message" role="status">{t('transactionSaved')} <Link to={'/payment-receipts/'+paymentReceipt}>{t('receipt')}</Link></p>}
      {(!shift || mode === 'start') && <section className="data-section"><h2>{t('startShift')}</h2><p>{t('selectNozzlesHelp')}</p>
        <OperationForm path="/shifts/" fields={startFields} onCancel={shift ? () => setMode(null) : undefined} transform={values => ({ ...values, attendant_id: values.attendant_id || null })} onDone={async result => { setSelected(result.id); setMode(null); await load(); }} />
      </section>}
      {shift && mode !== 'start' && <>
        {manager && shifts.length > 1 && <label className="role-select"><span>{t('attendant')}</span><select value={shift.id} onChange={event => { setSelected(event.target.value); setMode(null); setAssignment(null); }}>{shifts.map(shift => <option key={shift.id} value={shift.id}>{shift.reference} — {shift.attendant_name}</option>)}</select></label>}
        <section className="shift-summary data-section"><h2>{shift.reference} · {shift.attendant_name}</h2><p>{t('businessDate')}: <bdi>{shift.business_date}</bdi> · {t('expectedCash')}: <bdi>{shift.current_expected_cash}</bdi></p>
          <div className="nozzle-actions">{shift.assignments.map(item => <button className="secondary nozzle-action" key={item.id} onClick={() => { setAssignment(item); setMode(null); }}><strong>{item.nozzle_label}</strong><span>{item.product_name} · <bdi>{item.current_meter}</bdi></span><span>{t('recordReading')}</span></button>)}</div>
          <div className="form-actions"><button className="secondary" onClick={() => { setMode('payment'); setAssignment(null); }}>{t('recordPayment')}</button><button onClick={() => { setMode('close'); setAssignment(null); }}>{t('closeShift')}</button></div>
        </section>
        {assignment && <SaleEntry key={assignment.id} assignment={shift.assignments.find(item => item.id === assignment.id) || assignment} customers={options.customers} onCancel={() => setAssignment(null)} onDone={load} />}
        {mode === 'close' && <section className="data-section"><h2>{t('closeShift')}</h2><p>{t('closeShiftHelp')}</p>
          <OperationForm path={'/shifts/'+shift.id+'/close/'} fields={[
            ...shift.assignments.map(item => ({ key: 'meter_'+item.id, label: 'closingMeter', detail: item.nozzle_label, type: 'decimal', defaultValue: item.current_meter, required: true } as FieldSpec)),
            { key: 'counted_cash', label: 'countedCash', type: 'decimal', step: '0.01', required: true },
            ...(manager ? [{ key: 'reason', label: 'reason', type: 'textarea' } as FieldSpec] : []),
          ]} onCancel={() => setMode(null)} transform={values => ({ closing_meters: Object.fromEntries(shift.assignments.map(item => [item.id, values['meter_'+item.id]])), counted_cash: values.counted_cash, reason: values.reason || '' })} onDone={async () => { setMode(null); setAssignment(null); await load(); }} />
        </section>}
        {mode === 'payment' && <section className="data-section"><h2>{t('recordPayment')}</h2><OperationForm path="/customer-payments/" fields={[
          { key: 'customer_id', label: 'customer', type: 'select', required: true, choices: options.customers.map(customer => ({ value: customer.id, label: customer.name })) },
          { key: 'amount', label: 'paidAmount', type: 'decimal', step: '0.01', required: true },
          { key: 'method', label: 'paymentMethod', type: 'select', defaultValue: 'cash', choices: [{ value: 'cash', label: t('cash') }, { value: 'bank', label: t('bank') }] },
        ]} onCancel={() => setMode(null)} transform={values => ({ ...values, shift_id: shift.id })} onDone={async result => { setPaymentReceipt(result.id); setMode(null); await load(); }} /></section>}
      </>}
      <p><Link to="/operations/sales">{t('fuelSales')}</Link></p>
    </>}
  </>;
}

