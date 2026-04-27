import React, { useEffect, useMemo, useState } from 'react';
import {
  Telescope, Building2, Layers3, Wallet, Activity, Rocket, Hourglass,
} from 'lucide-react';
import {
  api, PlansOverview, PlansCalendar, TopEntry,
} from '../api';
import {
  StatTilesSkeleton, TopTableSkeleton, SectorsCardSkeleton, Refreshing,
} from './Skeletons';
import { OpportunityCalendar } from './OpportunityCalendar';
import { SectorsCard } from './SectorsCard';

const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' :
  v >= 1e9 ? `${(v / 1e9).toFixed(1)} млрд ₽` :
  v >= 1e6 ? `${(v / 1e6).toFixed(1)} млн ₽` :
  `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const fmtCount = (v: number) => v.toLocaleString('ru-RU');

interface Props {
  okpd2: string;
  region: string;
  onSelectOkpd2: (prefix: string) => void;
  onOpenCustomer: (inn: string) => void;
}

export const PlansView: React.FC<Props> = ({
  okpd2, region, onSelectOkpd2, onOpenCustomer,
}) => {
  // Год плана. По умолчанию — самый свежий из доступных в БД.
  const [years, setYears] = useState<number[]>([]);
  const [planYear, setPlanYear] = useState<number | undefined>(undefined);

  const [overview, setOverview] = useState<PlansOverview | null>(null);
  const [sectors, setSectors] = useState<TopEntry[]>([]);
  const [customers, setCustomers] = useState<TopEntry[]>([]);
  const [calendar, setCalendar] = useState<PlansCalendar | null>(null);

  const [loadOverview, setLoadOverview] = useState(false);
  const [loadSectors, setLoadSectors] = useState(false);
  const [loadCustomers, setLoadCustomers] = useState(false);
  const [loadCalendar, setLoadCalendar] = useState(false);

  useEffect(() => {
    api.plansYears().then(({ years }) => {
      setYears(years);
      if (years.length && planYear == null) {
        // Горизонт идёт от текущего года вперёд (БД уже отфильтровала прошлое).
        // По умолчанию — текущий год: «что закупают прямо сейчас».
        const now = new Date().getFullYear();
        setPlanYear(years.includes(now) ? now : years[0]);
      }
    }).catch(e => console.error('[plans] years failed', e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const params = useMemo(() => ({
    plan_year: planYear,
    okpd2: okpd2 || undefined,
    region: region || undefined,
  }), [planYear, okpd2, region]);

  useEffect(() => {
    if (planYear == null) return;

    setLoadOverview(true);
    api.plansOverview(params)
      .then(setOverview)
      .catch(e => console.error('[plans] overview', e))
      .finally(() => setLoadOverview(false));

    setLoadSectors(true);
    api.plansTopSectors({ plan_year: planYear, region: region || undefined, limit: 30 })
      .then(setSectors)
      .catch(e => console.error('[plans] sectors', e))
      .finally(() => setLoadSectors(false));

    setLoadCustomers(true);
    api.plansTopCustomers({ ...params, limit: 10 })
      .then(setCustomers)
      .catch(e => console.error('[plans] customers', e))
      .finally(() => setLoadCustomers(false));

    setLoadCalendar(true);
    api.plansCalendar({ plan_year: planYear, region: region || undefined, top_sectors: 8 })
      .then(setCalendar)
      .catch(e => console.error('[plans] calendar', e))
      .finally(() => setLoadCalendar(false));
  }, [params, planYear, region]);

  return (
    <div className="space-y-6">
      {/* Полоска фильтра «Горизонт» — отдельная узкая панель: для планов
          диапазон дат бессмысленен, нужен только год плана. */}
      <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
            <Telescope className="w-4 h-4 text-sky-500" /> Горизонт планирования:
          </div>
          <div className="inline-flex bg-slate-100 dark:bg-slate-900 rounded-lg p-0.5">
            {years.map((y) => (
              <button
                key={y}
                type="button"
                onClick={() => setPlanYear(y)}
                className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all
                  ${planYear === y
                    ? 'bg-gradient-to-r from-sky-400 to-cyan-500 text-white shadow-sm'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-800'}`}
              >
                {y}
              </button>
            ))}
          </div>
          {okpd2 && (
            <span className="ml-auto inline-flex items-center px-2 py-0.5 rounded-full
                             bg-sky-50 dark:bg-sky-900/40 border border-sky-200 dark:border-sky-800/50
                             text-xs text-sky-700 dark:text-sky-300 font-medium">
              отрасль: {okpd2}
            </span>
          )}
        </div>
      </div>

      {/* KPI плитки. Главное — соотношение «уже запустили / ещё впереди»:
          это и есть метрика дисциплины плана — насколько заказчики выполнили
          свои обещания и сколько возможностей для предпринимателя ещё открыто. */}
      {overview ? (
        <Refreshing loading={loadOverview}>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <KpiTile
              icon={<Layers3 className="w-4 h-4" />}
              label="Запланировано"
              value={fmtCount(overview.positions_count)}
              hint={fmtMln(overview.total_amount_current_year)}
              tone="sky"
            />
            <KpiTile
              icon={<Rocket className="w-4 h-4" />}
              label="Уже запущено"
              value={fmtCount(overview.launched_count)}
              hint={(() => {
                const pct = overview.positions_count
                  ? (100 * overview.launched_count / overview.positions_count).toFixed(0)
                  : '0';
                return `${pct}% · ${fmtMln(overview.launched_sum)}`;
              })()}
              tone="indigo"
            />
            <KpiTile
              icon={<Hourglass className="w-4 h-4" />}
              label="Ещё впереди"
              value={fmtCount(overview.upcoming_count)}
              hint={fmtMln(overview.upcoming_sum)}
              tone="cyan"
              accent
            />
            <KpiTile
              icon={<Building2 className="w-4 h-4" />}
              label="Заказчиков с планами"
              value={fmtCount(overview.unique_customers)}
              tone="emerald"
            />
            <KpiTile
              icon={<Wallet className="w-4 h-4" />}
              label={`Объём на 3 года`}
              value={fmtMln(overview.total_amount_all_years)}
              hint={`текущий: ${fmtMln(overview.total_amount_current_year)}`}
              tone="indigo"
            />
          </div>
        </Refreshing>
      ) : loadOverview ? (
        <StatTilesSkeleton />
      ) : null}

      {/* Календарь возможностей — hero-блок режима */}
      {calendar ? (
        <Refreshing loading={loadCalendar}>
          <OpportunityCalendar data={calendar} onSelectSector={onSelectOkpd2} />
        </Refreshing>
      ) : loadCalendar ? (
        <div className="h-64 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm
                        flex items-center justify-center">
          <Activity className="w-6 h-6 text-sky-500 animate-pulse" />
        </div>
      ) : null}

      {/* Топ отраслей в планах. Переиспользуем SectorsCard как есть — общий
          ритм и интерактив (клик по бару → выбор отрасли) идентичны. */}
      <div>
        {sectors.length === 0 && loadSectors ? (
          <SectorsCardSkeleton />
        ) : (
          <Refreshing loading={loadSectors}>
            <SectorsCard
              sectors={sectors}
              selectedOkpd2={okpd2}
              onSelect={onSelectOkpd2}
            />
          </Refreshing>
        )}
      </div>

      {/* Топ заказчиков с планами */}
      {customers.length === 0 && loadCustomers ? (
        <TopTableSkeleton />
      ) : (
        <Refreshing loading={loadCustomers}>
          <PlanCustomersTable rows={customers} onClickInn={onOpenCustomer} />
        </Refreshing>
      )}
    </div>
  );
};

// ============ subcomponents ============

const KpiTile: React.FC<{
  icon: React.ReactNode; label: string; value: string; hint?: string;
  tone: 'sky' | 'cyan' | 'indigo' | 'emerald';
  /** Усиливает плитку: насыщенный градиент для самой важной KPI («Ещё впереди»). */
  accent?: boolean;
}> = ({ icon, label, value, hint, tone, accent }) => {
  const soft: Record<string, string> = {
    sky: 'from-sky-50 to-white dark:from-sky-900/20 dark:to-slate-800 border-sky-200/70 dark:border-sky-800/40 text-sky-600 dark:text-sky-400',
    cyan: 'from-cyan-50 to-white dark:from-cyan-900/20 dark:to-slate-800 border-cyan-200/70 dark:border-cyan-800/40 text-cyan-600 dark:text-cyan-400',
    indigo: 'from-indigo-50 to-white dark:from-indigo-900/20 dark:to-slate-800 border-indigo-200/70 dark:border-indigo-800/40 text-indigo-600 dark:text-indigo-400',
    emerald: 'from-emerald-50 to-white dark:from-emerald-900/20 dark:to-slate-800 border-emerald-200/70 dark:border-emerald-800/40 text-emerald-600 dark:text-emerald-400',
  };
  if (accent) {
    return (
      <div className="p-3 rounded-xl border border-cyan-300 dark:border-cyan-700/60
                      bg-gradient-to-br from-cyan-500 to-sky-600 text-white shadow-md
                      ring-2 ring-cyan-200/60 dark:ring-cyan-700/30">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide font-semibold opacity-90 mb-1">
          {icon} {label}
        </div>
        <div className="text-lg font-bold leading-tight">{value}</div>
        {hint && <div className="text-[11px] opacity-85 mt-0.5 truncate" title={hint}>{hint}</div>}
      </div>
    );
  }
  return (
    <div className={`p-3 rounded-xl border bg-gradient-to-br ${soft[tone]} shadow-sm`}>
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide font-semibold opacity-90 mb-1">
        {icon} {label}
      </div>
      <div className="text-lg font-bold text-slate-800 dark:text-slate-100 leading-tight">{value}</div>
      {hint && <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 truncate" title={hint}>{hint}</div>}
    </div>
  );
};

const PlanCustomersTable: React.FC<{
  rows: TopEntry[]; onClickInn?: (inn: string) => void;
}> = ({ rows, onClickInn }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200 mb-3">
      <Building2 className="w-5 h-5 text-sky-500" />
      Топ заказчиков с планами
    </div>
    {rows.length === 0 ? (
      <div className="text-sm text-slate-500">Нет данных</div>
    ) : (
      <table className="w-full text-xs">
        <thead className="text-slate-500 border-b border-slate-200 dark:border-slate-700">
          <tr>
            <th className="text-left py-1">Заказчик</th>
            <th className="text-right py-1">Закупок в плане</th>
            <th className="text-right py-1">Объём плана</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const clickable = !!onClickInn && !!r.inn;
            return (
              <tr key={r.inn || i}
                  onClick={clickable ? () => onClickInn!(r.inn!) : undefined}
                  className={`border-b border-slate-100 dark:border-slate-800 transition-colors
                              ${clickable ? 'cursor-pointer hover:bg-sky-50/40 dark:hover:bg-sky-900/15' : ''}`}>
                <td className="py-1.5 pr-2 truncate max-w-xs" title={r.name || ''}>
                  <div className={`font-medium truncate ${clickable
                    ? 'text-sky-700 dark:text-sky-300 hover:underline'
                    : 'text-slate-700 dark:text-slate-200'}`}>
                    {r.short_name || r.name || r.inn}
                  </div>
                  <div className="text-slate-400 text-[10px]">ИНН {r.inn}</div>
                </td>
                <td className="text-right py-1.5 text-slate-600 dark:text-slate-300">{r.contracts}</td>
                <td className="text-right py-1.5 font-semibold text-slate-700 dark:text-slate-200">
                  {fmtMln(r.total_sum)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    )}
  </div>
);
