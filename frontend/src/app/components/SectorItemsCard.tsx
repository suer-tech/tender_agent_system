import React, { useState, useMemo } from 'react';
import { Package, Loader2, AlertTriangle, Trophy } from 'lucide-react';
import { TopItemEntry } from '../api';

type Metric = 'sum' | 'contracts';

const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' : v >= 1_000_000_000
    ? `${(v / 1_000_000_000).toFixed(1)} млрд ₽`
    : v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)} млн ₽`
      : `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const fmtPct = (v: number | null | undefined) =>
  v == null ? '—' : `${v.toFixed(1)}%`;

const ruPlural = (n: number, forms: [string, string, string]) => {
  const n10 = n % 10, n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return forms[0];
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return forms[1];
  return forms[2];
};

interface Props {
  items: TopItemEntry[];
  status: 'idle' | 'loading' | 'ok' | 'error';
  /** Заголовок отрасли (например, «21 — Фармацевтика») для подписи в шапке. */
  sectorLabel: string;
}

/** Топ позиций (товаров/услуг) внутри выбранной отрасли — в виде лидерборда.
 *  Намеренно не bar-chart: рядом стоит SectorsCard (тоже бары), и два бара
 *  визуально сливаются. Лидерборд другой жанр — список карточек с рангом,
 *  кодом, полным названием, тонкой прогресс-полоской доли и метриками.
 */
export const SectorItemsCard: React.FC<Props> = ({ items, status, sectorLabel }) => {
  // ВАЖНО: все хуки вызываем безусловно ДО любых early-return,
  // иначе React падает с error #310 при смене статуса (loading → ok).
  const [metric, setMetric] = useState<Metric>('sum');

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
        {ranked.map(it => <ItemRow key={it.code} item={it} metric={metric} />)}
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
}> = ({ item, metric }) => {
  const isMedal = item._rank <= 3;
  const medalCls =
    item._rank === 1 ? 'bg-amber-100 text-amber-700 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-800/40' :
    item._rank === 2 ? 'bg-slate-200 text-slate-700 ring-slate-300 dark:bg-slate-700 dark:text-slate-200 dark:ring-slate-600' :
    item._rank === 3 ? 'bg-orange-100 text-orange-700 ring-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:ring-orange-800/40' :
                       'bg-slate-50 text-slate-500 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700';

  return (
    <div className="py-3 first:pt-1 last:pb-1 flex gap-3 hover:bg-slate-50/60 dark:hover:bg-slate-700/20 -mx-2 px-2 rounded-lg transition-colors">
      {/* Rank — крупный, медальный для топ-3 */}
      <div className={`shrink-0 w-9 h-9 rounded-lg flex items-center justify-center font-bold text-base ring-1 ${medalCls}`}
           title={`${item._rank}-е место`}>
        {isMedal ? <span className="flex items-center gap-0.5"><Trophy className="w-3 h-3" />{item._rank}</span> : item._rank}
      </div>

      {/* Основное содержимое */}
      <div className="flex-1 min-w-0">
        {/* Шапка: код-бейдж + название */}
        <div className="flex items-baseline gap-2 mb-1">
          <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 shrink-0">
            {item.code}
          </span>
          <div className="text-sm text-slate-800 dark:text-slate-100 leading-snug">
            {item.name || '—'}
          </div>
        </div>

        {/* Прогресс-полоска доли (тонкая, не доминирует) */}
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

        {/* Метрики — в зависимости от выбранного режима меняется акцент */}
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
    </div>
  );
};
