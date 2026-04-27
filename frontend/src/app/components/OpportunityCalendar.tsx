import React, { useMemo } from 'react';
import { CalendarRange } from 'lucide-react';
import { PlansCalendar } from '../api';

const fmtMln = (v: number) =>
  v >= 1e9 ? `${(v / 1e9).toFixed(1)} млрд` :
  v >= 1e6 ? `${(v / 1e6).toFixed(0)} млн` :
  `${Math.round(v).toLocaleString('ru-RU')}`;

/** Календарь возможностей — heatmap годы × отрасли.
 *  Опорный визуал режима «Что будет»: видишь, где и когда появятся деньги.
 *  Цвет ячейки — насыщенность sky-палитры по объёму планов в эту клетку. */
export const OpportunityCalendar: React.FC<{
  data: PlansCalendar;
  onSelectSector?: (prefix: string) => void;
}> = ({ data, onSelectSector }) => {
  const { years, sectors, cells } = data;

  // Карта (year, prefix) → ячейка
  const cellMap = useMemo(() => {
    const m = new Map<string, { positions: number; total_sum: number }>();
    for (const c of cells) m.set(`${c.year}|${c.prefix}`, c);
    return m;
  }, [cells]);

  const maxSum = useMemo(
    () => Math.max(1, ...cells.map(c => c.total_sum)),
    [cells]
  );

  // Линейная интенсивность от 0 до 1 → насыщенность sky-палитры
  // Используем log-scale, иначе 1-2 крупных контракта забивают шкалу
  const intensity = (sum: number): number => {
    if (sum <= 0) return 0;
    return Math.min(1, Math.log10(sum + 1) / Math.log10(maxSum + 1));
  };

  if (!years.length || !sectors.length) {
    return (
      <div className="p-6 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          <CalendarRange className="w-5 h-5 text-sky-500" /> Календарь возможностей
        </div>
        <div className="text-sm text-slate-500 py-8 text-center">
          Нет данных о планируемых закупках в выбранном срезе
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
            <CalendarRange className="w-5 h-5 text-sky-500" /> Календарь возможностей
          </div>
          <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            только то, что ещё не запущено — план есть, извещения нет. Топ отраслей × год.
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span>меньше</span>
          <div className="flex gap-0.5">
            {[0.15, 0.35, 0.55, 0.75, 0.95].map((i) => (
              <div key={i} className="w-3 h-3 rounded-sm"
                   style={{ background: `rgba(14, 165, 233, ${i})` }} />
            ))}
          </div>
          <span>больше</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs border-separate" style={{ borderSpacing: '4px' }}>
          <thead>
            <tr>
              <th className="text-left text-slate-500 font-medium pr-3 pb-1 sticky left-0 bg-white dark:bg-slate-800 z-10">
                Отрасль
              </th>
              {years.map((y) => (
                <th key={y} className="text-center text-slate-500 font-semibold pb-1 min-w-[88px]">
                  {y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sectors.map((s) => (
              <tr key={s.prefix} className="group">
                <td className="pr-3 sticky left-0 bg-white dark:bg-slate-800 z-10
                               group-hover:bg-sky-50/40 dark:group-hover:bg-sky-900/10 transition-colors">
                  <button
                    type="button"
                    onClick={() => onSelectSector?.(s.prefix)}
                    className="text-left max-w-[180px] truncate hover:text-sky-700 dark:hover:text-sky-300 hover:underline"
                    title={`${s.prefix} — ${s.name}`}
                  >
                    <div className="font-medium text-slate-700 dark:text-slate-200 truncate">
                      {s.name || s.prefix}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {s.prefix} · план {fmtMln(s.total_sum)} ₽
                    </div>
                  </button>
                </td>
                {years.map((y) => {
                  const cell = cellMap.get(`${y}|${s.prefix}`);
                  const sum = cell?.total_sum ?? 0;
                  const pos = cell?.positions ?? 0;
                  const i = intensity(sum);
                  const empty = !cell;
                  return (
                    <td key={y} className="p-0">
                      <div
                        className={`h-14 rounded-md flex flex-col items-center justify-center
                                    transition-all
                                    ${empty
                                      ? 'border border-dashed border-slate-200 dark:border-slate-700'
                                      : 'shadow-sm hover:scale-[1.04] hover:shadow-md cursor-default'}`}
                        style={empty ? {} : {
                          background: `rgba(14, 165, 233, ${0.12 + i * 0.78})`,
                          color: i > 0.55 ? 'white' : '#0c4a6e',
                        }}
                        title={empty
                          ? `${s.name} ${y}: нет планов`
                          : `${s.name} в ${y}: ${pos.toLocaleString('ru-RU')} закупок · ${fmtMln(sum)} ₽`}
                      >
                        {empty ? (
                          <span className="text-slate-300 dark:text-slate-600 text-base">·</span>
                        ) : (
                          <>
                            <div className="font-bold text-[13px] leading-none">
                              {fmtMln(sum)}
                            </div>
                            <div className="text-[10px] opacity-80 mt-0.5">
                              {pos.toLocaleString('ru-RU')} зак.
                            </div>
                          </>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
