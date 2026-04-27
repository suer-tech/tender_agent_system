import React from 'react';
import { History, Telescope } from 'lucide-react';

export type AnalyticsMode = 'history' | 'plans';

/** Сегмент-контрол с pill-индикатором: «Что было ↔ Что будет».
 *  Sliding-анимация задаёт ощущение «двойной оптики» — один объект, два режима зрения.
 *  Прошлое — индиго (теплее, плотнее), будущее — sky/cyan (холоднее, «горизонт»). */
export const ModeSwitcher: React.FC<{
  mode: AnalyticsMode;
  onChange: (m: AnalyticsMode) => void;
}> = ({ mode, onChange }) => {
  const isHistory = mode === 'history';
  return (
    <div className="flex justify-center mb-6">
      <div className="relative inline-flex bg-white dark:bg-slate-800/80 backdrop-blur
                      rounded-full p-1 border border-slate-200 dark:border-slate-700
                      shadow-sm select-none">
        {/* Скользящая «таблетка» — фон активной кнопки */}
        <div
          className={`absolute top-1 bottom-1 w-[calc(50%-0.25rem)] rounded-full
                      transition-all duration-300 ease-out shadow-md
                      ${isHistory
                        ? 'left-1 bg-gradient-to-r from-indigo-500 to-indigo-600'
                        : 'left-[calc(50%+0rem)] bg-gradient-to-r from-sky-400 to-cyan-500'}`}
          aria-hidden
        />
        <button
          type="button"
          onClick={() => onChange('history')}
          className={`relative z-10 inline-flex items-center gap-2 px-5 py-2 text-sm font-medium
                      rounded-full transition-colors duration-200
                      ${isHistory
                        ? 'text-white'
                        : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'}`}
        >
          <History className="w-4 h-4" />
          Факт
        </button>
        <button
          type="button"
          onClick={() => onChange('plans')}
          className={`relative z-10 inline-flex items-center gap-2 px-5 py-2 text-sm font-medium
                      rounded-full transition-colors duration-200
                      ${!isHistory
                        ? 'text-white'
                        : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'}`}
        >
          <Telescope className="w-4 h-4" />
          План
        </button>
      </div>
    </div>
  );
};
