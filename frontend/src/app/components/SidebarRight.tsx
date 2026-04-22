import React from 'react';
import { ChevronRight, MessageCircle, MoreVertical } from 'lucide-react';
import { ChatUI } from './ChatUI';
import { Message } from '../types';

interface SidebarRightProps {
  isOpen: boolean;
  onToggle: () => void;
  messages: Message[];
  onSendMessage: (text: string) => void;
  isSearching: boolean;
  statusText?: string;
  hasTenders: boolean;
}

export const SidebarRight: React.FC<SidebarRightProps> = ({
  isOpen,
  onToggle,
  messages,
  onSendMessage,
  isSearching,
  statusText,
  hasTenders,
}) => {
  if (!hasTenders) return null;

  return (
    <div
      className={`h-full bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 flex flex-col transition-all duration-300 z-10 shadow-xl ${
        isOpen ? 'w-[480px]' : 'w-16'
      }`}
    >
      {!isOpen ? (
        <div className="flex flex-col items-center py-4 h-full border-l border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
          <button
            onClick={onToggle}
            className="p-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm text-indigo-600 dark:text-indigo-400 rounded-xl hover:bg-indigo-50 dark:hover:bg-indigo-900/30 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            title="Открыть чат"
          >
            <MessageCircle className="w-6 h-6" />
          </button>
          
          <div className="mt-8 flex-1 flex flex-col items-center gap-4 text-slate-400 dark:text-slate-600">
             <div className="w-1 h-1 rounded-full bg-slate-300 dark:bg-slate-600"></div>
             <div className="w-1 h-1 rounded-full bg-slate-300 dark:bg-slate-600"></div>
             <div className="w-1 h-1 rounded-full bg-slate-300 dark:bg-slate-600"></div>
          </div>
          
          <button className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors mt-auto mb-4">
            <MoreVertical className="w-5 h-5" />
          </button>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between p-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <div className="flex items-center gap-2 text-slate-800 dark:text-slate-100 font-semibold px-2">
              <MessageCircle className="w-5 h-5 text-indigo-500 dark:text-indigo-400" />
              <span>Диалог с агентом</span>
            </div>
            <button
              onClick={onToggle}
              className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="Свернуть чат"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <ChatUI
              messages={messages}
              onSendMessage={onSendMessage}
              isSearching={isSearching}
              statusText={statusText}
              centered={false}
            />
          </div>
        </>
      )}
    </div>
  );
};
