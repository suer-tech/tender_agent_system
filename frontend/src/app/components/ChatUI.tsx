import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, Search } from 'lucide-react';
import { Message } from '../types';

interface ChatUIProps {
  messages: Message[];
  onSendMessage: (text: string) => void;
  isSearching: boolean;
  statusText?: string;
  centered?: boolean;
}

export const ChatUI: React.FC<ChatUIProps> = ({ messages, onSendMessage, isSearching, statusText, centered = false }) => {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const hasMessages = messages.length > 0 || isSearching;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isSearching, statusText]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isSearching) return;
    onSendMessage(input.trim());
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const formatContent = (text: string) => {
    return text.split('\n').map((line, i) => (
      <span key={i}>
        {line}
        {i < text.split('\n').length - 1 && <br />}
      </span>
    ));
  };

  // =============================================
  // EMPTY STATE (centered): input in the middle
  // =============================================
  if (!hasMessages && centered) {
    return (
      <div className="flex flex-col h-full w-full">
        {/* Spacer — pushes content to vertical center */}
        <div className="flex-1" />

        <div className="w-full max-w-2xl mx-auto px-6 flex flex-col items-center">
          {/* Icon */}
          <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center text-indigo-500 dark:text-indigo-400 mb-5">
            <Search className="w-6 h-6" />
          </div>

          <h1 className="text-2xl font-semibold text-slate-800 dark:text-white mb-8 text-center">
            Что будем искать?
          </h1>

          {/* Input field */}
          <form onSubmit={handleSubmit} className="w-full relative flex items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Опишите, какие тендеры вас интересуют..."
              rows={1}
              className="w-full bg-slate-100 dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 rounded-2xl py-4 pl-5 pr-14 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:bg-white dark:focus:bg-slate-800 transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 resize-none text-base leading-normal"
              disabled={isSearching}
            />
            <button
              type="submit"
              disabled={!input.trim() || isSearching}
              className="absolute right-3 bottom-1/2 translate-y-1/2 p-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-30 transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>

        {/* Spacer + hint at the bottom */}
        <div className="flex-1 flex flex-col justify-end items-center pb-8">
          <p className="text-sm text-slate-400 dark:text-slate-500 text-center max-w-lg mt-6 leading-relaxed">
            Например: «Ремонт дорог в Московской области» · «Поставка медоборудования» · «Внедрение ИИ» · «Клининговые услуги» · «Строительство школы»
          </p>
        </div>
      </div>
    );
  }

  // =============================================
  // CHAT MODE: messages top, input bottom
  // =============================================
  return (
    <div className={`flex flex-col h-full w-full ${!centered ? 'border-l border-slate-200/50 dark:border-slate-800/50' : ''}`}>
      {/* Sidebar header — only in sidebar mode */}
      {!centered && (
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-100 dark:border-slate-800/60 flex-shrink-0">
          <div className="w-7 h-7 rounded-full bg-indigo-100 dark:bg-indigo-900/40 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
            <Bot className="w-3.5 h-3.5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-tight">ИИ-агент</h2>
            <p className="text-[11px] text-emerald-500 dark:text-emerald-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block animate-pulse" />
              Онлайн
            </p>
          </div>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className={`${centered ? 'max-w-3xl mx-auto pt-16' : ''} px-5 py-6 space-y-5`}>
          {messages.map((msg) => (
            <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role !== 'user' && (
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center text-indigo-500 dark:text-indigo-400 mt-0.5">
                  <Bot className="w-3.5 h-3.5" />
                </div>
              )}
              <div className={`max-w-[80%] text-[15px] leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 rounded-2xl rounded-tr-md px-4 py-3'
                  : 'text-slate-700 dark:text-slate-300 pt-1'
              }`}>
                {formatContent(msg.content)}
              </div>
              {msg.role === 'user' && (
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-slate-700 dark:bg-slate-600 flex items-center justify-center text-white mt-0.5">
                  <User className="w-3.5 h-3.5" />
                </div>
              )}
            </div>
          ))}

          {isSearching && (
            <div className="flex gap-3 justify-start">
              <div className="flex-shrink-0 w-7 h-7 rounded-full bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center text-indigo-500 dark:text-indigo-400 mt-0.5">
                <Bot className="w-3.5 h-3.5" />
              </div>
              <div className="text-[15px] text-slate-400 dark:text-slate-500 flex items-center gap-2.5 pt-1">
                <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
                <span>{statusText || 'Думаю...'}</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input at bottom */}
      <div className={`px-5 pb-5 pt-2 flex-shrink-0 ${centered ? 'max-w-3xl mx-auto w-full' : ''}`}>
        <form onSubmit={handleSubmit} className="relative flex items-end">
          <textarea
            ref={!centered ? inputRef : undefined}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={centered ? "Задайте вопрос..." : "Сообщение..."}
            rows={1}
            className="w-full bg-slate-100 dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 rounded-2xl py-3 pl-5 pr-12 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:bg-white dark:focus:bg-slate-800 transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 resize-none text-[15px] leading-normal"
            disabled={isSearching}
          />
          <button
            type="submit"
            disabled={!input.trim() || isSearching}
            className="absolute right-2.5 bottom-1/2 translate-y-1/2 p-2 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 disabled:opacity-30 transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
        {centered && (
          <p className="text-xs text-slate-400 dark:text-slate-500 text-center mt-2.5">
            Enter — отправить · Shift+Enter — новая строка
          </p>
        )}
      </div>
    </div>
  );
};
