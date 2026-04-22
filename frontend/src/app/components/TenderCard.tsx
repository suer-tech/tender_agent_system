import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronDown, ExternalLink, MessageSquare, AlertTriangle, CheckCircle, Code, ShieldCheck, FileText, Bot } from 'lucide-react';
import { Tender } from '../types';
import { TenderAnalytics } from './TenderAnalytics';

interface TenderCardProps {
  tender: Tender;
  onDiscuss: (tender: Tender) => void;
}

export const TenderCard: React.FC<TenderCardProps> = ({ tender, onDiscuss }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value);
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case '44-ФЗ': return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800/50';
      case '223-ФЗ': return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/50';
      case '��оммерческий': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800/50';
      default: return 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 90) return 'text-emerald-500 dark:text-emerald-400';
    if (score >= 70) return 'text-amber-500 dark:text-amber-400';
    return 'text-rose-500 dark:text-rose-400';
  };

  const getScoreBgColor = (score: number) => {
    if (score >= 90) return 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800/50';
    if (score >= 70) return 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/50';
    return 'bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800/50';
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition-shadow duration-300 overflow-hidden flex flex-col h-full">
      <div className="p-6 flex flex-col flex-1">
        {/* Header */}
        <div className="flex justify-between items-start gap-4 mb-3">
          <span className={`px-3 py-1 rounded-full text-xs font-semibold border ${getCategoryColor(tender.category)}`}>
            {tender.category}
          </span>
          <div className={`flex items-center justify-center w-12 h-12 rounded-full border-4 ${getScoreBgColor(tender.score)}`}>
            <span className={`text-sm font-bold ${getScoreColor(tender.score)}`}>{tender.score}</span>
          </div>
        </div>

        {/* Title */}
        <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 leading-snug mb-4 line-clamp-2" title={tender.title}>
          {tender.title}
        </h3>

        {/* Amount */}
        <div className="mb-4">
          <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
            {formatCurrency(tender.amount).replace(',00', '')}
          </span>
        </div>

        {/* Dates & Short Desc */}
        <div className="flex flex-col gap-3 mb-6 flex-1 text-sm">
          <div className="flex justify-between items-center text-slate-500 dark:text-slate-400 border-b border-slate-100 dark:border-slate-700 pb-3">
            <div className="flex flex-col">
              <span className="text-xs uppercase tracking-wider font-semibold">Начало</span>
              <span className="font-medium text-slate-700 dark:text-slate-300">{tender.startDate}</span>
            </div>
            <div className="w-px h-8 bg-slate-200 dark:bg-slate-700 mx-4"></div>
            <div className="flex flex-col text-right">
              <span className="text-xs uppercase tracking-wider font-semibold">Окончание</span>
              <span className="font-medium text-slate-700 dark:text-slate-300">{tender.endDate}</span>
            </div>
          </div>
          <p className="text-slate-600 dark:text-slate-400 line-clamp-3">
            {tender.description}
          </p>
        </div>

        {/* Actions */}
        <div className="flex gap-2 mt-auto pt-4 relative" style={{ containerType: 'inline-size' }}>
          <style>{`
            @container (max-width: 360px) {
              .btn-text { display: none; }
              .action-btn { flex: 1 1 0% !important; padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
            }
          `}</style>
          {tender.url ? (
            <a href={tender.url} target="_blank" rel="noopener noreferrer" className="action-btn flex-1 flex items-center justify-center gap-2 py-2.5 px-4 bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-sm font-semibold border border-slate-200 dark:border-slate-600 transition-colors" title="Открыть на Bicotender">
              <ExternalLink className="w-4 h-4" />
              <span className="btn-text">Открыть</span>
            </a>
          ) : (
            <button className="action-btn flex-1 flex items-center justify-center gap-2 py-2.5 px-4 bg-slate-50 dark:bg-slate-700/50 text-slate-400 rounded-xl text-sm font-semibold border border-slate-200 dark:border-slate-600 cursor-not-allowed" disabled>
              <ExternalLink className="w-4 h-4" />
              <span className="btn-text">Нет ссылки</span>
            </button>
          )}
          
          <button 
            onClick={() => setIsExpanded(!isExpanded)}
            className={`flex-none flex items-center justify-center p-2.5 rounded-xl border transition-colors ${isExpanded ? 'bg-indigo-50 dark:bg-indigo-900/30 border-indigo-200 dark:border-indigo-800/50 text-indigo-700 dark:text-indigo-400' : 'bg-slate-50 dark:bg-slate-700/50 border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'}`}
            title="Подробнее"
          >
            <ChevronDown className={`w-5 h-5 transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`} />
          </button>

          <button 
            onClick={() => onDiscuss(tender)}
            className="action-btn flex items-center justify-center gap-2 py-2.5 px-5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold shadow-sm shadow-indigo-200 dark:shadow-none transition-all hover:shadow-md"
            title="Обсудить"
          >
            <MessageSquare className="w-4 h-4" />
            <span className="btn-text">Обсудить</span>
          </button>
        </div>
      </div>

      {/* Expanded Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="bg-slate-50 dark:bg-slate-900/50 border-t border-slate-200 dark:border-slate-700 overflow-hidden"
          >
            <div className="p-6 space-y-4 text-sm">
              {/* Аналитика из витрины ЕИС */}
              <TenderAnalytics
                okpd2={tender.okpd2Guess}
                priceContext={tender.priceContext}
                customerRisk={tender.customerRisk}
              />

              <div className="p-4 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm">
                <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200 mb-2">
                  <Bot className="w-5 h-5 text-indigo-500 dark:text-indigo-400" />
                  <span>Комментарий ИИ-агента</span>
                </div>
                <p className="text-slate-600 dark:text-slate-400">{tender.details.aiComment}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200 mb-1">
                    <FileText className="w-4 h-4 text-slate-400" /> Key reqs
                  </div>
                  <p className="text-slate-600 dark:text-slate-400">{tender.details.requirements}</p>
                </div>
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200 mb-1">
                    <CheckCircle className="w-4 h-4 text-slate-400" /> Обязательные условия
                  </div>
                  <p className="text-slate-600 dark:text-slate-400">{tender.details.mandatory}</p>
                </div>
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200 mb-1">
                    <ShieldCheck className="w-4 h-4 text-slate-400" /> Квалификация
                  </div>
                  <p className="text-slate-600 dark:text-slate-400">{tender.details.qualification}</p>
                </div>
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200 mb-1">
                    <Code className="w-4 h-4 text-slate-400" /> Технологии
                  </div>
                  <p className="text-slate-600 dark:text-slate-400">{tender.details.technologies}</p>
                </div>
              </div>

              <div className="mt-4 p-3 bg-rose-50/50 dark:bg-rose-900/10 border border-rose-100 dark:border-rose-900/50 rounded-lg">
                <div className="flex items-center gap-2 font-semibold text-rose-700 dark:text-rose-400 mb-1">
                  <AlertTriangle className="w-4 h-4" /> Риски
                </div>
                <p className="text-rose-600/90 dark:text-rose-300/90">{tender.details.risks}</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
