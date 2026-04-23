import React, { forwardRef, useState, useEffect, useCallback } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import {
  Factory, X, ShieldAlert, ShieldCheck, FileWarning, Ban, Trophy,
  TrendingUp, AlertTriangle, Loader2, ChevronLeft, ChevronRight, ArrowUp, ArrowDown,
} from 'lucide-react';
import {
  SupplierDetails, ContractDetail, CustomerShare, api,
} from '../api';
import { CustomerCardSkeleton, SkeletonOverlayLoader } from './Skeletons';

const PAGE_SIZE = 20;
const CONCENTRATION_WARN_PCT = 50;
type SortBy = 'date' | 'price';
type SortDir = 'asc' | 'desc';
interface SortState { by: SortBy; dir: SortDir; }
const DEFAULT_SORT: SortState = { by: 'date', dir: 'desc' };

const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' : v >= 1_000_000_000
    ? `${(v / 1_000_000_000).toFixed(1)} млрд ₽`
    : v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)} млн ₽`
      : `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const fmtPct = (v: number | null | undefined) =>
  v == null ? '—' : `${v.toFixed(1)}%`;

const fmtDate = (s: string | null) => {
  if (!s) return '—';
  const [y, m, d] = s.split('-');
  return d ? `${d}.${m}.${y}` : s;
};

const ruPlural = (n: number, forms: [string, string, string]) => {
  const n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return forms[0];
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return forms[1];
  return forms[2];
};

const SUPPLIER_TYPE_LABELS: Record<string, string> = {
  legalEntityRF: 'Юр.лицо РФ',
  individualRF: 'Физлицо РФ',
  IP: 'ИП',
  foreignOrg: 'Иностранная организация',
  foreignIndividual: 'Иностранное физлицо',
};

interface Props {
  inn: string;
  fromDate: string;
  toDate: string;
  onClose: () => void;
  /** Открыть карточку заказчика — клик по заказчику в таблице контрактов
   *  или в топ-заказчиках. Прокидываем наружу, на уровне MarketPage. */
  onOpenCustomer?: (inn: string) => void;
}

export const SupplierCard = forwardRef<HTMLDivElement, Props>(({
  inn, fromDate, toDate, onClose, onOpenCustomer,
}, ref) => {
  const [data, setData] = useState<SupplierDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SortState>(DEFAULT_SORT);

  const fetchData = useCallback((p: number, s: SortState) => {
    setLoading(true);
    setError(false);
    api.supplierDetails({
      from_date: fromDate, to_date: toDate, inn,
      contracts_limit: PAGE_SIZE, contracts_offset: p * PAGE_SIZE,
      sort_by: s.by, sort_dir: s.dir,
    })
      .then(d => { setData(d); setPage(p); setSort(s); })
      .catch(e => { console.error('[supplier] details failed', e); setError(true); })
      .finally(() => setLoading(false));
  }, [inn, fromDate, toDate]);

  useEffect(() => {
    setData(null); setError(false);
    fetchData(0, DEFAULT_SORT);
  }, [inn, fromDate, toDate, fetchData]);

  if (!data) {
    return (
      <div ref={ref}>
        {error ? (
          <div className="p-5 bg-white dark:bg-slate-800 rounded-2xl border border-amber-200 dark:border-amber-800/40 shadow-md">
            <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
              <AlertTriangle className="w-4 h-4" />
              Не удалось загрузить профиль поставщика (ИНН {inn}). Попробуй закрыть и кликнуть снова.
            </div>
          </div>
        ) : (
          <SkeletonOverlayLoader loading text="Загружаю профиль поставщика…">
            <CustomerCardSkeleton />
          </SkeletonOverlayLoader>
        )}
      </div>
    );
  }

  return (
    <div ref={ref}
         className="relative p-5 bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-md
                    animate-in fade-in slide-in-from-bottom-2">
      <Header data={data} inn={inn} loading={loading} onClose={onClose} />
      <KpiRow data={data} />
      <RiskFlags data={data} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-4">
        <DynamicsBlock timeseries={data.timeseries} />
        <TopCustomersBlock
          customers={data.top_customers}
          concentration={data.concentration_pct}
          onOpenCustomer={onOpenCustomer}
        />
      </div>

      {data.contracts_total > 0 && (
        <ContractsTable
          rows={data.contracts}
          page={page}
          total={data.contracts_total}
          sort={sort}
          loading={loading}
          onPage={(p) => fetchData(p, sort)}
          onSort={(newSort) => fetchData(0, newSort)}
          onOpenCustomer={onOpenCustomer}
        />
      )}
    </div>
  );
});


// ============================================================================
// Подкомпоненты
// ============================================================================

const Header: React.FC<{
  data: SupplierDetails | null;
  inn: string;
  loading: boolean;
  onClose: () => void;
}> = ({ data, inn, loading, onClose }) => {
  const typeLabel = data?.supplier_type ? SUPPLIER_TYPE_LABELS[data.supplier_type] : null;
  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="w-12 h-12 rounded-xl bg-violet-100 dark:bg-violet-900/40 flex items-center justify-center shrink-0">
        <Factory className="w-6 h-6 text-violet-600 dark:text-violet-400" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-lg font-bold text-slate-800 dark:text-slate-100 leading-tight flex items-center gap-2 flex-wrap">
          {data?.short_name || data?.name || (loading ? 'Загружаю…' : inn)}
          {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-violet-500" />}
        </div>
        {data?.name && data.name !== data.short_name && (
          <div className="text-xs text-slate-500 mt-0.5 leading-snug">{data.name}</div>
        )}
        <div className="text-xs text-slate-500 mt-1 flex items-center gap-2 flex-wrap">
          <span className="font-mono">ИНН {inn}</span>
          {typeLabel && (
            <>
              <span className="text-slate-300 dark:text-slate-600">·</span>
              <span>{typeLabel}</span>
            </>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="w-8 h-8 inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-200 transition-colors shrink-0"
        title="Закрыть (Esc)">
        <X className="w-5 h-5" />
      </button>
    </div>
  );
};


const KpiRow: React.FC<{ data: SupplierDetails }> = ({ data }) => {
  const riskTone = data.risk_score >= 60
    ? { bg: 'bg-rose-50 dark:bg-rose-900/30', text: 'text-rose-700 dark:text-rose-300', label: 'высокий' }
    : data.risk_score >= 25
      ? { bg: 'bg-amber-50 dark:bg-amber-900/30', text: 'text-amber-700 dark:text-amber-300', label: 'средний' }
      : { bg: 'bg-emerald-50 dark:bg-emerald-900/30', text: 'text-emerald-700 dark:text-emerald-300', label: 'низкий' };
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
      <KpiTile label="Контрактов" value={data.contracts_count.toLocaleString('ru-RU')} sub="за период" />
      <KpiTile label="Объём" value={fmtMln(data.total_sum_rub)} sub="за период" />
      <KpiTile label="Средний контракт" value={fmtMln(data.avg_price_rub)} sub="за период" />
      <KpiTile label="Заказчиков" value={data.unique_customers.toLocaleString('ru-RU')} sub="за период" />
      <div className={`p-3 rounded-lg ${riskTone.bg}`}>
        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-0.5">Риск-скор</div>
        <div className={`text-lg font-bold ${riskTone.text}`}>{data.risk_score}/100</div>
        <div className="text-[11px] text-slate-500 mt-0.5">{riskTone.label}</div>
      </div>
    </div>
  );
};


const KpiTile: React.FC<{ label: string; value: string; sub: string }> = ({ label, value, sub }) => (
  <div className="p-3 bg-slate-50 dark:bg-slate-900/40 rounded-lg">
    <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-0.5">{label}</div>
    <div className="text-lg font-bold text-slate-800 dark:text-slate-100">{value}</div>
    <div className="text-[11px] text-slate-400 mt-0.5">{sub}</div>
  </div>
);


const RiskFlags: React.FC<{ data: SupplierDetails }> = ({ data }) => {
  const inRnp = data.in_rnp;
  const refusals = data.unilateral_refusals_against;
  const complaintsApp = data.complaints_as_applicant;
  return (
    <div className="flex items-center gap-2 mb-2 flex-wrap text-xs">
      <span className="text-slate-500">За всё время:</span>
      <RiskBadge
        good={!inRnp}
        icon={inRnp ? <Ban className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
        text={inRnp ? `в РНП (${data.rnp_records.length} ${ruPlural(data.rnp_records.length, ['запись', 'записи', 'записей'])})` : 'не в РНП'}
      />
      <RiskBadge
        good={refusals === 0}
        icon={refusals > 0 ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
        text={refusals > 0
          ? `${refusals} ${ruPlural(refusals, ['расторжение', 'расторжения', 'расторжений'])} по инициативе заказчика`
          : 'нет расторжений'}
      />
      {complaintsApp > 0 && (
        <RiskBadge
          good={false}
          icon={<FileWarning className="w-3 h-3" />}
          text={`${complaintsApp} ${ruPlural(complaintsApp, ['жалоба', 'жалобы', 'жалоб'])} как заявитель`}
        />
      )}
      {data.all_time_contracts_count > data.contracts_count && (
        <span className="text-slate-400 ml-1">
          · всего {data.all_time_contracts_count.toLocaleString('ru-RU')} {ruPlural(data.all_time_contracts_count, ['контракт', 'контракта', 'контрактов'])} в БД
        </span>
      )}
    </div>
  );
};


const RiskBadge: React.FC<{ good: boolean; icon: React.ReactNode; text: string }> = ({ good, icon, text }) => (
  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ring-1 ${
    good
      ? 'bg-emerald-50 dark:bg-emerald-900/30 ring-emerald-200 dark:ring-emerald-800/40 text-emerald-700 dark:text-emerald-300'
      : 'bg-amber-50 dark:bg-amber-900/30 ring-amber-200 dark:ring-amber-800/40 text-amber-700 dark:text-amber-300'
  }`}>
    {icon} {text}
  </span>
);


const DynamicsBlock: React.FC<{ timeseries: SupplierDetails['timeseries'] }> = ({ timeseries }) => (
  <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
    <div className="text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2 flex items-center gap-1.5">
      <TrendingUp className="w-3.5 h-3.5 text-violet-500" />
      Динамика контрактов по месяцам
    </div>
    {timeseries.length > 0 ? (
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={timeseries} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <XAxis dataKey="month" fontSize={10} />
          <YAxis fontSize={10} />
          <Tooltip
            contentStyle={{ fontSize: 11, padding: '4px 8px' }}
            formatter={(v: any) => [`${v} контр.`, '']}
          />
          <Line type="monotone" dataKey="contracts" stroke="#8b5cf6" strokeWidth={2}
                dot={{ r: 3, fill: '#8b5cf6' }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    ) : (
      <div className="h-[160px] flex items-center justify-center text-xs text-slate-500">
        Нет данных за период
      </div>
    )}
  </div>
);


const TopCustomersBlock: React.FC<{
  customers: CustomerShare[];
  concentration: number;
  onOpenCustomer?: (inn: string) => void;
}> = ({ customers, concentration, onOpenCustomer }) => (
  <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
    <div className="text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2 flex items-center gap-1.5">
      <Trophy className="w-3.5 h-3.5 text-violet-500" />
      Топ заказчиков
    </div>
    {concentration > CONCENTRATION_WARN_PCT && customers.length > 0 && (
      <div className="mb-2 px-2.5 py-1.5 bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800/40 rounded-lg flex items-start gap-1.5 text-[11px] text-amber-800 dark:text-amber-300">
        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-px" />
        <div>
          <span className="font-semibold">{concentration.toFixed(1)}% объёма</span> приходит от одного заказчика —
          поставщик зависим от одного клиента или это аффилированная связка.
        </div>
      </div>
    )}
    {customers.length === 0 ? (
      <div className="text-xs text-slate-500 py-4 text-center">Нет данных за период</div>
    ) : (
      <div className="space-y-1.5">
        {customers.map((c, i) => (
          <CustomerRow key={c.inn} customer={c} rank={i + 1} onOpenCustomer={onOpenCustomer} />
        ))}
      </div>
    )}
  </div>
);


const CustomerRow: React.FC<{
  customer: CustomerShare;
  rank: number;
  onOpenCustomer?: (inn: string) => void;
}> = ({ customer, rank, onOpenCustomer }) => {
  const isClickable = !!onOpenCustomer && !!customer.inn;
  const medalCls =
    rank === 1 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' :
    rank === 2 ? 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200' :
    rank === 3 ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300' :
                 'bg-slate-50 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
  const handleClick = () => isClickable && onOpenCustomer!(customer.inn);
  return (
    <div className={`flex items-center gap-2 text-xs ${isClickable ? 'cursor-pointer hover:bg-indigo-50/40 dark:hover:bg-indigo-900/15 -mx-1 px-1 py-0.5 rounded' : ''}`}
         onClick={handleClick}
         title={customer.name || ''}>
      <div className={`shrink-0 w-6 h-6 rounded flex items-center justify-center text-[11px] font-bold ${medalCls}`}>
        {rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className={`truncate ${isClickable ? 'text-indigo-700 dark:text-indigo-300 hover:underline' : 'text-slate-700 dark:text-slate-200'}`}>
          {customer.short_name || customer.name || customer.inn}
        </div>
        <div className="flex items-center gap-1.5 mt-0.5">
          <div className="flex-1 h-1 bg-slate-100 dark:bg-slate-700/60 rounded-full overflow-hidden">
            <div className="h-full bg-violet-500 dark:bg-violet-400 rounded-full"
                 style={{ width: `${Math.min(100, Math.max(2, customer.share_pct))}%` }} />
          </div>
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="font-semibold text-violet-700 dark:text-violet-300 tabular-nums">
          {fmtPct(customer.share_pct)}
        </div>
        <div className="text-[10px] text-slate-400">
          {customer.contracts} {ruPlural(customer.contracts, ['контр', 'контр', 'контр'])}
        </div>
      </div>
    </div>
  );
};


const ContractsTable: React.FC<{
  rows: ContractDetail[];
  page: number;
  total: number;
  sort: SortState;
  loading: boolean;
  onPage: (page: number) => void;
  onSort: (sort: SortState) => void;
  onOpenCustomer?: (inn: string) => void;
}> = ({ rows, page, total, sort, loading, onPage, onSort, onOpenCustomer }) => {
  const showNmck = rows.some(r => r.start_price != null && r.start_price > 0);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const fromIdx = page * PAGE_SIZE + 1;
  const toIdx = Math.min((page + 1) * PAGE_SIZE, total);
  const toggleSort = (by: SortBy) => {
    if (sort.by === by) onSort({ by, dir: sort.dir === 'desc' ? 'asc' : 'desc' });
    else onSort({ by, dir: 'desc' });
  };
  return (
    <div className="mt-4 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-800">
      <div className="px-3 py-2 bg-slate-50 dark:bg-slate-900/50 text-xs font-semibold text-slate-600 dark:text-slate-300 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Factory className="w-3.5 h-3.5" /> Контракты поставщика
          <span className="font-normal text-slate-400">
            · {fromIdx}–{toIdx} из {total.toLocaleString('ru-RU')}
          </span>
        </div>
        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-violet-500" />}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-slate-500 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <SortableTh label="Дата" align="left" sortKey="date" sort={sort} onClick={() => toggleSort('date')} />
              <th className="text-left px-3 py-1.5 font-medium">Контракт</th>
              <th className="text-left px-3 py-1.5 font-medium">Заказчик</th>
              {showNmck && <th className="text-right px-3 py-1.5 font-medium">НМЦК</th>}
              <SortableTh label="Цена" align="right" sortKey="price" sort={sort} onClick={() => toggleSort('price')} />
              {showNmck && <th className="text-right px-3 py-1.5 font-medium">Скидка</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const goodDiscount = r.discount_pct != null && r.discount_pct > 5;
              return (
                <tr key={r.reg_num}
                    className={`border-b border-slate-100 dark:border-slate-800 last:border-0
                                ${goodDiscount ? 'bg-emerald-50/30 dark:bg-emerald-900/10' : ''}`}>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-300 whitespace-nowrap align-top">
                    {fmtDate(r.sign_date)}
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-200 align-top max-w-md">
                    <div className="text-slate-800 dark:text-slate-100 leading-snug line-clamp-2"
                         title={r.contract_subject || ''}>
                      {r.contract_subject || <span className="text-slate-400">—</span>}
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">№ {r.reg_num}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-200 max-w-xs align-top">
                    {onOpenCustomer && r.customer_inn ? (
                      <button
                        type="button"
                        onClick={() => onOpenCustomer(r.customer_inn!)}
                        className="text-left truncate w-full text-xs text-indigo-700 dark:text-indigo-300 hover:underline"
                        title={`${r.customer_name || ''} — открыть карточку заказчика`}>
                        {r.customer_short_name || r.customer_name || '—'}
                      </button>
                    ) : (
                      <div className="truncate" title={r.customer_name || ''}>
                        {r.customer_short_name || r.customer_name || '—'}
                      </div>
                    )}
                  </td>
                  {showNmck && (
                    <td className="px-3 py-2 text-right text-slate-500 whitespace-nowrap font-mono align-top"
                        title="Начальная (максимальная) цена контракта из извещения">
                      {r.start_price != null ? fmtMln(r.start_price) : <span className="text-slate-300">—</span>}
                    </td>
                  )}
                  <td className="px-3 py-2 text-right text-slate-800 dark:text-slate-100 font-semibold whitespace-nowrap font-mono align-top">
                    {fmtMln(r.contract_price)}
                  </td>
                  {showNmck && (
                    <td className={`px-3 py-2 text-right whitespace-nowrap font-semibold align-top ${
                      goodDiscount ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-400'
                    }`}>
                      {r.discount_pct != null ? fmtPct(r.discount_pct) : <span className="text-slate-300">—</span>}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="px-3 py-2 bg-slate-50/60 dark:bg-slate-900/40 border-t border-slate-200 dark:border-slate-700 flex items-center justify-end gap-1 shrink-0">
        <button
          type="button"
          disabled={page === 0 || loading}
          onClick={() => onPage(page - 1)}
          className="w-7 h-7 inline-flex items-center justify-center rounded border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 enabled:hover:bg-slate-100 dark:enabled:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div className="text-xs text-slate-600 dark:text-slate-300 px-2 tabular-nums">
          {page + 1} / {totalPages}
        </div>
        <button
          type="button"
          disabled={page >= totalPages - 1 || loading}
          onClick={() => onPage(page + 1)}
          className="w-7 h-7 inline-flex items-center justify-center rounded border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 enabled:hover:bg-slate-100 dark:enabled:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};


const SortableTh: React.FC<{
  label: string; align: 'left' | 'right'; sortKey: SortBy;
  sort: SortState; onClick: () => void;
}> = ({ label, align, sortKey, sort, onClick }) => {
  const active = sort.by === sortKey;
  const Icon = active && sort.dir === 'asc' ? ArrowUp : ArrowDown;
  return (
    <th className={`px-3 py-1.5 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button type="button" onClick={onClick}
              className={`inline-flex items-center gap-1 select-none transition-colors ${
                active
                  ? 'text-violet-600 dark:text-violet-400'
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
              }`}
              title={`Сортировать по «${label.toLowerCase()}»`}>
        {label}
        <Icon className={`w-3 h-3 transition-opacity ${active ? 'opacity-100' : 'opacity-30'}`} />
      </button>
    </th>
  );
};
