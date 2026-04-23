import React, { useState, useMemo, useCallback } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import {
  Package, Loader2, AlertTriangle, Trophy, ChevronRight,
  TrendingDown, FileText, Building2, ChevronLeft, ArrowUp, ArrowDown,
} from 'lucide-react';
import { TopItemEntry, ItemDetails, ContractDetail, api } from '../api';

const PAGE_SIZE = 20;
type SortBy = 'date' | 'price';
type SortDir = 'asc' | 'desc';
interface SortState { by: SortBy; dir: SortDir; }
const DEFAULT_SORT: SortState = { by: 'date', dir: 'desc' };

type Metric = 'sum' | 'contracts';

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

interface Props {
  items: TopItemEntry[];
  status: 'idle' | 'loading' | 'ok' | 'error';
  sectorLabel: string;
  /** Параметры периода — нужны для drill-down запроса деталей. */
  fromDate: string;
  toDate: string;
  region: string;
}

/** Топ позиций (товаров/услуг) внутри выбранной отрасли — в виде лидерборда.
 *  Каждая строка кликабельна → раскрывается панель с деталями (динамика,
 *  скидки, последние контракты) для этого ОКПД2-кода.
 */
export const SectorItemsCard: React.FC<Props> = ({
  items, status, sectorLabel, fromDate, toDate, region,
}) => {
  const [metric, setMetric] = useState<Metric>('sum');
  // Только одна позиция раскрыта одновременно — клик по другой закрывает текущую.
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  // Кэш деталей по коду + текущая страница пагинации + текущая сортировка.
  // На повторном раскрытии не дёргаем API; на смене страницы/сортировки
  // дёргаем заново — endpoint всё равно возвращает шапку и timeseries.
  const [detailsCache, setDetailsCache] = useState<Record<string, { details: ItemDetails; page: number; sort: SortState }>>({});
  const [detailsLoading, setDetailsLoading] = useState<Record<string, boolean>>({});
  const [detailsError, setDetailsError] = useState<Record<string, boolean>>({});

  const ranked = useMemo(() => {
    const totalContracts = items.reduce((s, e) => s + e.contracts, 0);
    const totalSum = items.reduce((s, e) => s + e.total_sum, 0);
    const sorted = [...items].sort((a, b) =>
      metric === 'sum'
        ? b.total_sum - a.total_sum
        : b.contracts - a.contracts
    );
    return sorted.map((e, i) => ({
      ...e,
      _rank: i + 1,
      _share: metric === 'sum'
        ? (totalSum ? (e.total_sum / totalSum) * 100 : 0)
        : (totalContracts ? (e.contracts / totalContracts) * 100 : 0),
    }));
  }, [items, metric]);

  const fetchPage = useCallback((code: string, page: number, sort: SortState) => {
    setDetailsLoading(s => ({ ...s, [code]: true }));
    setDetailsError(s => ({ ...s, [code]: false }));
    api.itemDetails({
      from_date: fromDate, to_date: toDate, okpd2_code: code,
      region: region || undefined,
      contracts_limit: PAGE_SIZE,
      contracts_offset: page * PAGE_SIZE,
      sort_by: sort.by, sort_dir: sort.dir,
    })
      .then(d => setDetailsCache(s => ({ ...s, [code]: { details: d, page, sort } })))
      .catch(e => {
        console.error('[items] details failed', e);
        setDetailsError(s => ({ ...s, [code]: true }));
      })
      .finally(() => setDetailsLoading(s => ({ ...s, [code]: false })));
  }, [fromDate, toDate, region]);

  const handleToggle = useCallback((code: string) => {
    setExpandedCode(prev => (prev === code ? null : code));
    if (detailsCache[code] || detailsLoading[code]) return;
    fetchPage(code, 0, DEFAULT_SORT);
  }, [detailsCache, detailsLoading, fetchPage]);

  let body: React.ReactNode;
  if (status === 'loading') {
    body = (
      <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Загружаю позиции…
      </div>
    );
  } else if (status === 'error') {
    body = (
      <div className="flex flex-col items-center justify-center gap-2 py-8 text-sm text-amber-700 dark:text-amber-400">
        <AlertTriangle className="w-5 h-5" />
        <div className="text-center">
          <div className="font-medium">Не удалось загрузить позиции</div>
          <div className="text-xs text-slate-500 mt-1">
            Возможно, бэкенд не перезапущен после обновления
            (endpoint /api/market/top-items-in-sector). Проверь Network в DevTools.
          </div>
        </div>
      </div>
    );
  } else if (ranked.length === 0) {
    body = (
      <div className="text-sm text-slate-500 py-8 text-center">
        В этой отрасли нет позиций за выбранный период
      </div>
    );
  } else {
    body = (
      <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
        {ranked.map(it => {
          const cached = detailsCache[it.code];
          const sort = cached?.sort ?? DEFAULT_SORT;
          return (
            <ItemRow
              key={it.code}
              item={it}
              metric={metric}
              expanded={expandedCode === it.code}
              details={cached?.details}
              page={cached?.page ?? 0}
              sort={sort}
              loadingDetails={!!detailsLoading[it.code]}
              errorDetails={!!detailsError[it.code]}
              onToggle={() => handleToggle(it.code)}
              onPage={(page) => fetchPage(it.code, page, sort)}
              onSort={(newSort) => fetchPage(it.code, 0, newSort)}
            />
          );
        })}
      </div>
    );
  }

  return (
    <CardShell sectorLabel={sectorLabel} metric={metric} onMetric={setMetric}>
      {body}
    </CardShell>
  );
};


const CardShell: React.FC<{
  sectorLabel: string; metric: Metric; onMetric: (m: Metric) => void;
  children: React.ReactNode;
}> = ({ sectorLabel, metric, onMetric, children }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <Header sectorLabel={sectorLabel} metric={metric} onMetric={onMetric} />
    {children}
  </div>
);


const Header: React.FC<{ sectorLabel: string; metric: Metric; onMetric: (m: Metric) => void }> = ({
  sectorLabel, metric, onMetric,
}) => (
  <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
    <div className="flex items-center gap-2 min-w-0">
      <Package className="w-4 h-4 text-slate-400 shrink-0" />
      <div className="text-sm font-semibold text-slate-700 dark:text-slate-200 truncate">
        Топ позиций в отрасли «{sectorLabel}»
      </div>
    </div>
    <MetricToggle metric={metric} onChange={onMetric} />
  </div>
);


const MetricToggle: React.FC<{ metric: Metric; onChange: (m: Metric) => void }> = ({ metric, onChange }) => (
  <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden text-xs">
    <button
      onClick={() => onChange('sum')}
      className={`px-2.5 py-1 transition-colors ${
        metric === 'sum'
          ? 'bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
          : 'bg-white dark:bg-slate-800 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-700/50'
      }`}>
      По объёму ₽
    </button>
    <button
      onClick={() => onChange('contracts')}
      className={`px-2.5 py-1 border-l border-slate-200 dark:border-slate-600 transition-colors ${
        metric === 'contracts'
          ? 'bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
          : 'bg-white dark:bg-slate-800 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-700/50'
      }`}>
      По числу контрактов
    </button>
  </div>
);


const ItemRow: React.FC<{
  item: TopItemEntry & { _rank: number; _share: number };
  metric: Metric;
  expanded: boolean;
  details: ItemDetails | undefined;
  page: number;
  sort: SortState;
  loadingDetails: boolean;
  errorDetails: boolean;
  onToggle: () => void;
  onPage: (page: number) => void;
  onSort: (sort: SortState) => void;
}> = ({ item, metric, expanded, details, page, sort, loadingDetails, errorDetails, onToggle, onPage, onSort }) => {
  const isMedal = item._rank <= 3;
  const medalCls =
    item._rank === 1 ? 'bg-amber-100 text-amber-700 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-800/40' :
    item._rank === 2 ? 'bg-slate-200 text-slate-700 ring-slate-300 dark:bg-slate-700 dark:text-slate-200 dark:ring-slate-600' :
    item._rank === 3 ? 'bg-orange-100 text-orange-700 ring-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:ring-orange-800/40' :
                       'bg-slate-50 text-slate-500 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700';

  return (
    <div className={expanded ? 'bg-indigo-50/30 dark:bg-indigo-900/10 -mx-2 px-2 rounded-lg transition-colors' : ''}>
      <button
        onClick={onToggle}
        className={`w-full text-left py-3 first:pt-1 last:pb-1 flex gap-3 transition-colors -mx-2 px-2 rounded-lg
                    ${expanded
                      ? 'hover:bg-indigo-50/40 dark:hover:bg-indigo-900/20'
                      : 'hover:bg-slate-50/60 dark:hover:bg-slate-700/20'}`}>
        {/* Rank */}
        <div className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center font-bold text-base ring-1 ${medalCls}`}
             title={`${item._rank}-е место`}>
          {isMedal ? <span className="flex items-center gap-0.5"><Trophy className="w-3 h-3" />{item._rank}</span> : item._rank}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 shrink-0">
              {item.code}
            </span>
            <div className="text-sm text-slate-800 dark:text-slate-100 leading-snug">
              {item.name || '—'}
            </div>
          </div>

          <div className="flex items-center gap-2 mb-1">
            <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-700/60 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 dark:bg-indigo-400 rounded-full transition-all"
                style={{ width: `${Math.min(100, Math.max(2, item._share))}%` }}
              />
            </div>
            <div className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 w-12 text-right shrink-0">
              {fmtPct(item._share)}
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <span className={metric === 'sum' ? 'text-slate-800 dark:text-slate-100 font-semibold' : 'text-slate-500'}>
              {fmtMln(item.total_sum)}
            </span>
            <span className="text-slate-300 dark:text-slate-600">·</span>
            <span className={metric === 'contracts' ? 'text-slate-800 dark:text-slate-100 font-semibold' : 'text-slate-500'}>
              {item.contracts.toLocaleString('ru-RU')} {ruPlural(item.contracts, ['контракт', 'контракта', 'контрактов'])}
            </span>
          </div>
        </div>

        <ChevronRight
          className={`w-4 h-4 mt-1 shrink-0 text-slate-400 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
        />
      </button>

      {/* Раскрывающийся блок: CSS-grid trick для плавной height-анимации.
          Внутренний overflow-hidden обрезает контент во время анимации. */}
      <div className="grid transition-[grid-template-rows] duration-300 ease-out"
           style={{ gridTemplateRows: expanded ? '1fr' : '0fr' }}>
        <div className="overflow-hidden">
          {expanded && (
            <ExpandedDetails
              details={details}
              page={page}
              sort={sort}
              loading={loadingDetails}
              error={errorDetails}
              fallbackName={item.name}
              onPage={onPage}
              onSort={onSort}
            />
          )}
        </div>
      </div>
    </div>
  );
};


// ============================================================================
// Раскрытая панель деталей
// ============================================================================

const ExpandedDetails: React.FC<{
  details: ItemDetails | undefined;
  page: number;
  sort: SortState;
  loading: boolean;
  error: boolean;
  fallbackName: string | null;
  onPage: (page: number) => void;
  onSort: (sort: SortState) => void;
}> = ({ details, page, sort, loading, error, fallbackName, onPage, onSort }) => {
  if (loading && !details) {
    return (
      <div className="px-4 pb-4 pt-1 flex items-center justify-center gap-2 text-sm text-slate-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Загружаю детали по позиции…
      </div>
    );
  }
  if (error && !details) {
    return (
      <div className="px-4 pb-4 pt-1 flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
        <AlertTriangle className="w-4 h-4" />
        Не удалось загрузить детали — попробуй переоткрыть строку.
      </div>
    );
  }
  if (!details) return null;

  const hasTs = details.timeseries.length > 0;

  return (
    <div className="px-4 pb-4 pt-2 mt-1 border-t border-indigo-200/70 dark:border-indigo-800/30">
      {/* Шапка позиции */}
      <div className="mb-3 text-xs text-slate-500">
        Полное название: <span className="text-slate-700 dark:text-slate-200">
          {details.okpd2_name || fallbackName || '—'}
        </span>
      </div>

      {/* Верхний ряд: график + три плитки метрик */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-4">
        <div className="lg:col-span-2 p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 mb-2">
            <TrendingDown className="w-3.5 h-3.5 text-indigo-500" />
            Динамика контрактов по месяцам
          </div>
          {hasTs ? (
            <ResponsiveContainer width="100%" height={140}>
              <LineChart data={details.timeseries} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis dataKey="month" fontSize={10} />
                <YAxis fontSize={10} />
                <Tooltip
                  contentStyle={{ fontSize: 11, padding: '4px 8px' }}
                  formatter={(v: any) => [`${v} контр.`, '']}
                  labelFormatter={(l) => l}
                />
                <Line
                  type="monotone"
                  dataKey="contracts"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#6366f1' }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[140px] flex items-center justify-center text-xs text-slate-500">
              Нет данных
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-3">
          <MetricTile
            icon={<TrendingDown className="w-4 h-4 text-emerald-500" />}
            label="Медиана скидки"
            value={fmtPct(details.discount_pct_median)}
            sub={`по ${details.discounts_sample.toLocaleString('ru-RU')} ${ruPlural(details.discounts_sample, ['контракту', 'контрактам', 'контрактам'])} с НМЦК`}
            accent="emerald"
          />
          <MetricTile
            icon={<FileText className="w-4 h-4 text-indigo-500" />}
            label="Всего контрактов"
            value={details.contracts_total.toLocaleString('ru-RU')}
            sub="за выбранный период"
            accent="indigo"
          />
        </div>
      </div>

      {/* Таблица контрактов с пагинацией и сортировкой */}
      {details.contracts_total > 0 ? (
        <ContractsTable
          rows={details.contracts}
          page={page}
          total={details.contracts_total}
          sort={sort}
          loading={loading}
          onPage={onPage}
          onSort={onSort}
        />
      ) : (
        <div className="text-xs text-slate-500 text-center py-4">
          Нет данных по контрактам
        </div>
      )}
    </div>
  );
};


const MetricTile: React.FC<{
  icon: React.ReactNode; label: string; value: string; sub?: string;
  accent: 'emerald' | 'indigo';
}> = ({ icon, label, value, sub, accent }) => {
  const accentText = accent === 'emerald' ? 'text-emerald-700 dark:text-emerald-300' : 'text-indigo-700 dark:text-indigo-300';
  return (
    <div className="p-3 bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500 mb-1">
        {icon} {label}
      </div>
      <div className={`text-xl font-bold leading-tight ${accentText}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
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
}> = ({ rows, page, total, sort, loading, onPage, onSort }) => {
  // Клик по сортируемому заголовку: тот же столбец → переключаем направление,
  // другой столбец → переключаемся на него с дефолтным dir (desc).
  const toggleSort = (by: SortBy) => {
    if (sort.by === by) {
      onSort({ by, dir: sort.dir === 'desc' ? 'asc' : 'desc' });
    } else {
      onSort({ by, dir: 'desc' });
    }
  };
  // Скрываем колонки НМЦК и Скидка целиком, если на этой странице ни у одной
  // строки нет привязки к notice (типично для фармы / закупок у единственного
  // поставщика — там НМЦК структурно отсутствует).
  const showNmck = rows.some(r => r.start_price != null && r.start_price > 0);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const fromIdx = page * PAGE_SIZE + 1;
  const toIdx = Math.min((page + 1) * PAGE_SIZE, total);

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-800">
      <div className="px-3 py-2 bg-slate-50 dark:bg-slate-900/50 text-xs font-semibold text-slate-600 dark:text-slate-300 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Building2 className="w-3.5 h-3.5" /> Контракты
          <span className="font-normal text-slate-400">
            · {fromIdx}–{toIdx} из {total.toLocaleString('ru-RU')}
          </span>
        </div>
        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500" />}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-slate-500 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <SortableTh label="Дата" align="left" sortKey="date" sort={sort} onClick={() => toggleSort('date')} />
              <th className="text-left px-3 py-1.5 font-medium">Контракт</th>
              <th className="text-left px-3 py-1.5 font-medium">Заказчик</th>
              <th className="text-left px-3 py-1.5 font-medium">Поставщик</th>
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
                    <div className="truncate" title={r.customer_name || ''}>
                      {r.customer_short_name || r.customer_name || '—'}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-200 max-w-xs align-top">
                    <div className="truncate" title={r.supplier_name || ''}>
                      {r.supplier_short_name || r.supplier_name || '—'}
                    </div>
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
                      goodDiscount
                        ? 'text-emerald-700 dark:text-emerald-400'
                        : 'text-slate-400'
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

      <Paginator
        page={page}
        totalPages={totalPages}
        loading={loading}
        onPage={onPage}
        showNmckHint={!showNmck}
      />
    </div>
  );
};


const SortableTh: React.FC<{
  label: string;
  align: 'left' | 'right';
  sortKey: SortBy;
  sort: SortState;
  onClick: () => void;
}> = ({ label, align, sortKey, sort, onClick }) => {
  const active = sort.by === sortKey;
  const Icon = active && sort.dir === 'asc' ? ArrowUp : ArrowDown;
  return (
    <th className={`px-3 py-1.5 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 select-none transition-colors
                    ${active
                      ? 'text-indigo-600 dark:text-indigo-400'
                      : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
        title={`Сортировать по «${label.toLowerCase()}»`}>
        {label}
        <Icon className={`w-3 h-3 transition-opacity ${active ? 'opacity-100' : 'opacity-30'}`} />
      </button>
    </th>
  );
};


const Paginator: React.FC<{
  page: number; totalPages: number; loading: boolean;
  onPage: (page: number) => void;
  showNmckHint?: boolean;
}> = ({ page, totalPages, loading, onPage, showNmckHint }) => (
  <div className="px-3 py-2 bg-slate-50/60 dark:bg-slate-900/40 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between gap-3">
    <div className="text-[10px] text-slate-500">
      {showNmckHint
        ? 'У этих контрактов нет привязки к извещению — НМЦК и скидка недоступны (типично для закупок у единственного поставщика).'
        : null}
    </div>
    <div className="flex items-center gap-1 shrink-0">
      <button
        type="button"
        disabled={page === 0 || loading}
        onClick={() => onPage(page - 1)}
        className="w-7 h-7 inline-flex items-center justify-center rounded border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 enabled:hover:bg-slate-100 dark:enabled:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        aria-label="Предыдущая страница">
        <ChevronLeft className="w-4 h-4" />
      </button>
      <div className="text-xs text-slate-600 dark:text-slate-300 px-2 tabular-nums">
        {page + 1} / {totalPages}
      </div>
      <button
        type="button"
        disabled={page >= totalPages - 1 || loading}
        onClick={() => onPage(page + 1)}
        className="w-7 h-7 inline-flex items-center justify-center rounded border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 enabled:hover:bg-slate-100 dark:enabled:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        aria-label="Следующая страница">
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  </div>
);
