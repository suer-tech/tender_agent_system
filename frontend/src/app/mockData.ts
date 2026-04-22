import { ChatSession, Tender } from './types';

export const generateMockTenders = (query: string): Tender[] => [
  {
    id: `tnd-${Math.random().toString(36).substr(2, 9)}`,
    title: `Разработка государственной информационной системы (ГИС) на базе отечественного ПО для нужд министерства`,
    category: '44-ФЗ',
    amount: 145000000,
    startDate: '2026-04-10',
    endDate: '2026-05-01',
    score: 96,
    description: 'Требуется разработка высоконагруженной системы с интеграцией через СМЭВ. Обязательное условие - наличие в реестре отечественного ПО.',
    details: {
      requirements: 'Опыт разработки федеральных систем, наличие допусков ФСТЭК.',
      mandatory: 'Отечественный стек (PostgresPro, Astra Linux).',
      qualification: 'Не менее 3 аналогичных завершенных контрактов за последние 5 лет.',
      technologies: 'Java/Go, PostgreSQL, React/Vue, Kubernetes.',
      risks: 'Высокие штрафные санкции за срыв сроков. Сложный процесс согласования архитектуры.',
      aiComment: 'Отличный тендер, идеально подходит под ваш профиль. Высокий скоринг обусловлен точным совпадением стека технологий.',
    }
  },
  {
    id: `tnd-${Math.random().toString(36).substr(2, 9)}`,
    title: `Создание и внедрение корпоративного портала с использованием микросервисной архитектуры`,
    category: '223-ФЗ',
    amount: 32000000,
    startDate: '2026-04-15',
    endDate: '2026-05-10',
    score: 84,
    description: 'Разработка интранет-портала для 10,000+ сотрудников госкорпорации с модулями обучения и оценки персонала.',
    details: {
      requirements: 'Интеграция с Active Directory, 1C:ЗУП. Разработка мобильного приложения.',
      mandatory: 'Обеспечение отказоустойчивости 99.9%.',
      qualification: 'Штат разработчиков не менее 50 человек.',
      technologies: 'Node.js, React Native, MongoDB, Redis.',
      risks: 'Размытые требования к UI/UX, возможен scope creep.',
      aiComment: 'Хороший вариант, но обратите внимание на требования к интеграции с 1С - у нас в портфолио мало таких кейсов.',
    }
  },
  {
    id: `tnd-${Math.random().toString(36).substr(2, 9)}`,
    title: `Услуги по заказной разработке веб-приложений (Outstaffing)`,
    category: 'Коммерческий',
    amount: 15000000,
    startDate: '2026-04-16',
    endDate: '2026-04-30',
    score: 72,
    description: 'Предоставление выделенных команд разработчиков (frontend, backend, QA) для проектов банка.',
    details: {
      requirements: 'Middle+ и Senior специалисты с опытом работы в финтехе.',
      mandatory: 'Прохождение технического интервью каждым кандидатом.',
      qualification: 'Аккредитация IT-компании.',
      technologies: 'React, TypeScript, Java Spring Boot.',
      risks: 'Риск невыхода кандидатов, долгий процесс онбординга.',
      aiComment: 'Скоринг снижен из-за формата outstaff, вы искали преимущественно проекты под ключ (fixed price).',
    }
  }
];

export const initialSessions: ChatSession[] = [
  {
    id: 'session-1',
    title: 'Разработка ГИС',
    createdAt: '2026-04-16T10:00:00Z',
    messages: [
      { id: 'm1', role: 'user', content: 'Найди тендеры на разработку информацио��ных систем для госсектора', timestamp: '2026-04-16T10:00:00Z' },
      { id: 'm2', role: 'agent', content: 'Я нашел несколько подходящих тендеров по вашему запросу. Обратите внимание на первый — он имеет самое высокое совпадение по технологиям.', timestamp: '2026-04-16T10:00:05Z' }
    ],
    tenders: generateMockTenders('ГИС')
  },
  {
    id: 'session-2',
    title: 'Мобильные приложения',
    createdAt: '2026-04-15T14:30:00Z',
    messages: [
      { id: 'm1', role: 'user', content: 'Ищу тендеры на создание мобильных приложений (React Native)', timestamp: '2026-04-15T14:30:00Z' },
      { id: 'm2', role: 'agent', content: 'Поиск завершен. Найдено 2 релевантных тендера, но конкуренция по ним довольно высокая.', timestamp: '2026-04-15T14:30:08Z' }
    ],
    tenders: [generateMockTenders('Моб')[1]] // Just use one from the mock generator for variety
  }
];
