import { useState, type FormEvent } from 'react';
import { useI18n, type TranslationKey } from '../i18n';
import { errorKey, ApiError } from '../services/api';
import { useConnection } from '../hooks/useConnection';

export type RecordValues = Record<string, unknown>;
export interface Choice { value: string; label: string }
export interface FieldSpec {
  key: string; label: TranslationKey;
  type?: 'text' | 'password' | 'email' | 'date' | 'time' | 'color' | 'decimal' | 'textarea' | 'checkbox' | 'select' | 'multiselect' | 'overrides' | 'list';
  required?: boolean; createOnly?: boolean; readOnlyEdit?: boolean; step?: string; maxLength?: number;
  choices?: Choice[]; reference?: string; defaultValue?: unknown;
  detail?: string;
}
const permissionKeys: Record<string, TranslationKey> = {
  'station.view': 'permStationView', 'station.manage': 'permStationManage', 'employees.manage': 'permEmployees',
  'access.manage': 'permAccess', 'fuel.view': 'permFuelView', 'fuel.manage': 'permFuelManage',
  'shifts.own': 'permOwnShift', 'shifts.manage': 'permShifts', 'reports.operational': 'permOperational',
  'reports.financial': 'permFinancial', 'accounting.manage': 'permAccounting', 'audit.view': 'permAudit',
  'purchases.manage': 'permPurchases', 'inventory.manage': 'permInventory', 'customers.manage': 'permCustomers', 'cash.manage': 'permCash', 'closing.manage': 'permClosing',
};
export function permissionLabel(key: string): TranslationKey { return permissionKeys[key] || 'permissions'; }

export function RecordForm({ fields, initial, editing = false, choices = {}, onSave, onCancel }: {
  fields: FieldSpec[]; initial?: RecordValues; editing?: boolean; choices?: Record<string, Choice[]>;
  onSave: (values: RecordValues) => Promise<void>; onCancel?: () => void;
}) {
  const { t } = useI18n();
  const online = useConnection();
  const [values, setValues] = useState<RecordValues>(() => Object.fromEntries(fields.map(field => [field.key, initial?.[field.key] ?? field.defaultValue ?? (field.type === 'checkbox' ? false : field.type === 'overrides' ? {} : '')])));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const errors = error instanceof ApiError ? error.details : undefined;
  const visible = fields.filter(field => !editing || !field.createOnly);
  function update(key: string, value: unknown) { setValues(previous => ({ ...previous, [key]: value })); setSaved(false); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !online) return;
    const missing = visible.find(field => field.required && field.type === 'multiselect' && (!Array.isArray(values[field.key]) || !(values[field.key] as unknown[]).length));
    if (missing) { setError(new ApiError('invalid', 400, { [missing.key]: true })); return; }
    setBusy(true); setError(null); setSaved(false);
    const payload = Object.fromEntries(visible.filter(field => !editing || !field.readOnlyEdit).map(field => {
      let value = values[field.key];
      if (field.type === 'list' && typeof value === 'string') value = value.split(/[,،\n]/).map(v => v.trim()).filter(Boolean);
      if ((field.type === 'date' || field.reference) && value === '') value = null;
      return [field.key, value];
    }).filter(([key, value]) => !(editing && fields.find(field => field.key === key)?.type === 'password' && !value)));
    try { await onSave(payload); setSaved(true); }
    catch (error) { setError(error); }
    finally { setBusy(false); }
  }
  return <form onSubmit={event => void submit(event)} className="record-form">
    <div className="form-grid">
      {visible.map(field => {
        const id = `field-${field.key}`;
        const type = field.type || 'text';
        const invalid = Boolean(errors?.[field.key]);
        const disabled = busy || (editing && field.readOnlyEdit);
        const options = field.choices || choices[field.key] || [];
        if (type === 'overrides') return <fieldset className="wide" key={field.key}><legend>{t(field.label)}</legend>
          <p className="muted">{t('overrideHelp')}</p>
          <div className="permission-grid">{Object.keys(permissionKeys).map(permission => {
            const overrides = (values[field.key] || {}) as Record<string, boolean>;
            return <label key={permission}><span>{t(permissionLabel(permission))}</span>
              <select disabled={busy} value={permission in overrides ? String(overrides[permission]) : 'inherit'} onChange={event => {
                const next = { ...overrides };
                if (event.target.value === 'inherit') delete next[permission]; else next[permission] = event.target.value === 'true';
                update(field.key, next);
              }}><option value="inherit">{t('inherit')}</option><option value="true">{t('allow')}</option><option value="false">{t('deny')}</option></select>
            </label>;
          })}</div>
        </fieldset>;
        if (type === 'checkbox') return <label key={field.key} className="checkbox-field" htmlFor={id}>
          <input id={id} type="checkbox" checked={Boolean(values[field.key])} disabled={disabled} onChange={event => update(field.key, event.target.checked)} />{t(field.label)}
        </label>;
        if (type === 'multiselect') return <fieldset key={field.key} className="nozzle-field" aria-invalid={invalid}>
          <legend>{t(field.label)}{field.required ? ' *' : ''}</legend>
          <div className="nozzle-choices">{options.map(option => <label className="checkbox-field" key={option.value}><input type="checkbox" checked={Array.isArray(values[field.key]) && (values[field.key] as string[]).includes(option.value)} disabled={disabled} onChange={event => {
            const selected = Array.isArray(values[field.key]) ? values[field.key] as string[] : [];
            update(field.key, event.target.checked ? [...selected, option.value] : selected.filter(value => value !== option.value));
          }} />{option.label}</label>)}</div>
          {options.length === 0 && <p>{t('noRecords')}</p>}
          {invalid && <small className="error-text">{t('errorValidation')}</small>}
        </fieldset>;
        const value = Array.isArray(values[field.key]) ? (values[field.key] as string[]).join(', ') : String(values[field.key] ?? '');
        return <label key={field.key} htmlFor={id} className={type === 'textarea' || type === 'list' ? 'wide' : ''}>
          <span>{t(field.label)}{field.detail ? ` — ${field.detail}` : ''}{field.required ? ' *' : ''}</span>
          {type === 'select' || field.reference ? <select id={id} required={field.required} disabled={disabled} value={value} aria-invalid={invalid} onChange={event => update(field.key, event.target.value)}>
            <option value="">{t('choose')}</option>{options.map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
          </select> : type === 'textarea' || type === 'list' ? <textarea id={id} value={value} required={field.required} disabled={disabled} maxLength={field.maxLength || 4000} aria-invalid={invalid} onChange={event => update(field.key, event.target.value)} />
            : <input id={id} type={type === 'decimal' ? 'number' : type} step={field.step || '0.001'} min={type === 'decimal' ? '0' : undefined}
              value={value} required={field.required && !(editing && type === 'password')} disabled={disabled} maxLength={field.maxLength || (type === 'password' ? 256 : 200)} autoComplete={type === 'password' ? 'new-password' : undefined}
              dir={type === 'color' ? 'ltr' : 'auto'} aria-invalid={invalid} onChange={event => update(field.key, event.target.value)} />}
          {invalid && <small className="error-text">{t('errorValidation')}</small>}
        </label>;
      })}
    </div>
    {error != null && <p role="alert" className="error-message">{t(errorKey(error))}</p>}
    {!online && <p role="status" className="notice">{t('offlineHelp')}</p>}
    {saved && <p role="status" className="success-message">{t('saved')}</p>}
    <div className="form-actions"><button type="submit" disabled={busy || !online}>{t(busy ? 'saving' : 'save')}</button>
      {onCancel && <button type="button" className="secondary" disabled={busy} onClick={onCancel}>{t('cancel')}</button>}
    </div>
  </form>;
}
