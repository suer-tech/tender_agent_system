export type Category = '44-ФЗ' | '223-ФЗ' | 'Коммерческий';

export interface TenderDetails {
  requirements: string;
  mandatory: string;
  qualification: string;
  technologies: string;
  risks: string;
  aiComment: string;
}

export interface Okpd2Guess {
  code: string;
  name?: string;
  confidence: number;
  source: 'exact' | 'classified';
}

export interface PriceContext {
  okpd2_prefix: string;
  region_code: string;
  sample_size: number;
  contracts_with_discount: number;
  discount_pct_median: number | null;
  discount_pct_p25: number | null;
  discount_pct_p75: number | null;
  nmck_median: number | null;
  final_price_median: number | null;
  summary: string;
}

export interface RnpRecord {
  reg_number: string;
  publish_date: string;
  approve_org_name: string;
  create_reason: string;
  auto_exclude_date: string;
}

export interface CustomerRisk {
  inn: string;
  name?: string;
  contracts_as_customer: number;
  contracts_sum_as_customer: number;
  notices_count: number;
  complaints_count: number;
  unilateral_refusals_count: number;
  in_rnp: boolean;
  rnp_records: RnpRecord[];
  risk_flags: string[];
  risk_score: number;
  summary?: string;
}

export interface Tender {
  id: string;
  title: string;
  category: Category;
  amount: number;
  startDate: string;
  endDate: string;
  score: number;
  description: string;
  details: TenderDetails;
  url?: string;
  docStatus?: string;
  docCount?: number;
  // аналитические блоки — null когда «данных мало»
  okpd2Guess?: Okpd2Guess | null;
  priceContext?: PriceContext | null;
  customerRisk?: CustomerRisk | null;
}

export interface Message {
  id: string;
  role: 'user' | 'agent' | 'system';
  content: string;
  timestamp: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  tenders: Tender[];
  createdAt: string;
}
