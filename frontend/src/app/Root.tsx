import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Tender } from './types';
import { SidebarLeft } from './components/SidebarLeft';
import { SidebarRight } from './components/SidebarRight';
import { ChatUI } from './components/ChatUI';
import { TenderCard } from './components/TenderCard';
import { useAppState } from './store';


export const Root: React.FC = () => {
  const {
    sessions, activeSession, activeSessionId,
    isSearching, statusText,
    sendMessage, newChat, selectSession, deleteSession, discussTender,
  } = useAppState();

  // На мобильных (ширина < 768px, Tailwind md) левую панель скрываем по умолчанию.
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  const [isLeftSidebarOpen, setIsLeftSidebarOpen] = useState(!isMobile);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(!isMobile);

  const hasTenders = !!(activeSession && activeSession.tenders.length > 0);

  const handleDiscussTender = (tender: Tender) => {
    if (!isRightSidebarOpen) setIsRightSidebarOpen(true);
    discussTender(tender);
  };

  return (
    <div className="flex h-screen w-screen bg-slate-50 dark:bg-slate-950 overflow-hidden font-sans text-slate-900 dark:text-slate-100 selection:bg-indigo-100 dark:selection:bg-indigo-900/50 selection:text-indigo-900 dark:selection:text-indigo-100">
      <SidebarLeft
        isOpen={isLeftSidebarOpen}
        onToggle={() => setIsLeftSidebarOpen(!isLeftSidebarOpen)}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={selectSession}
        onNewChat={newChat}
        onDeleteSession={deleteSession}
      />

      <div className="flex-1 overflow-hidden flex flex-col relative z-0">
        <AnimatePresence mode="wait">
          {!hasTenders ? (
            <motion.div
              key="center-chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              className="flex-1 flex flex-col bg-white dark:bg-slate-900"
            >
              <ChatUI
                messages={activeSession?.messages || []}
                onSendMessage={sendMessage}
                isSearching={isSearching}
                statusText={statusText}
                centered={true}
              />
            </motion.div>
          ) : (
            <motion.div
              key="tenders-grid"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 overflow-y-auto p-6 md:p-8 bg-slate-50 dark:bg-slate-950 custom-scrollbar"
            >
              <div className="max-w-7xl mx-auto">
                <header className="mb-8 flex items-center justify-between">
                  <div>
                    <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">Результаты поиска</h1>
                    <p className="text-slate-500 dark:text-slate-400 mt-2 font-medium">
                      Найдено {activeSession!.tenders.length} тендеров
                      {activeSession!.tenders.filter(t => t.score >= 70).length > 0 &&
                        ` · ${activeSession!.tenders.filter(t => t.score >= 70).length} релевантных`
                      }
                    </p>
                  </div>
                </header>

                <div className="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-6 items-start">
                  {activeSession!.tenders.map((tender, index) => (
                    <motion.div
                      key={tender.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.4, delay: index * 0.08 }}
                    >
                      <TenderCard tender={tender} onDiscuss={handleDiscussTender} />
                    </motion.div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <SidebarRight
        isOpen={isRightSidebarOpen}
        onToggle={() => setIsRightSidebarOpen(!isRightSidebarOpen)}
        messages={activeSession?.messages || []}
        onSendMessage={sendMessage}
        isSearching={isSearching}
        statusText={statusText}
        hasTenders={hasTenders}
      />

      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background-color: rgba(148, 163, 184, 0.3); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background-color: rgba(148, 163, 184, 0.5); }
        html.dark .custom-scrollbar::-webkit-scrollbar-thumb { background-color: rgba(148, 163, 184, 0.2); }
        html.dark .custom-scrollbar::-webkit-scrollbar-thumb:hover { background-color: rgba(148, 163, 184, 0.4); }
      `}} />
    </div>
  );
};
