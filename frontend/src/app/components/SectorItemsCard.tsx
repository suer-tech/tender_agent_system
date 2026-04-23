import React, { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { Package } from 'lucide-react';
import { TopItemEntry } from '../api';

const TABLEAU10 = [
  '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F',
  '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC',
];

type Metric = 'sum' | 'contracts';

const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' : v >= 1_000_000_000
    ? `${(v / 1_000_000_000).toFixed(1)} млрд ₽`
    : v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)} млн ₽`
      : `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const fmtPct = (v: number | null | undefined) =>
  v == null ? '—' : `${v.toFixed(1)}%`;

interface Props {
  items: TopItemEntry[];
  /** Заголовок отрасли (например, «21 — Фармацевтика») для подписи в шапке. */
  sectorLabel: string;
}

/** Топ конкретных позиций (товаров/услуг) внутри выбранной отрасли.
 *  Метрика переключается: по объёму ₽ или по числу контрактов.
 *  Группировка по полному коду ОКПД2 — это и есть «один товар/услуга».
 */
export const SectorItemsCard: React.FC<Props> = ({ items, sectorLabel }) => {
  const [metric, setMetric] = useState<Metric>('sum');

  if (items.length === 0) {
    return (
      <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
        <Header sectorLabel={sectorLabel} metric={metric} onMetric={setMetric} />
        <div className="text-sm text-slate-500 py-8 text-center">
          В этой отрасли нет позиций за выбранный период
        </div>
      </div>
    );
  }

  const dataKey = metric === 'sum' ? 'total_sum' : 'contracts';
  const sorted = [...items].sort((a, b) =>
    (b[dataKey] as number) - (a[dataKey] as number));

  // Если переключились на «контракты», доли в API про объём — пересчитаем под контракты.
  const totalContracts = items.reduce((s, e) => s + e.contracts, 0);
  const data = sorted.map((e, i) => ({
    ...e,
    label: trimLabel(e.code, e.name),
    _color: TABLEAU10[i % TABLEAU10.length],
    _share: metric === 'sum'
      ? e.share_pct
      : (totalContracts ? (e.contracts / totalContracts) * 100 : 0),
  }));

  return (
    <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
      <Header sectorLabel={sectorLabel} metric={metric} onMetric={setMetric} />
      <ResponsiveContainer width="100%" height={Math.max(280, data.length * 32 + 40)}>
        <BarChart data={data} layout="vertical"
                  margin={{ top: 4, right: 70, left: 0, bottom: 4 }}>
          <XAxis type="number" fontSize={11}
                 tickFormatter={v => metric === 'sum' ? fmtMln(v) : v.toLocaleString('ru-RU')} />
          <YAxis dataKey="label" type="category" fontSize={11.5} width={300}
                 tick={{ fill: 'currentColor' }}
                 className="text-slate-700 dark:text-slate-300" />
          <Tooltip cursor={{ fill: 'rgba(99,102,241,0.06)' }}
                   content={<ItemTooltip metric={metric} />} />
          <Bar dataKey={dataKey} radius={[0, 4, 4, 0]}
               label={{ position: 'right',
                        formatter: (v: any, e: any) => {
                          const pct = (e && e._share != null) ? e._share : null;
                          return pct != null ? `${pct.toFixed(1)}%` : '';
                        },
                        fontSize: 11, fill: '#64748b' }}>
            {data.map((d, i) => <Cell key={i} fill={d._color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};


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


const ItemTooltip: React.FC<any> = ({ active, payload, metric }) => {
  if (!active || !payload || !payload.length) return null;
  const e = payload[0].payload;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg px-3 py-2 text-xs max-w-md">
      <div className="font-semibold text-slate-800 dark:text-slate-100 mb-1">
        {e.code}
      </div>
      <div className="text-slate-600 dark:text-slate-300 mb-1.5">
        {e.name || '—'}
      </div>
      <div className="space-y-0.5 border-t border-slate-200 dark:border-slate-700 pt-1.5">
        <div className="text-slate-600 dark:text-slate-300">
          Объём: <span className="font-semibold text-slate-800 dark:text-slate-100">{fmtMln(e.total_sum)}</span>
        </div>
        <div className="text-slate-600 dark:text-slate-300">
          Контрактов: <span className="font-semibold text-slate-800 dark:text-slate-100">{e.contracts.toLocaleString('ru-RU')}</span>
        </div>
        <div className="text-slate-600 dark:text-slate-300">
          Доля в отрасли ({metric === 'sum' ? 'по ₽' : 'по контрактам'}):{' '}
          <span className="font-semibold text-slate-800 dark:text-slate-100">{fmtPct(e._share)}</span>
        </div>
      </div>
    </div>
  );
};


/** Лейбл для оси Y: «21.20.10.194 · Препараты противоопухолевые …»,
 *  обрезаем длинное название чтобы влезло в 300px. */
function trimLabel(code: string, name: string | null): string {
  const n = (name || '—').trim();
  const max = 42;
  const short = n.length > max ? n.slice(0, max - 1) + '…' : n;
  return `${code} · ${short}`;
}
