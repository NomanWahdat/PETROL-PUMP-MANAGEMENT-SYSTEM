export interface Assignment { id: string; nozzle: string; nozzle_label: string; product_name: string; tank: string; opening_meter: string; current_meter: string; unit_price: string; tax_rate: string; is_active: boolean }
export interface Shift { id: string; reference: string; day: string; business_date: string; attendant_name: string; status: string; opening_cash: string; current_expected_cash: string; assignments: Assignment[] }
export interface Options { open_shifts?: OpenShiftChoice[]; nozzles: { id: string; label: string; meter: string }[]; customers: { id: string; name: string }[]; attendants?: { id: string; name: string }[]; suppliers?: { id: string; name: string }[]; tanks?: { id: string; name: string; product_name: string; capacity: string; book_stock: string; minimum_stock: string; latest_physical: Record<string, unknown> | null }[]; cash_balance?: string; day?: { id: string; business_date: string; status: string } | null }
export interface Quote { opening_meter: string; closing_meter: string; liters: string; unit_price: string; subtotal: string; tax_rate: string; tax_amount: string; total: string; cash_amount: string }
export type Transaction = Record<string, unknown> & { id: string };
export interface OpenShiftChoice { id: string; label: string }

