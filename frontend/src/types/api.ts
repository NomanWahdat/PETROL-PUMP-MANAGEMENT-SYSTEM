export type Language = 'fa' | 'ps' | 'en';
export interface User {
  id: string;
  username: string;
  display_name: string;
  language: Language;
  is_superadmin: boolean;
  tenant: { id: string; name: string } | null;
  role: 'owner' | 'manager' | 'worker' | 'accountant' | 'superadmin' | 'unassigned';
  permissions: string[];
}
export interface Station {
  id: string;
  slug: string;
  name: string;
  address: string;
  phone: string;
  currency: string;
  language: Language;
  timezone: string;
  primary_color: string;
  secondary_color: string;
  logo_url: string;
  province?: string;
  district?: string;
  email?: string;
  owner_name?: string;
  date_format?: string;
  receipt_header?: string;
  receipt_footer?: string;
  settings?: Record<string, unknown>;
}
export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
export interface StationChoice { id: string; name: string; role: User['role'] }
