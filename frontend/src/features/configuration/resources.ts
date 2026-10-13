import type { FieldSpec } from '../../components/RecordForm';
import type { ResourceSpec } from '../../pages/RecordsPage';
import type { User } from '../../types/api';
import type { TranslationKey } from '../../i18n';

type Translate = (key: TranslationKey) => string;
const active: FieldSpec = { key: 'is_active', label: 'active', type: 'checkbox', defaultValue: true };
const notes: FieldSpec = { key: 'notes', label: 'notes', type: 'textarea' };
const name: FieldSpec = { key: 'name', label: 'displayName', required: true, maxLength: 100 };
const products = '/fuel/products/';
const roleKeys = { owner: 'roleOwner', manager: 'roleManager', worker: 'roleWorker', accountant: 'roleAccountant' } as const;
export function roleChoices(t: Translate, workerOnly = false) {
  return Object.entries(roleKeys).filter(([role]) => !workerOnly || role === 'worker').map(([value, label]) => ({ value, label: t(label) }));
}
export function languageChoices(t: Translate) {
  return [{ value: 'fa', label: t('languageFa') }, { value: 'ps', label: t('languagePs') }, { value: 'en', label: t('languageEn') }];
}

export function resourceSpec(kind: string, user: User, t: Translate): ResourceSpec {
  const canWriteFuel = user.permissions.includes('fuel.manage');
  const canAccess = user.permissions.includes('access.manage');
  const statusColumn = { key: 'is_active', label: 'status' as const };
  const definitions: Record<string, ResourceSpec> = {
    suppliers: { title: 'suppliers', path: '/suppliers/', canWrite: user.permissions.includes('purchases.manage'),
      columns: [{ key: 'name', label: 'supplier' }, { key: 'code', label: 'code' }, { key: 'phone', label: 'phone' }, { key: 'balance', label: 'balance' }, statusColumn],
      fields: [name, { key: 'code', label: 'code', required: true, maxLength: 40 }, { key: 'phone', label: 'phone', maxLength: 40 }, { key: 'address', label: 'address', type: 'textarea' }, active, notes] },
    customers: { title: 'customers', path: '/customers/', canWrite: user.permissions.includes('customers.manage'),
      columns: [{ key: 'name', label: 'customer' }, { key: 'code', label: 'code' }, { key: 'phone', label: 'phone' }, { key: 'credit_limit', label: 'creditLimit' }, { key: 'balance', label: 'balance' }, statusColumn],
      fields: [name, { key: 'code', label: 'code', required: true, maxLength: 40 }, { key: 'phone', label: 'phone', maxLength: 40 }, { key: 'address', label: 'address', type: 'textarea' }, { key: 'credit_limit', label: 'creditLimit', type: 'decimal', step: '0.01', defaultValue: '0.00' }, { key: 'opening_balance', label: 'openingDebt', type: 'decimal', step: '0.01', defaultValue: '0.00', readOnlyEdit: true }, active, notes] },
    products: { title: 'fuelProducts', path: products, canWrite: canWriteFuel,
      columns: [{ key: 'name', label: 'displayName' }, { key: 'code', label: 'code' }, { key: 'unit', label: 'unit' }, { key: 'purchase_price', label: 'purchasePrice' }, { key: 'selling_price', label: 'sellingPrice' }, statusColumn],
      fields: [name, { key: 'code', label: 'code', required: true, maxLength: 30 }, { key: 'unit', label: 'unit', required: true, defaultValue: 'liter', maxLength: 30 },
        { key: 'purchase_price', label: 'purchasePrice', type: 'decimal', step: '0.0001', defaultValue: '0' },
        { key: 'selling_price', label: 'sellingPrice', type: 'decimal', step: '0.0001', defaultValue: '0' },
        { key: 'minimum_stock', label: 'minimumStock', type: 'decimal', defaultValue: '0' }, active,
        { key: 'price_reason', label: 'priceReason', maxLength: 250 }, notes] },
    tanks: { title: 'tanks', path: '/tanks/', canWrite: canWriteFuel,
      columns: [{ key: 'name', label: 'displayName' }, { key: 'product', label: 'fuelProduct' }, { key: 'capacity', label: 'capacity' }, { key: 'opening_quantity', label: 'openingQuantity' }, statusColumn],
      fields: [name, { key: 'product', label: 'fuelProduct', required: true, reference: products }, { key: 'capacity', label: 'capacity', type: 'decimal', required: true },
        { key: 'opening_quantity', label: 'openingQuantity', type: 'decimal', defaultValue: '0' }, { key: 'minimum_stock', label: 'minimumStock', type: 'decimal', defaultValue: '0' }, active, notes] },
    pumps: { title: 'pumps', path: '/pumps/', canWrite: canWriteFuel,
      columns: [{ key: 'name', label: 'displayName' }, { key: 'number', label: 'number' }, { key: 'location', label: 'location' }, { key: 'status', label: 'status' }, statusColumn],
      fields: [name, { key: 'number', label: 'number', required: true, maxLength: 30 }, { key: 'location', label: 'location' },
        { key: 'status', label: 'status', type: 'select', defaultValue: 'ready', choices: [{ value: 'ready', label: t('ready') }, { value: 'maintenance', label: t('maintenance') }] }, active] },
    nozzles: { title: 'nozzles', path: '/nozzles/', canWrite: canWriteFuel,
      columns: [{ key: 'number', label: 'number' }, { key: 'pump', label: 'pump' }, { key: 'product', label: 'fuelProduct' }, { key: 'tank', label: 'tank' }, { key: 'opening_meter', label: 'openingMeter' }, statusColumn],
      fields: [{ key: 'number', label: 'number', required: true, maxLength: 30 }, { key: 'pump', label: 'pump', required: true, reference: '/pumps/' },
        { key: 'product', label: 'fuelProduct', required: true, reference: products }, { key: 'tank', label: 'tank', reference: '/tanks/' },
        { key: 'opening_meter', label: 'openingMeter', type: 'decimal', defaultValue: '0', readOnlyEdit: true }, active, notes] },
    employees: { title: 'employees', path: '/employees/', canWrite: true,
      canEdit: row => canAccess || row.role === 'worker',
      columns: [{ key: 'name', label: 'displayName' }, { key: 'username', label: 'username' }, { key: 'role', label: 'role' }, { key: 'phone', label: 'phone' }, statusColumn],
      fields: [name, { key: 'username', label: 'username', required: true, readOnlyEdit: true, maxLength: 150 },
        { key: 'password', label: 'password', type: 'password', required: true, ...(canAccess ? {} : { createOnly: true }) },
        { key: 'role', label: 'role', type: 'select', choices: roleChoices(t, !canAccess), defaultValue: 'worker', required: true },
        { key: 'phone', label: 'phone', maxLength: 40 }, { key: 'address', label: 'address', type: 'textarea' }, { key: 'job_title', label: 'jobTitle', maxLength: 100 },
        { key: 'joined_on', label: 'joinedOn', type: 'date' }, active, notes,
        ...(canAccess ? [{ key: 'permission_overrides', label: 'permissionOverrides', type: 'overrides' } as FieldSpec] : [])] },
    tenants: { title: 'tenants', path: '/platform/tenants/', canWrite: true,
      columns: [{ key: 'name', label: 'stationName' }, { key: 'slug', label: 'stationCode' }, { key: 'owner_username_display', label: 'ownerUsername' }, statusColumn],
      fields: [name, { key: 'slug', label: 'stationCode', required: true }, active,
        { key: 'owner_name', label: 'ownerName', required: true, createOnly: true, maxLength: 150 }, { key: 'owner_username', label: 'ownerUsername', required: true, createOnly: true, maxLength: 150 },
        { key: 'owner_password', label: 'ownerPassword', type: 'password', required: true, createOnly: true },
        { key: 'language', label: 'language', type: 'select', choices: languageChoices(t), defaultValue: 'fa', createOnly: true },
        { key: 'primary_color', label: 'primaryColor', type: 'color', defaultValue: '#215b48' }, { key: 'secondary_color', label: 'secondaryColor', type: 'color', defaultValue: '#64748b' }] },
    users: { title: 'systemUsers', path: '/platform/users/', canWrite: true,
      columns: [{ key: 'username', label: 'username' }, { key: 'first_name', label: 'firstName' }, { key: 'last_name', label: 'lastName' }, { key: 'is_superuser', label: 'systemAdministrator' }, statusColumn],
      fields: [{ key: 'username', label: 'username', required: true, readOnlyEdit: true, maxLength: 150 }, { key: 'password', label: 'password', type: 'password', required: true, createOnly: true },
        { key: 'first_name', label: 'firstName', maxLength: 150 }, { key: 'last_name', label: 'lastName', maxLength: 150 }, { key: 'email', label: 'email', type: 'email' }, active,
        { key: 'is_superuser', label: 'systemAdministrator', type: 'checkbox' },
        { key: 'preferred_language', label: 'language', type: 'select', choices: languageChoices(t), defaultValue: 'fa' },
        { key: 'tenant_id', label: 'stationName', reference: '/platform/tenants/', createOnly: true }, { key: 'role', label: 'role', type: 'select', choices: roleChoices(t), defaultValue: 'worker', createOnly: true }] },
    compliance: { title: 'compliance', path: '/station/compliance/', canWrite: true,
      columns: [{ key: 'title', label: 'title' }, { key: 'authority', label: 'authority' }, { key: 'reference', label: 'reference' }, { key: 'expiry_date', label: 'expiryDate' }, { key: 'status', label: 'status' }],
      fields: [{ key: 'title', label: 'title', required: true }, { key: 'authority', label: 'authority' }, { key: 'reference', label: 'reference' }, { key: 'source_url', label: 'sourceUrl' },
        { key: 'issue_date', label: 'issueDate', type: 'date' }, { key: 'expiry_date', label: 'expiryDate', type: 'date' }, { key: 'status', label: 'status', required: true, defaultValue: t('pending') }, notes] },
    audit: { title: 'systemAudit', path: '/platform/audit/', canWrite: false, fields: [],
      columns: [{ key: 'actor', label: 'username' }, { key: 'action', label: 'action' }, { key: 'object_id', label: 'reference' }, { key: 'created_at', label: 'date' }] },
  };
  return definitions[kind];
}
