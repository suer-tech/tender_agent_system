import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { ChatSession, Message, Tender, Category } from './types';

// ============ mapping helpers (переехали из Root) ============

function mapCategory(lawType: string): Category {
  if (lawType?.includes('44')) return '44-ФЗ';
  if (lawType?.includes('223')) return '223-ФЗ';
  if (lawType?.toLowerCase().includes('коммерч')) return 'Коммерческий';
  return 'Коммерческий';
}

function parseAmount(price: string): number {
  if (!price) return 0;
  const nums = price.replace(/[^\d.,]/g, '').replace(',', '.');
  return parseFloat(nums) || 0;
}

function mapTender(t: any): Tender {
  return {
    id: t.id || t.external_id || '',
    title: t.title || 'Без названия',
    category: mapCategory(t.law_type || ''),
    amount: parseAmount(t.price || ''),
    startDate: t.start_date || '',
    endDate: t.deadline || t.deadline_info || '',
    score: Math.round((t.score || 0) * 10),
    description: t.summary || t.description || '',
    url: t.url || '',
    docStatus: t.doc_status || '',
    docCount: t.doc_count || 0,
    details: {
      requirements: (t.key_requirements || []).join('\n') || '',
      mandatory: (t.mandatory_conditions || []).join('\n') || '',
      qualification: t.qualification || '',
      technologies: t.tech_stack || '',
      risks: t.risks || '',
      aiComment: t.recommendation || '',
    },
    okpd2Guess: t.okpd2_guess || null,
    priceContext: t.price_context || null,
    customerRisk: t.customer_risk || null,
  };
}

const STORAGE_KEY = 'tender-sessions-v1';
const ACTIVE_KEY = 'tender-active-session-v1';

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {}
  return [{
    id: `session-${Date.now()}`,
    title: 'Новый поиск',
    messages: [],
    tenders: [],
    createdAt: new Date().toISOString(),
  }];
}

function loadActiveId(sessions: ChatSession[]): string {
  try {
    const id = localStorage.getItem(ACTIVE_KEY);
    if (id && sessions.some(s => s.id === id)) return id;
  } catch {}
  return sessions[0].id;
}

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;


// ============ Notifications ============

export interface Toast {
  id: string;
  type: 'success' | 'info' | 'error';
  title: string;
  body?: string;
  sessionId?: string;   // если клик по toast должен увести в этот чат
  createdAt: number;
}

// ============ Context type ============

interface AppState {
  sessions: ChatSession[];
  activeSessionId: string;
  activeSession: ChatSession | null;
  isSearching: boolean;
  statusText: string;
  toasts: Toast[];
  // actions
  sendMessage: (text: string) => void;
  newChat: () => void;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => void;
  discussTender: (tender: Tender) => void;
  dismissToast: (id: string) => void;
}

const AppContext = createContext<AppState | null>(null);

export function useAppState(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppState must be used inside <AppStateProvider>');
  return ctx;
}


// ============ Provider ============

export const AppStateProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [sessions, setSessions] = useState<ChatSession[]>(() => loadSessions());
  const [activeSessionId, setActiveSessionId] = useState<string>(() => loadActiveId(loadSessions()));
  const [isSearching, setIsSearching] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [toasts, setToasts] = useState<Toast[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef(activeSessionId);
  useEffect(() => { sessionIdRef.current = activeSessionId; }, [activeSessionId]);

  // persist
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions)); } catch {}
  }, [sessions]);
  useEffect(() => {
    try { localStorage.setItem(ACTIVE_KEY, activeSessionId); } catch {}
  }, [activeSessionId]);

  const pushToast = useCallback((toast: Omit<Toast, 'id' | 'createdAt'>) => {
    const t: Toast = { ...toast, id: `t-${Date.now()}-${Math.random()}`, createdAt: Date.now() };
    setToasts(prev => [...prev, t]);
    // auto-dismiss через 8 сек
    setTimeout(() => setToasts(prev => prev.filter(x => x.id !== t.id)), 8000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // --- WebSocket ---
  const connectWs = useCallback((sid: string) => {
    try { wsRef.current?.close(); } catch {}
    const ws = new WebSocket(`${WS_URL}/${sid}`);
    wsRef.current = ws;

    ws.onopen = () => console.log('[ws] connected', sid);
    ws.onclose = () => {
      console.log('[ws] disconnected', sid);
      setTimeout(() => {
        if (sessionIdRef.current === sid) connectWs(sid);
      }, 3000);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const currentSid = sessionIdRef.current;

      switch (data.type) {
        case 'message': {
          const msg: Message = {
            id: `m-${Date.now()}-${Math.random()}`,
            role: data.role === 'user' ? 'user' : 'agent',
            content: data.content || '',
            timestamp: new Date().toISOString(),
          };
          setSessions(prev => prev.map(s =>
            s.id === currentSid ? { ...s, messages: [...s.messages, msg] } : s
          ));
          setIsSearching(false);
          setStatusText('');
          break;
        }
        case 'thinking':
          setIsSearching(!!data.active);
          if (!data.active) setStatusText('');
          break;
        case 'status':
          if (data.text) {
            setStatusText(data.text);
            setIsSearching(true);
          } else {
            setStatusText('');
          }
          break;
        case 'tenders': {
          const tenders: Tender[] = (data.data || []).map(mapTender);
          setSessions(prev => prev.map(s =>
            s.id === currentSid ? { ...s, tenders } : s
          ));
          setIsSearching(false);
          setStatusText('');
          // Toast если пользователь не на главной
          if (window.location.pathname !== '/') {
            pushToast({
              type: 'success',
              title: `Найдено ${tenders.length} тендеров`,
              body: tenders.filter(t => t.score >= 70).length > 0
                ? `${tenders.filter(t => t.score >= 70).length} с высокой релевантностью — нажми, чтобы открыть чат`
                : 'Нажми чтобы вернуться к чату',
              sessionId: currentSid,
            });
          }
          break;
        }
        case 'session_title': {
          const title = data.title || '';
          if (title) {
            setSessions(prev => prev.map(s =>
              s.id === currentSid ? { ...s, title } : s
            ));
          }
          break;
        }
      }
    };
  }, [pushToast]);

  // Держим WS живым на весь жизненный цикл AppStateProvider
  useEffect(() => {
    connectWs(activeSessionId);
    return () => { try { wsRef.current?.close(); } catch {} };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Пересоединиться когда меняется активная сессия
  useEffect(() => {
    if (sessionIdRef.current === activeSessionId && wsRef.current?.readyState === WebSocket.OPEN) {
      // уже подключены к правильному
    }
    if (wsRef.current) {
      const currentUrl = wsRef.current.url;
      if (!currentUrl.endsWith(`/${activeSessionId}`)) {
        connectWs(activeSessionId);
      }
    }
  }, [activeSessionId, connectWs]);

  // --- actions ---

  const sendMessage = useCallback((text: string) => {
    let currentSid = activeSessionId;
    if (!currentSid) {
      const newSid = `session-${Date.now()}`;
      setSessions(prev => [{
        id: newSid, title: 'Новый поиск', messages: [], tenders: [],
        createdAt: new Date().toISOString(),
      }, ...prev]);
      currentSid = newSid;
      setActiveSessionId(newSid);
    }

    const userMsg: Message = {
      id: `m-${Date.now()}`, role: 'user', content: text,
      timestamp: new Date().toISOString(),
    };
    setSessions(prev => prev.map(s =>
      s.id === currentSid
        ? {
            ...s,
            title: s.messages.length === 0
              ? (text.length > 25 ? text.substring(0, 25) + '...' : text)
              : s.title,
            messages: [...s.messages, userMsg],
          }
        : s
    ));

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ message: text }));
    }
  }, [activeSessionId]);

  const newChat = useCallback(() => {
    const newSid = `session-${Date.now()}`;
    setSessions(prev => [{
      id: newSid, title: 'Новый поиск', messages: [], tenders: [],
      createdAt: new Date().toISOString(),
    }, ...prev]);
    setActiveSessionId(newSid);
    setIsSearching(false);
    setStatusText('');
  }, []);

  const selectSession = useCallback((id: string) => {
    setActiveSessionId(id);
    setIsSearching(false);
    setStatusText('');
  }, []);

  const deleteSession = useCallback((id: string) => {
    setSessions(prev => {
      const filtered = prev.filter(s => s.id !== id);
      if (id === activeSessionId) {
        if (filtered.length > 0) setActiveSessionId(filtered[0].id);
        else {
          const newSid = `session-${Date.now()}`;
          filtered.push({
            id: newSid, title: 'Новый поиск', messages: [], tenders: [],
            createdAt: new Date().toISOString(),
          });
          setActiveSessionId(newSid);
        }
      }
      return filtered;
    });
  }, [activeSessionId]);

  const discussTender = useCallback((tender: Tender) => {
    const msg = `Расскажи подробнее про тендер "${tender.title}" (${tender.category}). Какие обязательные условия? Стоит ли участвовать?`;
    sendMessage(msg);
  }, [sendMessage]);

  const activeSession = sessions.find(s => s.id === activeSessionId) || null;

  const value: AppState = {
    sessions, activeSessionId, activeSession,
    isSearching, statusText, toasts,
    sendMessage, newChat, selectSession, deleteSession, discussTender,
    dismissToast,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};
