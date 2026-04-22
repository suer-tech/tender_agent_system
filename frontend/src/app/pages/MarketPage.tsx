import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend,
} from 'recharts';
import {
  api, REGIONS, OKPD2_TOP,
  MarketOverview, TopEntry, TimeSeriesEntry,
} from '../api';
import { ArrowLeft, TrendingDown, Building2, Factory, BarChart3, Loader2, Search } from 'lucide-react';
import { useAppState } from '../store';

const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' : v >= 1_000_000_000
    ? `${(v / 1_000_000_000).toFixed(1)} млрд ₽`
    : v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)} млн ₽`
      : `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const fmtPct = (v: number | null | undefined) => v == null ? '—' : `${v.toFixed(1)}%`;

// По дефолту — весь апрель 2026 (наши данные)
const DEFAULT_FROM = '2026-04-01';
const DEFAULT_TO = '2026-04-30';

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
  const [customers, setCustomers] = useState<TopEntry[]>([]);
  const [suppliers, setSuppliers] = useState<TopEntry[]>([]);
  const [timeseries, setTimeseries] = useState<TimeSeriesEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const params = {
      from_date: fromDate, to_date: toDate,
      okpd2: okpd2 || undefined, region: region || undefined,
    };
    try {
      const [ov, sc, cs, sp, ts] = await Promise.all([
        api.marketOverview(params),
        api.topSectors({ ...params, limit: 10 }),
        api.topCustomers({ ...params, limit: 10 }),
        api.topSuppliers({ ...params, limit: 10 }),
        api.timeseries(params),
      ]);
      setOverview(ov); setSectors(sc); setCustomers(cs); setSuppliers(sp); setTimeseries(ts);
    } catch (e) {
      console.error('[market] load failed', e);
    } finally {
      setLoading(false);
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
            {loading && <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />}
          </div>
        </div>

        {/* Filters */}
        <div className="mb-6 p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1">Отрасль (ОКПД2)</label>
              <select value={okpd2} onChange={e => setOkpd2(e.target.value)} className={selectCls} style={selectStyle}>
                {OKPD2_TOP.map(o => <option key={o.code} value={o.code}>{o.name}</option>)}
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
        {overview && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
            <StatCard label="Контрактов" value={overview.contracts_count.toLocaleString('ru-RU')} />
            <StatCard label="Объём" value={fmtMln(overview.total_sum_rub)} />
            <StatCard label="Заказчиков" value={overview.unique_customers.toLocaleString('ru-RU')} />
            <StatCard label="Поставщиков" value={overview.unique_suppliers.toLocaleString('ru-RU')} />
            <StatCard label="HHI" value={overview.hhi?.toFixed(0) ?? '—'} hint={hhiHint(overview.hhi)} />
          </div>
        )}

        {/* Discount panel */}
        {overview && overview.discounts_sample > 0 && (
          <div className="mb-6 p-4 bg-emerald-50/50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800/40 rounded-xl">
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300 font-semibold mb-2">
              <TrendingDown className="w-5 h-5" /> Скидки на торгах
            </div>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div><span className="text-slate-500">25-й перцентиль:</span> <b>{fmtPct(overview.discount_pct_p25)}</b></div>
              <div><span className="text-slate-500">медиана:</span> <b>{fmtPct(overview.discount_pct_median)}</b></div>
              <div><span className="text-slate-500">75-й перцентиль:</span> <b>{fmtPct(overview.discount_pct_p75)}</b></div>
            </div>
            <div className="mt-1 text-xs text-slate-500">Выборка {overview.discounts_sample} контрактов со связкой «извещение-контракт»</div>
          </div>
        )}

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          {timeseries.length > 0 && (
            <ChartCard title="Динамика контрактов по месяцам">
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
            </ChartCard>
          )}

          {sectors.length > 0 && !okpd2 && (
            <ChartCard title="Топ отраслей (ОКПД2) по объёму">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={sectors.slice(0, 10)} layout="vertical">
                  <XAxis type="number" fontSize={11} tickFormatter={v => fmtMln(v)} />
                  <YAxis dataKey="prefix" type="category" fontSize={11} width={40} />
                  <Tooltip formatter={(v: any) => fmtMln(v as number)} />
                  <Bar dataKey="total_sum" fill="#10b981" />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          )}
        </div>

        {/* Top tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TopTable icon={<Building2 className="w-5 h-5" />} title="Топ заказчиков" rows={customers} />
          <TopTable icon={<Factory className="w-5 h-5" />} title="Топ поставщиков" rows={suppliers} />
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

const ChartCard: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <div className="text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">{title}</div>
    {children}
  </div>
);

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
                <div className="font-medium text-slate-700 dark:text-slate-200 truncate">{r.name || r.inn}</div>
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
