import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router';
import { motion, AnimatePresence } from 'motion/react';
import { MessageSquarePlus, History, Search, ChevronLeft, ChevronRight, Hash, Sun, Moon, MoreHorizontal, Trash2, BarChart3 } from 'lucide-react';
import { ChatSession } from '../types';
import { useTheme } from 'next-themes';

interface SidebarLeftProps {
  isOpen: boolean;
  onToggle: () => void;
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string) => void;
}

export const SidebarLeft: React.FC<SidebarLeftProps> = ({
  isOpen,
  onToggle,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}) => {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMounted(true); }, []);

  // Close menu on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    if (menuOpenId) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpenId]);

  return (
    <div
      className={`h-full bg-slate-900 dark:bg-slate-950 border-r border-slate-800 dark:border-slate-900 flex flex-col transition-all duration-300 z-20 text-slate-300 shadow-xl ${
        isOpen ? 'w-72' : 'w-16'
      }`}
    >
      {/* Header */}
      <div className="p-4 flex items-center justify-between border-b border-slate-800/50 dark:border-slate-800">
        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              className="flex items-center gap-2 overflow-hidden whitespace-nowrap"
            >
              <Search className="w-5 h-5 text-indigo-400" />
              <span className="font-bold text-white tracking-wide">TenderAI</span>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="flex items-center gap-1">
          {mounted && isOpen && (
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-amber-300 dark:hover:text-indigo-300 transition-colors"
              title="Сменить тему"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          )}
          <button
            onClick={onToggle}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors border border-transparent hover:border-slate-700"
            title={isOpen ? "Свернуть панель" : "Развернуть панель"}
          >
            {isOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          className={`flex items-center justify-center gap-2 w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-all shadow-md shadow-indigo-900/20 ${
            !isOpen ? 'px-0' : 'px-4'
          }`}
          title="Новый поиск"
        >
          <MessageSquarePlus className="w-5 h-5" />
          {isOpen && <span>Новый поиск</span>}
        </button>
        <Link
          to="/market"
          className={`mt-2 flex items-center justify-center gap-2 w-full py-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-medium transition-all ${
            !isOpen ? 'px-0' : 'px-4'
          }`}
          title="Аналитика рынка"
        >
          <BarChart3 className="w-5 h-5" />
          {isOpen && <span>Аналитика рынка</span>}
        </Link>
      </div>

      {/* History List */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar py-2">
        <div className="px-3 mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
          <History className="w-3.5 h-3.5" />
          {isOpen && <span>История поисков</span>}
        </div>

        <div className="space-y-0.5 px-2">
          {sessions.map((session) => {
            const isActive = activeSessionId === session.id;
            const isMenuOpen = menuOpenId === session.id;

            return (
              <div key={session.id} className="relative group">
                <button
                  onClick={() => onSelectSession(session.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-left ${
                    isActive
                      ? 'bg-slate-800 text-white font-medium'
                      : 'hover:bg-slate-800/50 text-slate-400 hover:text-slate-200'
                  }`}
                  title={session.title}
                >
                  <Hash className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-indigo-400' : 'text-slate-600'}`} />
                  {isOpen && (
                    <span className="truncate flex-1 text-sm">{session.title}</span>
                  )}
                </button>

                {/* Three-dot menu */}
                {isOpen && (
                  <div className={`absolute right-2 top-1/2 -translate-y-1/2 ${isMenuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity`}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(isMenuOpen ? null : session.id);
                      }}
                      className="p-1 rounded-md hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      <MoreHorizontal className="w-4 h-4" />
                    </button>

                    {/* Dropdown */}
                    {isMenuOpen && (
                      <div
                        ref={menuRef}
                        className="absolute right-0 top-full mt-1 w-40 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 py-1 overflow-hidden"
                      >
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(null);
                            onDeleteSession(session.id);
                          }}
                          className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors text-left"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Удалить
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
