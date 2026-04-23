import React from 'react';
import { Loader2, BarChart3 } from 'lucide-react';

/** Базовый прямоугольник скелетона. */
export const Skeleton: React.FC<{ className?: string; style?: React.CSSProperties }> =
  ({ className = '', style }) => (
    <div
      className={`bg-slate-200 dark:bg-slate-700/60 rounded animate-pulse ${className}`}
      style={style}
    />
  );

/** Полоска прогресса наверху страницы — Linear-app-style: индиго подложка
 *  + бегущая стрипа-градиент. Высоко-видимый индикатор фоновой загрузки. */
export const TopProgressBar: React.FC<{ visible: boolean }> = ({ visible }) => (
  <>
    <style>{`
      @keyframes top-progress-slide {
        0%   { transform: translateX(-100%); }
        100% { transform: translateX(250%); }
      }
    `}</style>
    <div
      className={`fixed top-0 left-0 right-0 h-[3px] z-50 pointer-events-none overflow-hidden
                  transition-opacity duration-300
                  ${visible ? 'opacity-100' : 'opacity-0'}`}
      aria-hidden={!visible}>
      <div className="absolute inset-0 bg-indigo-100 dark:bg-indigo-950/40" />
      <div
        className="absolute inset-y-0 w-2/5 bg-gradient-to-r from-transparent via-indigo-500 to-transparent"
        style={{ animation: 'top-progress-slide 1.4s ease-in-out infinite' }}
      />
    </div>
  </>
);


// Палитра баров эквалайзера: indigo → violet → emerald.
const EQ_COLORS = ['#6366f1', '#818cf8', '#a78bfa', '#22c55e', '#10b981'];
const EQ_KEYFRAMES = `@keyframes eq-bounce { 0%,100% { transform: scaleY(0.25); } 50% { transform: scaleY(1); } }`;

/** Эквалайзер — переиспользуемый «спинер». Сам по себе ничего не позиционирует,
 *  можно класть и в floating-overlay, и в inline-блок, и в overlay поверх
 *  скелетона. */
export const EqualizerSpinner: React.FC<{ size?: 'sm' | 'md' | 'lg' }> = ({ size = 'md' }) => {
  const dims = size === 'sm'
    ? { gap: 'gap-1', h: 'h-7', w: 'w-1.5' }
    : size === 'lg'
      ? { gap: 'gap-2', h: 'h-16', w: 'w-2.5' }
      : { gap: 'gap-1.5', h: 'h-12', w: 'w-2' };
  return (
    <>
      <style>{EQ_KEYFRAMES}</style>
      <div className={`flex items-end ${dims.gap} ${dims.h}`}>
        {EQ_COLORS.map((color, i) => (
          <div key={i}
               className={`${dims.w} h-full origin-bottom rounded-sm`}
               style={{
                 background: color,
                 animation: 'eq-bounce 0.9s ease-in-out infinite',
                 animationDelay: `${i * 0.11}s`,
               }}
          />
        ))}
      </div>
    </>
  );
};


/** Внутренняя карточка лоадера — общая для AnalyticsLoader (центр страницы)
 *  и SkeletonOverlayLoader (центр конкретного скелетона). */
const LoaderCard: React.FC<{
  text: string;
  done?: number;
  total?: number;
}> = ({ text, done, total }) => (
  <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl
                  border border-slate-200 dark:border-slate-700
                  px-6 py-5 flex flex-col items-center gap-3 min-w-[240px]">
    <EqualizerSpinner size="md" />
    <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
      <BarChart3 className="w-4 h-4 text-indigo-500" />
      {text}
    </div>
    {total != null && total > 0 && done != null && (
      <div className="w-full">
        <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1">
          <span>Загружаем разделы</span>
          <span className="font-mono">{done}/{total}</span>
        </div>
        <div className="h-1 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
          <div className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full transition-all duration-300"
               style={{ width: `${(done / total) * 100}%` }} />
        </div>
      </div>
    )}
  </div>
);


/** Центральный лоадер первой загрузки — full-screen overlay. */
export const AnalyticsLoader: React.FC<{
  visible: boolean;
  done: number;
  total: number;
}> = ({ visible, done, total }) => {
  if (!visible) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center pointer-events-none"
         aria-live="polite" aria-busy="true">
      <div className="absolute inset-0 backdrop-blur-[1px] bg-slate-50/30 dark:bg-slate-950/30" />
      <div className="relative">
        <LoaderCard text="Собираем аналитику…" done={done} total={total} />
      </div>
    </div>
  );
};


/** Обёртка: скелетон под, центрированный лоадер сверху. Используется когда
 *  нужно показать форму будущего контента + явно сигнализировать активность. */
export const SkeletonOverlayLoader: React.FC<{
  loading: boolean;
  text: string;
  children: React.ReactNode;
}> = ({ loading, text, children }) => (
  <div className="relative">
    {children}
    {loading && (
      <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none"
           aria-live="polite" aria-busy="true">
        <div className="absolute inset-0 backdrop-blur-[1px] bg-white/30 dark:bg-slate-900/30 rounded-xl" />
        <div className="relative">
          <LoaderCard text={text} />
        </div>
      </div>
    )}
  </div>
);

/** Обёртка-«обновляю»: затемняет содержимое и накладывает плашку со спинером
 *  в правом верхнем углу. Используется когда у карточки уже есть данные,
 *  но идёт фоновое обновление (например, после смены отрасли). */
export const Refreshing: React.FC<{ loading: boolean; children: React.ReactNode }> =
  ({ loading, children }) => (
    <div className="relative">
      <div className={`transition-opacity duration-150 ${loading ? 'opacity-40 pointer-events-none' : ''}`}>
        {children}
      </div>
      {loading && (
        <div className="absolute top-3 right-3 z-10 flex items-center gap-1.5 px-2 py-1 rounded-full
                        bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600
                        shadow-sm text-xs text-slate-600 dark:text-slate-300">
          <Loader2 className="w-3 h-3 animate-spin" /> обновляю
        </div>
      )}
    </div>
  );

// ============================================================================
// Скелетоны конкретных карточек — повторяют форму реального контента,
// чтобы при загрузке layout не прыгал.
// ============================================================================

export const StatTilesSkeleton: React.FC = () => (
  <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
    {Array.from({ length: 5 }).map((_, i) => (
      <div key={i}
           className="p-3 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
        <Skeleton className="h-3 w-20 mb-2" />
        <Skeleton className="h-6 w-24" />
      </div>
    ))}
  </div>
);

export const LineChartSkeleton: React.FC<{ height?: number }> = ({ height = 220 }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <Skeleton className="h-4 w-56 mb-3" />
    <div className="relative" style={{ height }}>
      {/* Имитация осей */}
      <div className="absolute inset-0 flex flex-col justify-between py-1">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="border-t border-dashed border-slate-100 dark:border-slate-700/60" />
        ))}
      </div>
      {/* Линия — несколько соединённых сегментов разной высоты */}
      <svg className="absolute inset-0 w-full h-full" viewBox="0 0 200 100" preserveAspectRatio="none">
        <polyline
          points="0,70 30,55 60,65 90,40 120,50 150,30 180,35 200,20"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
          className="text-slate-300 dark:text-slate-600 animate-pulse"
        />
      </svg>
    </div>
  </div>
);

export const DiscountsCardSkeleton: React.FC = () => (
  <div className="p-4 bg-emerald-50/30 dark:bg-emerald-900/10 rounded-xl border border-emerald-200/60 dark:border-emerald-800/30 shadow-sm flex flex-col gap-3">
    <Skeleton className="h-4 w-40" />
    {/* перцентили */}
    <div className="grid grid-cols-3 gap-2">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="p-3 rounded-lg bg-white/60 dark:bg-slate-800/60 text-center">
          <Skeleton className="h-2.5 w-12 mx-auto mb-1.5" />
          <Skeleton className="h-5 w-16 mx-auto" />
        </div>
      ))}
    </div>
    {/* блок "сэкономлено" */}
    <div className="rounded-lg p-3 bg-white/60 dark:bg-slate-800/60 flex items-center gap-3">
      <Skeleton className="w-9 h-9 rounded-full shrink-0" />
      <div className="flex-1 space-y-1.5">
        <Skeleton className="h-2.5 w-32" />
        <Skeleton className="h-5 w-28" />
      </div>
    </div>
    {/* конверсия */}
    <div>
      <div className="flex justify-between mb-1.5">
        <Skeleton className="h-3 w-48" />
        <Skeleton className="h-3 w-10" />
      </div>
      <Skeleton className="h-1.5 w-full rounded-full" />
    </div>
    <Skeleton className="h-3 w-64" />
  </div>
);

/** Скелетон для SectorsCard — горизонтальные бары убывающей длины.
 *  Высота ~360px чтобы совпадать с реальной карточкой. */
const SECTOR_BAR_PCT = [92, 78, 64, 56, 48, 41, 36, 30, 26, 22];
export const SectorsCardSkeleton: React.FC = () => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <div className="flex items-center justify-between mb-3">
      <Skeleton className="h-4 w-64" />
      <Skeleton className="h-7 w-32" />
    </div>
    <div className="space-y-2.5 py-2">
      {SECTOR_BAR_PCT.map((pct, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-4 w-44 shrink-0" />
          <div className="flex-1 h-7 bg-slate-100 dark:bg-slate-700/40 rounded">
            <div className="h-full bg-slate-200 dark:bg-slate-700/70 rounded animate-pulse"
                 style={{ width: `${pct}%` }} />
          </div>
          <Skeleton className="h-3 w-10 shrink-0" />
        </div>
      ))}
    </div>
  </div>
);

/** Скелетон для SectorItemsCard — список карточек с рангом, кодом, текстом и
 *  тонкой полосой прогресса. Должен визуально совпадать с реальными строками. */
export const SectorItemsCardSkeleton: React.FC<{ rows?: number }> = ({ rows = 6 }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <div className="flex items-center justify-between mb-3">
      <Skeleton className="h-4 w-72" />
      <Skeleton className="h-7 w-44" />
    </div>
    <div className="divide-y divide-slate-100 dark:divide-slate-700/60">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="py-3 flex gap-3">
          <Skeleton className="w-9 h-9 rounded-lg shrink-0" />
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex gap-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 flex-1 max-w-md" />
            </div>
            <div className="flex items-center gap-2">
              <Skeleton className="h-1.5 flex-1 rounded-full" />
              <Skeleton className="h-3 w-12" />
            </div>
            <Skeleton className="h-3 w-40" />
          </div>
        </div>
      ))}
    </div>
  </div>
);

export const TopTableSkeleton: React.FC<{ rows?: number; title?: string }> = ({ rows = 8 }) => (
  <div className="p-4 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
    <Skeleton className="h-4 w-40 mb-3" />
    <table className="w-full">
      <thead>
        <tr>
          <th className="text-left pb-2"><Skeleton className="h-3 w-20" /></th>
          <th className="text-right pb-2"><Skeleton className="h-3 w-12 ml-auto" /></th>
          <th className="text-right pb-2"><Skeleton className="h-3 w-16 ml-auto" /></th>
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: rows }).map((_, i) => (
          <tr key={i} className="border-b border-slate-100 dark:border-slate-800">
            <td className="py-1.5 pr-2">
              <Skeleton className="h-3.5 w-48 mb-1" />
              <Skeleton className="h-2.5 w-20" />
            </td>
            <td className="py-1.5"><Skeleton className="h-3 w-8 ml-auto" /></td>
            <td className="py-1.5"><Skeleton className="h-3.5 w-20 ml-auto" /></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
