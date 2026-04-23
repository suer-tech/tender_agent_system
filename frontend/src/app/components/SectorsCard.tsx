import React, { useState, useMemo, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from 'recharts';
import { BarChart3, PieChart as PieIcon, X } from 'lucide-react';
import { TopEntry } from '../api';

// Tableau-10 — качественная палитра, читаемая на светлой и тёмной темах.
const TABLEAU10 = [
  '#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F',
  '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC',
];
const DIM_COLOR_LIGHT = '#e2e8f0'; // slate-200
const DIM_COLOR_DARK = '#334155';  // slate-700
const OTHER_COLOR = '#94a3b8';     // slate-400 — ломтик «Прочие»

type View = 'bar' | 'pie';

const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' : v >= 1_000_000_000
    ? `${(v / 1_000_000_000).toFixed(1)} млрд ₽`
    : v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)} млн ₽`
      : `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const fmtPct = (v: number | null | undefined) =>
  v == null ? '—' : `${v.toFixed(1)}%`;

interface Props {
  /** Топ отраслей за период (всегда полный рынок, без фильтра по okpd2). */
  sectors: TopEntry[];
  /** Текущий фильтр ОКПД2 (любой длины — берём первые 2 символа). */
  selectedOkpd2: string;
  /** Клик по бару/сектору. Передаём 2-значный префикс или '' для сброса. */
  onSelect: (prefix2: string) => void;
}

/** Полноширинная карточка «Топ отраслей» с переключателем Bar / Donut.
 *
 *  Поведение:
 *  - Если ничего не выбрано → все 10 баров/секторов цветные (Tableau-10).
 *  - Если выбран фильтр → бар/сектор выбранной отрасли цветной, остальные
 *    приглушены. Выбор сохраняется при переключении вида.
 *  - Клик по бару/сектору устанавливает или снимает фильтр.
 *  - Если выбранная отрасль не входит в top-10 → её строка добавляется
 *    отдельно ниже разделителя.
 *  - Тип отображения запоминается в localStorage.
 */
export const SectorsCard: React.FC<Props> = ({ sectors, selectedOkpd2, onSelect }) => {
  const [view, setView] = useState<View>(() => {
    if (typeof window === 'undefined') return 'bar';
    return (localStorage.getItem('sectorsView') as View) || 'bar';
  });
  useEffect(() => { localStorage.setItem('sectorsView', view); }, [view]);

  const selectedPrefix = selectedOkpd2 ? selectedOkpd2.slice(0, 2) : '';
  const top10 = sectors.slice(0, 10);
  const totalSum = useMemo(() => sectors.reduce((s, e) => s + (e.total_sum || 0), 0), [sectors]);

  // Если выбранная отрасль ниже top-10, найдём её отдельно для вставки.
  const selectedInTop = top10.some(e => e.prefix === selectedPrefix);
  const selectedExtra = !selectedInTop && selectedPrefix
    ? sectors.find(e => e.prefix === selectedPrefix)
    : undefined;
  const selectedRank = selectedExtra
    ? sectors.findIndex(e => e.prefix === selectedPrefix) + 1
    : 0;

  const selectedEntry = sectors.find(e => e.prefix === selectedPrefix);

  const colorFor = (prefix: string | undefined, idx: number) => {
    if (!selectedPrefix) return TABLEAU10[idx % TABLEAU10.length];
    if (prefix === selectedPrefix) return TABLEAU10[idx % TABLEAU10.length];
    return DIM_COLOR_LIGHT;
  };

  // Pie data: top-9 + «Прочие» одним ломтиком (если есть остаток).
  const pieData = useMemo(() => {
    const top9 = sectors.slice(0, 9);
    const restSum = sectors.slice(9).reduce((s, e) => s + (e.total_sum || 0), 0);
    const restPct = totalSum ? (restSum / totalSum) * 100 : 0;
    const out: any[] = top9.map((e, i) => ({
      ...e,
      _color: colorFor(e.prefix, i),
      label: `${e.prefix} · ${e.name || '—'}`,
    }));
    if (restSum > 0) {
      out.push({
        prefix: '__other__',
        name: 'Прочие',
        contracts: 0,
        total_sum: restSum,
        share_pct: restPct,
        _color: !selectedPrefix ? OTHER_COLOR : DIM_COLOR_LIGHT,
        label: 'Прочие',
      });
    }
    return out;
  }, [sectors, totalSum, selectedPrefix]);

  return (
    <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <div className="text-sm font-semibold text-slate-700 dark:text-slate-200 whitespace-nowrap">
            Топ отраслей (ОКПД2) по объёму
          </div>
          {selectedEntry && (
            <button
              onClick={() => onSelect('')}
              title="Снять фильтр"
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-900/40 border border-indigo-200 dark:border-indigo-800/50 text-xs text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition-colors max-w-full">
              <span className="font-semibold">{selectedEntry.prefix}</span>
              <span className="truncate">{selectedEntry.name || ''}</span>
              <span className="text-indigo-500 dark:text-indigo-400 whitespace-nowrap">
                {fmtPct(selectedEntry.share_pct)}
              </span>
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
        <ViewToggle view={view} onChange={setView} />
      </div>

      {sectors.length === 0 ? (
        <div className="text-sm text-slate-500 py-8 text-center">Нет данных за выбранный период</div>
      ) : view === 'bar' ? (
        <SectorsBar
          top10={top10}
          selectedPrefix={selectedPrefix}
          colorFor={colorFor}
          selectedExtra={selectedExtra}
          selectedRank={selectedRank}
          onSelect={onSelect}
        />
      ) : (
        <SectorsPie
          data={pieData}
          totalSum={totalSum}
          selectedPrefix={selectedPrefix}
          onSelect={onSelect}
        />
      )}
    </div>
  );
};


const ViewToggle: React.FC<{ view: View; onChange: (v: View) => void }> = ({ view, onChange }) => (
  <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden text-xs">
    <button
      onClick={() => onChange('bar')}
      className={`flex items-center gap-1 px-2.5 py-1 transition-colors ${
        view === 'bar'
          ? 'bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
          : 'bg-white dark:bg-slate-800 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-700/50'
      }`}>
      <BarChart3 className="w-3.5 h-3.5" /> Бары
    </button>
    <button
      onClick={() => onChange('pie')}
      className={`flex items-center gap-1 px-2.5 py-1 border-l border-slate-200 dark:border-slate-600 transition-colors ${
        view === 'pie'
          ? 'bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
          : 'bg-white dark:bg-slate-800 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-700/50'
      }`}>
      <PieIcon className="w-3.5 h-3.5" /> Кольцо
    </button>
  </div>
);


const SectorsBar: React.FC<{
  top10: TopEntry[];
  selectedPrefix: string;
  colorFor: (p: string | undefined, i: number) => string;
  selectedExtra?: TopEntry;
  selectedRank: number;
  onSelect: (prefix2: string) => void;
}> = ({ top10, selectedPrefix, colorFor, selectedExtra, selectedRank, onSelect }) => {
  const data = top10.map((e, i) => ({
    ...e,
    label: `${e.prefix} · ${e.name || '—'}`,
    _color: colorFor(e.prefix, i),
  }));

  const handleClick = (entry: any) => {
    if (!entry || !entry.prefix) return;
    onSelect(entry.prefix === selectedPrefix ? '' : entry.prefix);
  };

  return (
    <>
      <ResponsiveContainer width="100%" height={Math.max(280, top10.length * 32 + 40)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 60, left: 0, bottom: 4 }}>
          <XAxis type="number" fontSize={11} tickFormatter={v => fmtMln(v)} />
          <YAxis dataKey="label" type="category" fontSize={12} width={210}
                 tick={{ fill: 'currentColor' }}
                 className="text-slate-700 dark:text-slate-300" />
          <Tooltip
            cursor={{ fill: 'rgba(99,102,241,0.06)' }}
            content={<SectorsTooltip />} />
          <Bar dataKey="total_sum" onClick={handleClick} cursor="pointer"
               radius={[0, 4, 4, 0]}
               label={{ position: 'right', formatter: (v: any, e: any) => {
                 // Показываем долю % справа от бара. e — entry, но recharts типизирует слабо.
                 const pct = (e && e.share_pct != null) ? e.share_pct : null;
                 return pct != null ? `${pct.toFixed(1)}%` : '';
               }, fontSize: 11, fill: '#64748b' }}>
            {data.map((d, i) => <Cell key={i} fill={d._color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {selectedExtra && (
        <div className="mt-3 pt-3 border-t border-dashed border-slate-200 dark:border-slate-700">
          <div className="text-xs text-slate-500 mb-1.5">
            Выбранная отрасль вне топ-10 ({selectedRank}-е место):
          </div>
          <button
            onClick={() => onSelect('')}
            className="w-full flex items-center gap-3 p-2 rounded-lg bg-indigo-50/50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800/40 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-colors text-left">
            <div className="font-semibold text-indigo-700 dark:text-indigo-300 text-sm w-10 shrink-0">
              {selectedExtra.prefix}
            </div>
            <div className="flex-1 truncate text-sm text-slate-700 dark:text-slate-200">
              {selectedExtra.name || '—'}
            </div>
            <div className="text-sm font-semibold text-slate-800 dark:text-slate-100 whitespace-nowrap">
              {fmtMln(selectedExtra.total_sum)}
            </div>
            <div className="text-xs text-slate-500 w-14 text-right whitespace-nowrap">
              {fmtPct(selectedExtra.share_pct)}
            </div>
          </button>
        </div>
      )}
    </>
  );
};


const SectorsPie: React.FC<{
  data: any[];
  totalSum: number;
  selectedPrefix: string;
  onSelect: (prefix2: string) => void;
}> = ({ data, totalSum, selectedPrefix, onSelect }) => {
  const handleClick = (entry: any) => {
    if (!entry || !entry.prefix || entry.prefix === '__other__') return;
    onSelect(entry.prefix === selectedPrefix ? '' : entry.prefix);
  };

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={340}>
        <PieChart>
          <Pie
            data={data}
            dataKey="total_sum"
            nameKey="label"
            cx="50%"
            cy="50%"
            innerRadius={75}
            outerRadius={130}
            paddingAngle={1}
            onClick={handleClick}
            cursor="pointer">
            {data.map((d, i) => (
              <Cell key={i}
                    fill={d._color}
                    stroke={d.prefix === selectedPrefix ? '#1e293b' : '#fff'}
                    strokeWidth={d.prefix === selectedPrefix ? 2 : 1} />
            ))}
          </Pie>
          <Tooltip content={<SectorsTooltip />} />
          <Legend
            verticalAlign="bottom"
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            formatter={(value: string, entry: any) => {
              const e = entry?.payload;
              if (!e) return value;
              const pct = e.share_pct != null ? ` · ${e.share_pct.toFixed(1)}%` : '';
              return (
                <span className="text-slate-600 dark:text-slate-300">
                  {value}<span className="text-slate-400">{pct}</span>
                </span>
              );
            }}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Центральная подпись donut: total */}
      <div className="absolute left-1/2 top-[145px] -translate-x-1/2 -translate-y-1/2 text-center pointer-events-none">
        <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-0.5">Всего</div>
        <div className="text-base font-bold text-slate-800 dark:text-slate-100 whitespace-nowrap">
          {fmtMln(totalSum)}
        </div>
      </div>
    </div>
  );
};


const SectorsTooltip: React.FC<any> = ({ active, payload }) => {
  if (!active || !payload || !payload.length) return null;
  const e = payload[0].payload;
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg px-3 py-2 text-xs">
      {e.prefix && e.prefix !== '__other__' && (
        <div className="font-semibold text-slate-800 dark:text-slate-100 mb-1">
          {e.prefix} · {e.name || '—'}
        </div>
      )}
      {e.prefix === '__other__' && (
        <div className="font-semibold text-slate-800 dark:text-slate-100 mb-1">Прочие отрасли</div>
      )}
      <div className="space-y-0.5">
        <div className="text-slate-600 dark:text-slate-300">
          Сумма: <span className="font-semibold text-slate-800 dark:text-slate-100">{fmtMln(e.total_sum)}</span>
        </div>
        {e.contracts > 0 && (
          <div className="text-slate-600 dark:text-slate-300">
            Контрактов: <span className="font-semibold text-slate-800 dark:text-slate-100">{e.contracts.toLocaleString('ru-RU')}</span>
          </div>
        )}
        {e.share_pct != null && (
          <div className="text-slate-600 dark:text-slate-300">
            Доля: <span className="font-semibold text-slate-800 dark:text-slate-100">{fmtPct(e.share_pct)}</span>
          </div>
        )}
      </div>
    </div>
  );
};
