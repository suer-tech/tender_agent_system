import React from 'react';
import { useNavigate } from 'react-router';
import { motion, AnimatePresence } from 'motion/react';
import { CheckCircle2, Info, XCircle, X } from 'lucide-react';
import { useAppState } from '../store';

const ICONS = {
  success: <CheckCircle2 className="w-5 h-5 text-emerald-500" />,
  info: <Info className="w-5 h-5 text-indigo-500" />,
  error: <XCircle className="w-5 h-5 text-rose-500" />,
};

const BG = {
  success: 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800/50',
  info: 'bg-indigo-50 dark:bg-indigo-950/40 border-indigo-200 dark:border-indigo-800/50',
  error: 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-800/50',
};


export const ToastContainer: React.FC = () => {
  const { toasts, dismissToast, selectSession } = useAppState();
  const navigate = useNavigate();

  return (
    <div className="fixed bottom-6 right-6 z-[1000] flex flex-col gap-2 w-80 max-w-[calc(100vw-3rem)] pointer-events-none">
      <AnimatePresence>
        {toasts.map(t => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, x: 400, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 400, scale: 0.95 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className={`rounded-xl border shadow-lg backdrop-blur-sm p-4 pointer-events-auto cursor-pointer hover:scale-[1.01] transition-transform ${BG[t.type]}`}
            onClick={() => {
              if (t.sessionId) {
                selectSession(t.sessionId);
                navigate('/');
              }
              dismissToast(t.id);
            }}
          >
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 mt-0.5">{ICONS[t.type]}</div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 dark:text-slate-100 text-sm">{t.title}</div>
                {t.body && <div className="text-xs text-slate-600 dark:text-slate-400 mt-0.5">{t.body}</div>}
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); dismissToast(t.id); }}
                className="flex-shrink-0 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
};
