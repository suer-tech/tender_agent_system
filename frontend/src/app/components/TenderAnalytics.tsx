import React from 'react';
import { TrendingDown, Building2, AlertOctagon, Info, Tag } from 'lucide-react';
import { Okpd2Guess, PriceContext, CustomerRisk } from '../types';

interface Props {
  okpd2?: Okpd2Guess | null;
  priceContext?: PriceContext | null;
  customerRisk?: CustomerRisk | null;
}

const formatMln = (v: number | null | undefined) =>
  v == null ? '—' : v >= 1_000_000
    ? `${(v / 1_000_000).toFixed(1)} млн ₽`
    : `${Math.round(v).toLocaleString('ru-RU')} ₽`;

const formatPct = (v: number | null | undefined) =>
  v == null ? '—' : `${v.toFixed(1)}%`;


export const TenderAnalytics: React.FC<Props> = ({ okpd2, priceContext, customerRisk }) => {
  // Если ничего нет — один серый блок с честным текстом.
  const nothing = !okpd2 && !priceContext && !customerRisk;
  if (nothing) {
    return (
      <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
        <Info className="w-4 h-4 flex-shrink-0" />
        <span>Аналитика недоступна — тендер не найден в витрине ЕИС, ОКПД2 не определён</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* ОКПД2 бейдж */}
      {okpd2 && (
        <div className="flex items-center gap-2 text-xs">
          <span className={`px-2 py-1 rounded-md flex items-center gap-1.5 border ${
            okpd2.source === 'exact'
              ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800/50'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700'
          }`}>
            <Tag className="w-3 h-3" />
            <span className="font-semibold">ОКПД2 {okpd2.code}</span>
            {okpd2.source === 'classified' && (
              <span className="opacity-70">~{Math.round(okpd2.confidence * 100)}%</span>
            )}
          </span>
          {okpd2.name && (
            <span className="text-slate-500 dark:text-slate-400 truncate" title={okpd2.name}>
              {okpd2.name}
            </span>
          )}
        </div>
      )}

      {/* Ценовой контекст */}
      {priceContext ? (
        <div className="p-3 bg-emerald-50/60 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800/40 rounded-xl text-xs">
          <div className="flex items-center gap-2 font-semibold text-emerald-700 dark:text-emerald-300 mb-1">
            <TrendingDown className="w-4 h-4" />
            Ценовой контекст (ЕИС, 12 мес)
          </div>
          <div className="grid grid-cols-3 gap-2 text-slate-700 dark:text-slate-300">
            <div>
              <div className="text-slate-400 dark:text-slate-500 mb-0.5">Выборка</div>
              <div className="font-semibold">{priceContext.sample_size}</div>
            </div>
            <div>
              <div className="text-slate-400 dark:text-slate-500 mb-0.5">Медиана скидки</div>
              <div className="font-semibold">{formatPct(priceContext.discount_pct_median)}</div>
            </div>
            <div>
              <div className="text-slate-400 dark:text-slate-500 mb-0.5">Медиана цены</div>
              <div className="font-semibold">{formatMln(priceContext.final_price_median)}</div>
            </div>
          </div>
          {priceContext.contracts_with_discount < 5 && (
            <div className="mt-1 text-slate-400 dark:text-slate-500">
              Скидка по {priceContext.contracts_with_discount} контрактам — оценочно
            </div>
          )}
        </div>
      ) : okpd2 ? (
        <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
          <Info className="w-4 h-4 flex-shrink-0" />
          <span>По ОКПД2 {okpd2.code} в нашей базе за 12 мес недостаточно контрактов для бенчмарка</span>
        </div>
      ) : null}

      {/* Риск-карточка заказчика */}
      {customerRisk ? (
        <div className={`p-3 rounded-xl text-xs border ${
          customerRisk.in_rnp
            ? 'bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800/40'
            : customerRisk.risk_score >= 30
              ? 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/40'
              : 'bg-slate-50 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700'
        }`}>
          <div className={`flex items-center gap-2 font-semibold mb-1 ${
            customerRisk.in_rnp
              ? 'text-rose-700 dark:text-rose-300'
              : customerRisk.risk_score >= 30
                ? 'text-amber-700 dark:text-amber-300'
                : 'text-slate-700 dark:text-slate-300'
          }`}>
            {customerRisk.in_rnp ? <AlertOctagon className="w-4 h-4" /> : <Building2 className="w-4 h-4" />}
            Заказчик · ИНН {customerRisk.inn}
          </div>
          {customerRisk.in_rnp && customerRisk.rnp_records[0] && (
            <div className="mb-2 p-2 bg-rose-100 dark:bg-rose-900/40 rounded text-rose-800 dark:text-rose-200">
              🚨 В реестре недобросовестных поставщиков с {customerRisk.rnp_records[0].publish_date.slice(0, 10)}.
              Причина: {customerRisk.rnp_records[0].create_reason}
            </div>
          )}
          <div className="grid grid-cols-4 gap-2 text-slate-700 dark:text-slate-300">
            <div>
              <div className="text-slate-400 dark:text-slate-500 mb-0.5">Контрактов</div>
              <div className="font-semibold">{customerRisk.contracts_as_customer}</div>
            </div>
            <div>
              <div className="text-slate-400 dark:text-slate-500 mb-0.5">Извещений</div>
              <div className="font-semibold">{customerRisk.notices_count}</div>
            </div>
            <div>
              <div className="text-slate-400 dark:text-slate-500 mb-0.5">Жалоб</div>
              <div className="font-semibold">{customerRisk.complaints_count}</div>
            </div>
            <div>
              <div className="text-slate-400 dark:text-slate-500 mb-0.5">Расторжений</div>
              <div className="font-semibold">{customerRisk.unilateral_refusals_count}</div>
            </div>
          </div>
          {customerRisk.risk_flags.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {customerRisk.risk_flags.map((flag, i) => (
                <span key={i} className="px-1.5 py-0.5 bg-white dark:bg-slate-700 rounded text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-600">
                  {flag}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
          <Info className="w-4 h-4 flex-shrink-0" />
          <span>Заказчик не встречался в нашей базе — недостаточно данных для анализа</span>
        </div>
      )}
    </div>
  );
};
