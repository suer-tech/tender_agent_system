import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Link } from 'react-router';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend,
} from 'recharts';
import {
  api, REGIONS, OKPD2_TOP,
  MarketOverview, TopEntry, TopItemEntry, TimeSeriesEntry,
} from '../api';
import { ArrowLeft, TrendingDown, Building2, Factory, BarChart3, Search, PiggyBank } from 'lucide-react';
import { useAppState } from '../store';
import { SectorsCard } from '../components/SectorsCard';
import { SectorItemsCard } from '../components/SectorItemsCard';
import {
  TopProgressBar, Refreshing, AnalyticsLoader, SkeletonOverlayLoader,
  StatTilesSkeleton, LineChartSkeleton, DiscountsCardSkeleton,
  SectorsCardSkeleton, SectorItemsCardSkeleton, TopTableSkeleton,
} from '../components/Skeletons';

const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' : v >= 1_000_000_000
    ? `${(v / 1_000_000_000).toFixed(1)} млрд ₽`
    : v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)} млн ₽`
      : `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const fmtPct = (v: number | null | undefined) => v == null ? '—' : `${v.toFixed(1)}%`;

// По дефолту — последние 12 месяцев (скользящее окно от сегодня).
// Считаем один раз при монтировании страницы; ISO YYYY-MM-DD без TZ-сдвига.
const isoDate = (d: Date) => d.toISOString().slice(0, 10);
const today = new Date();
const yearAgo = new Date(today);
yearAgo.setFullYear(today.getFullYear() - 1);
const DEFAULT_FROM = isoDate(yearAgo);
const DEFAULT_TO = isoDate(today);

// Кастомный select: отключаем нативную стрелку (appearance-none) и рисуем свою справа
// через background-image (inline style), чтобы отступ был предсказуемый.
const selectCls = "w-full pl-3 pr-9 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm appearance-none";
const selectStyle: React.CSSProperties = {
  backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'><polyline points='6 9 12 15 18 9'/></svg>\")",
  backgroundRepeat: 'no-repeat',
  backgroundPosition: 'right 12px center',
};


export const MarketPage: React.FC = () => {
  const { isSearching, statusText } = useAppState();

  const [okpd2, setOkpd2] = useState('');
  const [region, setRegion] = useState('');
  const [fromDate, setFromDate] = useState(DEFAULT_FROM);
  const [toDate, setToDate] = useState(DEFAULT_TO);

  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [sectors, setSectors] = useState<TopEntry[]>([]);
  const [items, setItems] = useState<TopItemEntry[]>([]);
  const [itemsStatus, setItemsStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [customers, setCustomers] = useState<TopEntry[]>([]);
  const [suppliers, setSuppliers] = useState<TopEntry[]>([]);
  const [timeseries, setTimeseries] = useState<TimeSeriesEntry[]>([]);

  // Per-section loading flags. Карточки появляются прогрессивно по мере
  // прихода ответов, а не «всё разом или ничего». Каждый запрос сам
  // выставляет/снимает свой флаг.
  const [load_overview, setLoadOverview] = useState(false);
  const [load_sectors, setLoadSectors] = useState(false);
  const [load_items, setLoadItems] = useState(false);
  const [load_customers, setLoadCustomers] = useState(false);
  const [load_suppliers, setLoadSuppliers] = useState(false);
  const [load_timeseries, setLoadTimeseries] = useState(false);
  const anyLoading =
    load_overview || load_sectors || load_items ||
    load_customers || load_suppliers || load_timeseries;

  // Прогресс первой загрузки: считаем сколько секций уже не в loading.
  // Items включаем в общее число только когда выбрана отрасль (в остальных
  // случаях этой секции просто нет).
  const flags = okpd2
    ? [load_overview, load_sectors, load_items, load_customers, load_suppliers, load_timeseries]
    : [load_overview, load_sectors, load_customers, load_suppliers, load_timeseries];
  const totalSections = flags.length;
  const doneSections = flags.filter(f => !f).length;

  // «Первая загрузка завершена» = когда anyLoading хоть раз перешёл из
  // true в false. Делаем это через отслеживание перехода, а не через
  // «есть ли данные в overview», иначе лоадер закрывается на первом ответе.
  const [firstLoadDone, setFirstLoadDone] = useState(false);
  const prevAnyLoadingRef = useRef(false);
  useEffect(() => {
    if (prevAnyLoadingRef.current && !anyLoading && !firstLoadDone) {
      setFirstLoadDone(true);
    }
    prevAnyLoadingRef.current = anyLoading;
  }, [anyLoading, firstLoadDone]);
  const isFirstLoad = !firstLoadDone;

  const load = useCallback(() => {
    const params = {
      from_date: fromDate, to_date: toDate,
      okpd2: okpd2 || undefined, region: region || undefined,
    };
    // Топ отраслей всегда показываем по всему рынку (без okpd2-фильтра) —
    // выбранная отрасль подсвечивается на фоне общей картины.
    const sectorsParams = {
      from_date: fromDate, to_date: toDate,
      region: region || undefined, limit: 30,
    };

    setLoadOverview(true);
    api.marketOverview(params)
      .then(setOverview)
      .catch(e => console.error('[market] overview failed', e))
      .finally(() => setLoadOverview(false));

    setLoadSectors(true);
    api.topSectors(sectorsParams)
      .then(setSectors)
      .catch(e => console.error('[market] sectors failed', e))
      .finally(() => setLoadSectors(false));

    setLoadCustomers(true);
    api.topCustomers({ ...params, limit: 10 })
      .then(setCustomers)
      .catch(e => console.error('[market] customers failed', e))
      .finally(() => setLoadCustomers(false));

    setLoadSuppliers(true);
    api.topSuppliers({ ...params, limit: 10 })
      .then(setSuppliers)
      .catch(e => console.error('[market] suppliers failed', e))
      .finally(() => setLoadSuppliers(false));

    setLoadTimeseries(true);
    api.timeseries(params)
      .then(setTimeseries)
      .catch(e => console.error('[market] timeseries failed', e))
      .finally(() => setLoadTimeseries(false));

    // Топ позиций — отдельный запрос со своим статусом, чтобы 404/500
    // на этом endpoint не обнулял остальной дашборд и был видим в UI.
    if (okpd2) {
      setLoadItems(true);
      setItemsStatus('loading');
      api.topItemsInSector({
        from_date: fromDate, to_date: toDate, okpd2,
        region: region || undefined, limit: 15,
      })
        .then(it => { setItems(it); setItemsStatus('ok'); })
        .catch(e => {
          console.error('[market] top-items failed', e);
          setItems([]); setItemsStatus('error');
        })
        .finally(() => setLoadItems(false));
    } else {
      setItems([]); setItemsStatus('idle'); setLoadItems(false);
    }
  }, [okpd2, region, fromDate, toDate]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200">
              <ArrowLeft className="w-5 h-5" />
              <span className="text-sm">Назад в чат</span>
            </Link>
            <div className="border-l border-slate-300 dark:border-slate-700 h-6 mx-2" />
            <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
              <BarChart3 className="w-6 h-6 text-indigo-500" /> Аналитика рынка 44-ФЗ
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {isSearching && (
              <Link to="/" className="flex items-center gap-2 px-3 py-1.5 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-800/50 rounded-lg text-sm text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 transition-colors" title={statusText || 'Идёт поиск в чате'}>
                <Search className="w-4 h-4 animate-pulse" />
                <span>Поиск в чате…</span>
              </Link>
            )}
          </div>
        </div>

        <TopProgressBar visible={anyLoading} />
        <AnalyticsLoader
          visible={isFirstLoad && anyLoading}
          done={doneSections}
          total={totalSections}
        />

        {/* Filters */}
        <div className="mb-6 p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">Отрасль (ОКПД2)</label>
              <select value={okpd2} onChange={e => setOkpd2(e.target.value)} className={selectCls} style={selectStyle}>
                {OKPD2_TOP.map(o => <option key={o.code} value={o.code}>{o.name}</option>)}
                {/* Если выбранный префикс пришёл с клика по бару и его нет в OKPD2_TOP — дописываем,
                    иначе селектор рассинхронизируется с реальным фильтром. */}
                {okpd2 && !OKPD2_TOP.some(o => o.code === okpd2) && (
                  <option value={okpd2}>
                    {okpd2}{sectorNameOf(sectors, okpd2) ? ` — ${sectorNameOf(sectors, okpd2)}` : ''}
                  </option>
                )}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">Регион</label>
              <select value={region} onChange={e => setRegion(e.target.value)} className={selectCls} style={selectStyle}>
                {REGIONS.map(r => <option key={r.code} value={r.code}>{r.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">С даты</label>
              <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">По дату</label>
              <input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-900 text-sm" />
            </div>
          </div>
        </div>

        {/* Overview stats */}
        {overview ? (
          <Refreshing loading={load_overview}>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
              <StatCard label="Контрактов" value={overview.contracts_count.toLocaleString('ru-RU')} />
              <StatCard label="Объём" value={fmtMln(overview.total_sum_rub)} />
              <StatCard label="Заказчиков" value={overview.unique_customers.toLocaleString('ru-RU')} />
              <StatCard label="Поставщиков" value={overview.unique_suppliers.toLocaleString('ru-RU')} />
              <StatCard label="HHI" value={overview.hhi?.toFixed(0) ?? '—'} hint={hhiHint(overview.hhi)} />
            </div>
          </Refreshing>
        ) : load_overview ? (
          <StatTilesSkeleton />
        ) : null}

        {/* Ряд 1: топ отраслей — точка входа в drill-down */}
        <div className="mb-6">
          {sectors.length === 0 && load_sectors ? (
            <SectorsCardSkeleton />
          ) : (
            <Refreshing loading={load_sectors}>
              <SectorsCard sectors={sectors} selectedOkpd2={okpd2} onSelect={setOkpd2} />
            </Refreshing>
          )}
        </div>

        {/* Ряд 2: динамика + скидки — обе карточки фильтруются выбранной отраслью */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          {timeseries.length === 0 && load_timeseries ? (
            <LineChartSkeleton />
          ) : (
            <Refreshing loading={load_timeseries}>
              <ChartCard
                title="Динамика контрактов по месяцам"
                badge={okpd2 ? sectorBadgeLabel(okpd2, sectors) : undefined}
              >
                {timeseries.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={timeseries}>
                      <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                      <XAxis dataKey="month" fontSize={11} />
                      <YAxis fontSize={11} />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="contracts" stroke="#6366f1" name="Контрактов" />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[220px] flex items-center justify-center text-sm text-slate-500">
                    Нет данных за выбранный период
                  </div>
                )}
              </ChartCard>
            </Refreshing>
          )}

          {!overview && load_overview ? (
            <DiscountsCardSkeleton />
          ) : (
            <Refreshing loading={load_overview}>
              <DiscountsCard
                overview={overview}
                badge={okpd2 ? sectorBadgeLabel(okpd2, sectors) : undefined}
              />
            </Refreshing>
          )}
        </div>

        {/* Ряд 3: позиции внутри выбранной отрасли */}
        {okpd2 && (
          <div className="mb-6">
            {items.length === 0 && load_items ? (
              <SkeletonOverlayLoader loading text="Загружаю позиции…">
                <SectorItemsCardSkeleton />
              </SkeletonOverlayLoader>
            ) : (
              <Refreshing loading={load_items}>
                <SectorItemsCard
                  items={items}
                  status={itemsStatus}
                  sectorLabel={`${okpd2}${sectorNameOf(sectors, okpd2) ? ` — ${sectorNameOf(sectors, okpd2)}` : ''}`}
                  fromDate={fromDate}
                  toDate={toDate}
                  region={region}
                />
              </Refreshing>
            )}
          </div>
        )}

        {/* Ряд 4: топы заказчиков и поставщиков */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {customers.length === 0 && load_customers ? (
            <TopTableSkeleton />
          ) : (
            <Refreshing loading={load_customers}>
              <TopTable icon={<Building2 className="w-5 h-5" />} title="Топ заказчиков" rows={customers} />
            </Refreshing>
          )}
          {suppliers.length === 0 && load_suppliers ? (
            <TopTableSkeleton />
          ) : (
            <Refreshing loading={load_suppliers}>
              <TopTable icon={<Factory className="w-5 h-5" />} title="Топ поставщиков" rows={suppliers} />
            </Refreshing>
          )}
        </div>
      </div>
    </div>
  );
};


const StatCard: React.FC<{ label: string; value: string; hint?: string }> = ({ label, value, hint }) => (
  <div className="p-3 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
    <div className="text-xs text-slate-500 mb-1">{label}</div>
    <div className="text-lg font-bold text-slate-800 dark:text-slate-100">{value}</div>
    {hint && <div className="text-xs text-slate-400 mt-0.5">{hint}</div>}
  </div>
);

const ChartCard: React.FC<{
  title: string; badge?: string; children: React.ReactNode;
}> = ({ title, badge, children }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <div className="flex items-center gap-2 mb-3 flex-wrap">
      <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</div>
      {badge && <SectorBadge label={badge} />}
    </div>
    {children}
  </div>
);


const SectorBadge: React.FC<{ label: string }> = ({ label }) => (
  <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-900/40 border border-indigo-200 dark:border-indigo-800/50 text-xs text-indigo-700 dark:text-indigo-300 font-medium max-w-full truncate"
        title={`Данные показаны по отрасли ${label}`}>
    {label}
  </span>
);


const DiscountsCard: React.FC<{ overview: MarketOverview | null; badge?: string }> = ({ overview, badge }) => {
  const has = overview && overview.discounts_sample > 0;
  return (
    <div className="p-4 bg-emerald-50/40 dark:bg-emerald-900/15 rounded-xl border border-emerald-200 dark:border-emerald-800/40 shadow-sm flex flex-col">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300">
          <TrendingDown className="w-4 h-4" /> Скидки на торгах
        </div>
        {badge && <SectorBadge label={badge} />}
      </div>
      {has ? (
        <div className="flex-1 flex flex-col gap-3">
          {/* Перцентили — структура распределения скидок */}
          <div className="grid grid-cols-3 gap-2">
            <PercentileTile label="P25" value={fmtPct(overview!.discount_pct_p25)} />
            <PercentileTile label="Медиана" value={fmtPct(overview!.discount_pct_median)} highlight />
            <PercentileTile label="P75" value={fmtPct(overview!.discount_pct_p75)} />
          </div>

          {/* Главная цифра — суммарная экономия заказчиков */}
          {overview!.total_savings_rub > 0 && (
            <div className="rounded-lg p-3 bg-white dark:bg-slate-800 border border-emerald-200 dark:border-emerald-800/40 flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center shrink-0">
                <PiggyBank className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-0.5">
                  Сэкономлено заказчиками
                </div>
                <div className="text-xl font-bold text-emerald-700 dark:text-emerald-300 leading-tight">
                  {fmtMln(overview!.total_savings_rub)}
                </div>
              </div>
            </div>
          )}

          {/* Конверсия — насколько часто торги дают реальную скидку */}
          {overview!.discount_rate_pct != null && (
            <div>
              <div className="flex items-baseline justify-between text-xs mb-1.5">
                <span className="text-slate-600 dark:text-slate-300">
                  Скидка была в{' '}
                  <span className="font-semibold text-slate-800 dark:text-slate-100">
                    {overview!.contracts_with_discount.toLocaleString('ru-RU')}
                  </span>{' '}
                  из {overview!.contracts_count.toLocaleString('ru-RU')} контрактов
                </span>
                <span className="font-semibold text-emerald-700 dark:text-emerald-300">
                  {fmtPct(overview!.discount_rate_pct)}
                </span>
              </div>
              <div className="h-1.5 bg-emerald-100 dark:bg-emerald-900/30 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 dark:bg-emerald-400 rounded-full transition-all"
                     style={{ width: `${Math.min(100, Math.max(2, overview!.discount_rate_pct!))}%` }} />
              </div>
            </div>
          )}

          <div className="text-xs text-slate-500 mt-auto">
            Выборка {overview!.discounts_sample.toLocaleString('ru-RU')} контрактов со связкой «извещение–контракт»
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-sm text-slate-500">
          Недостаточно связок «извещение–контракт» для расчёта
        </div>
      )}
    </div>
  );
};


const PercentileTile: React.FC<{ label: string; value: string; highlight?: boolean }> = ({ label, value, highlight }) => (
  <div className={`p-3 rounded-lg text-center ${
    highlight
      ? 'bg-white dark:bg-slate-800 border border-emerald-300 dark:border-emerald-700/60'
      : 'bg-white/60 dark:bg-slate-800/60'
  }`}>
    <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-0.5">{label}</div>
    <div className={`text-lg font-bold ${highlight ? 'text-emerald-700 dark:text-emerald-300' : 'text-slate-700 dark:text-slate-200'}`}>
      {value}
    </div>
  </div>
);


function sectorNameOf(sectors: TopEntry[], prefix: string): string {
  return sectors.find(s => s.prefix === prefix)?.name || '';
}

function sectorBadgeLabel(prefix: string, sectors: TopEntry[]): string {
  const name = sectorNameOf(sectors, prefix);
  return name ? `${prefix} — ${name}` : prefix;
}

const TopTable: React.FC<{ icon: React.ReactNode; title: string; rows: TopEntry[] }> = ({ icon, title, rows }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">
      {icon} {title}
    </div>
    {rows.length === 0 ? (
      <div className="text-sm text-slate-500">Нет данных</div>
    ) : (
      <table className="w-full text-xs">
        <thead className="text-slate-500 border-b border-slate-200 dark:border-slate-700">
          <tr>
            <th className="text-left py-1">Компания</th>
            <th className="text-right py-1">Контрактов</th>
            <th className="text-right py-1">Сумма</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.inn || i} className="border-b border-slate-100 dark:border-slate-800">
              <td className="py-1.5 pr-2 truncate max-w-xs" title={r.name}>
                <div className="font-medium text-slate-700 dark:text-slate-200 truncate">{r.short_name || r.name || r.inn}</div>
                <div className="text-slate-400 text-[10px]">ИНН {r.inn}</div>
              </td>
              <td className="text-right py-1.5 text-slate-600 dark:text-slate-300">{r.contracts}</td>
              <td className="text-right py-1.5 font-semibold text-slate-700 dark:text-slate-200">{fmtMln(r.total_sum)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
);

function hhiHint(hhi: number | null): string {
  if (hhi == null) return '';
  if (hhi < 1500) return 'открытый рынок';
  if (hhi < 2500) return 'умеренная концентрация';
  return 'высокая концентрация';
}
