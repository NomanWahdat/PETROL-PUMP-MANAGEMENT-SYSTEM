export const operationReadPermissions = {
  shifts: ['reports.operational', 'shifts.manage', 'shifts.own'],
  sales: ['reports.operational', 'shifts.manage', 'shifts.own'],
  'meter-readings': ['reports.operational', 'shifts.manage', 'shifts.own'],
  purchases: ['reports.operational', 'purchases.manage'],
  'customer-payments': ['reports.operational', 'customers.manage', 'shifts.own'],
  'inventory-movements': ['reports.operational', 'inventory.manage'],
  'physical-stock': ['reports.operational', 'inventory.manage'],
  'cash-movements': ['reports.operational', 'cash.manage'],
  'daily-closings': ['reports.operational', 'closing.manage'],
};
export type OperationKind = keyof typeof operationReadPermissions;
