import { useRef } from 'react';
import { RecordForm, type FieldSpec, type RecordValues } from '../../components/RecordForm';
import { api } from '../../services/api';
import type { Transaction } from './types';

export function OperationForm({ path, fields, initial, transform, onDone, onCancel }: {
  path: string; fields: FieldSpec[]; initial?: RecordValues; transform?: (values: RecordValues) => RecordValues;
  onDone: (record: Transaction) => void | Promise<void>; onCancel?: () => void;
}) {
  const key = useRef(crypto.randomUUID());
  return <RecordForm fields={fields} initial={initial} onCancel={onCancel} onSave={async values => {
    const payload = transform ? transform(values) : Object.fromEntries(Object.entries(values).map(([key, value]) => [key, key.endsWith('_id') && value === '' ? null : value]));
    const result = await api<Transaction>(path, { method: 'POST', headers: { 'Idempotency-Key': key.current }, body: JSON.stringify(payload) });
    key.current = crypto.randomUUID();
    await onDone(result);
  }} />;
}

