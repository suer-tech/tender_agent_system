// Клиент для /api/* эндпоинтов.

export interface BenchData {
  source: 'cache' | 'live';
  okpd2_prefix: string;
  region_code: string;
  period_months?: number;
  sample_size: number;
  nmck_median: number | null;
  nmck_p25?: number | null;
  nmck_p75?: number | null;
  final_price_median: number | null;
  discount_pct_median: number | null;
  discount_pct_p25: number | null;
  discount_pct_p75: number | null;
  contracts_with_discount: number;
}

export interface RiskData {
  inn: string;
  name?: string;
  enough_data: boolean;
  as_customer: {
    contracts_total: number;
    contracts_sum_rub: number;
    notices_count: number;
    complaints_count: number;
    unilateral_refusals_count: number;
  };
  as_supplier: {
    contracts_total: number;
    contracts_sum_rub: number;
    unilateral_refusals_against: number;
    complaints_as_applicant: number;
    in_rnp: boolean;
    rnp_records: any[];
  };
  risk_flags: string[];
  risk_score: number;
}

export interface MarketOverview {
  contracts_count: number;
  total_sum_rub: number;
  avg_price_rub: number | null;
  unique_customers: number;
  unique_suppliers: number;
  discount_pct_median: number | null;
  discount_pct_p25: number | null;
  discount_pct_p75: number | null;
  discounts_sample: number;
  total_savings_rub: number;
  contracts_with_discount: number;
  discount_rate_pct: number | null;
  hhi: number | null;
}

export interface TopEntry {
  prefix?: string;
  inn?: string;
  name?: string;
  short_name?: string;
  contracts: number;
  total_sum: number;
  share_pct?: number;
}

export interface TopItemEntry {
  code: string;
  name: string | null;
  contracts: number;
  total_sum: number;
  share_pct: number;
}

export interface ContractDetail {
  reg_num: string;
  sign_date: string | null;
  contract_subject: string | null;
  customer_inn?: string | null;
  customer_name: string | null;
  customer_short_name: string | null;
  supplier_inn?: string | null;
  supplier_name: string | null;
  supplier_short_name: string | null;
  contract_price: number | null;
  start_price: number | null;
  discount_pct: number | null;
}

export interface ItemDetails {
  okpd2_code: string;
  okpd2_name: string | null;
  timeseries: { month: string; contracts: number; total_sum: number }[];
  discount_pct_median: number | null;
  discounts_sample: number;
  contracts: ContractDetail[];
  contracts_total: number;
}

export interface SupplierShare {
  inn: string;
  name: string | null;
  short_name: string;
  contracts: number;
  total_sum: number;
  share_pct: number;
}

export interface CustomerShare {
  inn: string;
  name: string | null;
  short_name: string;
  contracts: number;
  total_sum: number;
  share_pct: number;
}

export interface SupplierDetails {
  inn: string;
  name: string | null;
  short_name: string;
  supplier_type: string | null;
  // KPI за период
  contracts_count: number;
  total_sum_rub: number;
  avg_price_rub: number | null;
  unique_customers: number;
  // Риски (за всё время)
  risk_score: number;
  risk_flags: string[];
  in_rnp: boolean;
  rnp_records: any[];
  unilateral_refusals_against: number;
  complaints_as_applicant: number;
  all_time_contracts_count: number;
  // Графики и связки
  timeseries: { month: string; contracts: number; total_sum: number }[];
  top_customers: CustomerShare[];
  concentration_pct: number;
  // Контракты
  contracts: ContractDetail[];
  contracts_total: number;
}

export interface CustomerDetails {
  inn: string;
  name: string | null;
  short_name: string;
  region_code: string | null;
  // KPI за период
  contracts_count: number;
  total_sum_rub: number;
  avg_price_rub: number | null;
  unique_suppliers: number;
  // Риски (за всё время)
  risk_score: number;
  risk_flags: string[];
  complaints_count: number;
  unilateral_refusals_count: number;
  in_rnp_as_supplier: boolean;
  all_time_contracts_count: number;
  all_time_notices_count: number;
  // Графики и связки (за период)
  timeseries: { month: string; contracts: number; total_sum: number }[];
  top_suppliers: SupplierShare[];
  concentration_pct: number;
  // Контракты с пагинацией
  contracts: ContractDetail[];
  contracts_total: number;
}

export interface TimeSeriesEntry {
  month: string;
  contracts: number;
  total_sum: number;
}


async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json() as Promise<T>;
}

function q(params: Record<string, any>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  return entries.length ? '?' + entries.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&') : '';
}

export const api = {
  bench: (okpd2: string, region?: string, months = 12) =>
    fetchJson<BenchData>(`/api/bench${q({ okpd2, region, months })}`),

  risk: (inn: string) =>
    fetchJson<RiskData>(`/api/risk${q({ inn })}`),

  marketOverview: (params: { from_date: string; to_date: string; okpd2?: string; region?: string }) =>
    fetchJson<MarketOverview>(`/api/market/overview${q(params)}`),

  topSectors: (params: { from_date: string; to_date: string; region?: string; limit?: number }) =>
    fetchJson<TopEntry[]>(`/api/market/top-sectors${q(params)}`),

  topItemsInSector: (params: { from_date: string; to_date: string; okpd2: string; region?: string; limit?: number }) =>
    fetchJson<TopItemEntry[]>(`/api/market/top-items-in-sector${q(params)}`),

  itemDetails: (params: { from_date: string; to_date: string; okpd2_code: string; region?: string; contracts_limit?: number; contracts_offset?: number; sort_by?: 'date' | 'price'; sort_dir?: 'asc' | 'desc' }) =>
    fetchJson<ItemDetails>(`/api/market/item-details${q(params)}`),

  customerDetails: (params: { from_date: string; to_date: string; inn: string; contracts_limit?: number; contracts_offset?: number; sort_by?: 'date' | 'price'; sort_dir?: 'asc' | 'desc' }) =>
    fetchJson<CustomerDetails>(`/api/market/customer-details${q(params)}`),

  supplierDetails: (params: { from_date: string; to_date: string; inn: string; contracts_limit?: number; contracts_offset?: number; sort_by?: 'date' | 'price'; sort_dir?: 'asc' | 'desc' }) =>
    fetchJson<SupplierDetails>(`/api/market/supplier-details${q(params)}`),

  topCustomers: (params: { from_date: string; to_date: string; okpd2?: string; region?: string; limit?: number }) =>
    fetchJson<TopEntry[]>(`/api/market/top-customers${q(params)}`),

  topSuppliers: (params: { from_date: string; to_date: string; okpd2?: string; region?: string; limit?: number }) =>
    fetchJson<TopEntry[]>(`/api/market/top-suppliers${q(params)}`),

  timeseries: (params: { from_date: string; to_date: string; okpd2?: string; region?: string }) =>
    fetchJson<TimeSeriesEntry[]>(`/api/market/timeseries${q(params)}`),

  classifyOkpd2: async (title: string, description = '') => {
    const r = await fetch('/api/classify-okpd2', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });
    return r.json();
  },
};


// Справочники для фильтров
export const REGIONS = [
  { code: '', name: 'Вся РФ' },
  { code: '77', name: 'Москва' },
  { code: '78', name: 'Санкт-Петербург' },
  { code: '50', name: 'Московская область' },
  { code: '16', name: 'Татарстан' },
  { code: '66', name: 'Свердловская' },
  { code: '23', name: 'Краснодарский' },
  { code: '54', name: 'Новосибирская' },
  { code: '61', name: 'Ростовская' },
  { code: '52', name: 'Нижегородская' },
  { code: '74', name: 'Челябинская' },
];

export const OKPD2_TOP = [
  { code: '', name: 'Все отрасли' },
  { code: '21', name: '21 — Фармацевтика' },
  { code: '26', name: '26 — IT / электроника' },
  { code: '33', name: '33 — Ремонт и монтаж' },
  { code: '35', name: '35 — Электричество / тепло' },
  { code: '41', name: '41 — Здания и сооружения' },
  { code: '42', name: '42 — Гражданское строительство' },
  { code: '43', name: '43 — Спец. строительные работы' },
  { code: '46', name: '46 — Оптовая торговля' },
  { code: '47', name: '47 — Розничная торговля' },
  { code: '58', name: '58 — Издательство' },
  { code: '62', name: '62 — IT-услуги' },
  { code: '71', name: '71 — Архитектура / проектирование' },
  { code: '80', name: '80 — Охрана' },
  { code: '81', name: '81 — Хозяйственные услуги' },
  { code: '85', name: '85 — Образование' },
  { code: '86', name: '86 — Медицина' },
];
