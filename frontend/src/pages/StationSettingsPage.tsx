import { useMemo } from 'react';
import { LogoUpload } from '../components/LogoUpload';
import { RecordForm, type FieldSpec } from '../components/RecordForm';
import { useAuth } from '../features/auth/AuthContext';
import { languageChoices } from '../features/configuration/resources';
import { useStation } from '../features/station/StationContext';
import { useI18n } from '../i18n';
import { api, errorKey } from '../services/api';

const settingKeys = ['payment_methods', 'expense_categories', 'tax_enabled', 'tax_rate', 'cash_difference_threshold', 'stock_variance_threshold', 'opening_time', 'closing_time', 'receipt_width'];
export function StationSettingsPage() {
  const { t, language } = useI18n();
  const { reloadIdentity } = useAuth();
  const { station, loading, error, reloadStation } = useStation();
  const fields = useMemo<FieldSpec[]>(() => [
    { key: 'name', label: 'stationName', required: true }, { key: 'owner_name', label: 'ownerName', maxLength: 150 },
    { key: 'address', label: 'address', type: 'textarea' }, { key: 'province', label: 'province', maxLength: 100 }, { key: 'district', label: 'district', maxLength: 100 },
    { key: 'phone', label: 'phone', maxLength: 40 }, { key: 'email', label: 'email', type: 'email' },
    { key: 'currency', label: 'currency', required: true, maxLength: 3 }, { key: 'language', label: 'language', type: 'select', choices: languageChoices(t), required: true },
    { key: 'timezone', label: 'timezone', required: true, maxLength: 50 },
    { key: 'date_format', label: 'dateFormat', type: 'select', choices: ['yyyy-MM-dd', 'dd/MM/yyyy', 'MM/dd/yyyy'].map(value => ({ value, label: value })), required: true },
    { key: 'primary_color', label: 'primaryColor', type: 'color' }, { key: 'secondary_color', label: 'secondaryColor', type: 'color' },
    { key: 'receipt_header', label: 'receiptHeader', type: 'textarea' }, { key: 'receipt_footer', label: 'receiptFooter', type: 'textarea' },
    { key: 'payment_methods', label: 'paymentMethods', type: 'list' }, { key: 'expense_categories', label: 'expenseCategories', type: 'list' },
    { key: 'tax_enabled', label: 'taxEnabled', type: 'checkbox' }, { key: 'tax_rate', label: 'taxRate', type: 'decimal', step: '0.0001', defaultValue: '0' },
    { key: 'cash_difference_threshold', label: 'cashDifferenceThreshold', type: 'decimal', step: '0.0001', defaultValue: '0' },
    { key: 'stock_variance_threshold', label: 'stockVarianceThreshold', type: 'decimal', step: '0.0001', defaultValue: '0' },
    { key: 'opening_time', label: 'openingTime', type: 'time', defaultValue: '06:00' }, { key: 'closing_time', label: 'closingTime', type: 'time', defaultValue: '22:00' },
    { key: 'receipt_width', label: 'receiptWidth', type: 'select', defaultValue: '80', choices: [{ value: '58', label: '58' }, { value: '80', label: '80' }] },
  ], [language]);
  return <><div className="page-heading"><h1>{t('stationSettings')}</h1><p>{t('stationSettingsHelp')}</p></div>
    {loading && !station ? <p role="status">{t('loading')}</p> : error ? <div role="alert"><p className="error-message">{t(errorKey(error))}</p><button onClick={() => void reloadStation()}>{t('retry')}</button></div>
      : station && <>
        <section className="data-section"><RecordForm fields={fields} initial={{ ...station, ...station.settings }} editing key={station.id} onSave={async values => {
          const settings = Object.fromEntries(settingKeys.map(key => [key, values[key]]));
          const profile = Object.fromEntries(Object.entries(values).filter(([key]) => !settingKeys.includes(key)));
          await api('/station/', { method: 'PATCH', body: JSON.stringify({ ...profile, settings }) });
          await Promise.all([reloadStation(), reloadIdentity()]);
        }} /></section>
        <section className="data-section"><LogoUpload endpoint="/station/logo/" name={station.name} src={station.logo_url} onUploaded={reloadStation} />
          <p className="station-login-link">{t('stationLoginLink')}: <a href={'/login?station='+encodeURIComponent(station.slug)}>{location.origin+'/login?station='+station.slug}</a></p>
        </section>
      </>}
  </>;
}
