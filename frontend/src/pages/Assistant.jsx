import React, { useEffect, useRef, useState } from 'react';
import { chatAPI } from '../utils/api';
import Layout from '../components/Layout';

const SUGGESTIONS = [
  'How much did I spend this month?',
  'How can I save more money?',
  'What are my top spending categories?',
  'Am I on track for my savings goals?',
];

// Mirrors services/chat_advisor.py's SUPPORTED_LANGUAGES - used if the
// GET /api/chat/languages call fails (e.g. an older backend still
// running without this route) so the selector never silently shrinks.
const FALLBACK_LANGUAGES = [
  { code: 'auto', label: 'Auto-detect' },
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'mr', label: 'Marathi' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
  { code: 'bn', label: 'Bengali' },
  { code: 'gu', label: 'Gujarati' },
  { code: 'kn', label: 'Kannada' },
  { code: 'ml', label: 'Malayalam' },
  { code: 'pa', label: 'Punjabi' },
];
const LANGUAGE_STORAGE_KEY = 'ai_assistant_language';

/** Renders a chat message's text with basic markdown-ish formatting (bold, bullet lines) as plain HTML-free React nodes. */
const MessageText = ({ text }) => {
  const lines = text.split('\n');
  return (
    <>
      {lines.map((line, i) => {
        const trimmed = line.trim();
        const isBullet = trimmed.startsWith('- ') || trimmed.startsWith('• ');
        const content = isBullet ? trimmed.slice(2) : line;
        const parts = content.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
        const rendered = parts.map((part, j) =>
          part.startsWith('**') && part.endsWith('**')
            ? <strong key={j}>{part.slice(2, -2)}</strong>
            : <React.Fragment key={j}>{part}</React.Fragment>
        );
        return (
          <p key={i} className={isBullet ? 'flex gap-1.5' : ''}>
            {isBullet && <span className="text-indigo-400">•</span>}
            <span>{rendered}</span>
          </p>
        );
      })}
    </>
  );
};

const AssistantPage = () => {
  const [messages, setMessages] = useState([]); // {role: 'user'|'assistant', content}
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [languages, setLanguages] = useState(FALLBACK_LANGUAGES);
  const [language, setLanguage] = useState(() => localStorage.getItem(LANGUAGE_STORAGE_KEY) || 'auto');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  useEffect(() => {
    chatAPI.getLanguages()
      .then((response) => setLanguages(response.data.data))
      .catch(() => {}); // keep the fallback list - not worth blocking the page over
  }, []);

  const handleLanguageChange = (code) => {
    setLanguage(code);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
  };

  const send = async (text) => {
    const message = text.trim();
    if (!message || sending) return;

    setError(null);
    const history = messages.slice(-20);
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setInput('');
    setSending(true);

    try {
      const response = await chatAPI.sendMessage(message, history, language);
      setMessages((prev) => [...prev, { role: 'assistant', content: response.data.data.reply }]);
    } catch (err) {
      const status = err.response?.status;
      if (status === 503) {
        setNotConfigured(true);
      } else {
        setError(err.response?.data?.error || 'The assistant could not respond. Please try again.');
      }
      // Roll back the optimistically-added user message so a retry doesn't duplicate it
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setSending(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    send(input);
  };

  return (
    <Layout>
      <div className="max-w-3xl mx-auto flex flex-col h-[calc(100vh-8rem)] sm:h-[calc(100vh-6rem)]">
        <div className="mb-4 sm:mb-6 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">AI Assistant</h1>
            <p className="text-gray-500 mt-1 text-sm sm:text-base">
              Ask about your spending, budgets, or goals — answers are grounded in your real transaction data.
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-gray-400 text-xs">🌐</span>
            <select
              value={language}
              onChange={(e) => handleLanguageChange(e.target.value)}
              className="text-xs sm:text-sm border border-gray-200 rounded-full pl-3 pr-7 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              aria-label="Reply language"
            >
              {languages.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex-1 bg-white rounded-2xl shadow-sm flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
            {messages.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-center px-4">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-2xl mb-4">
                  💬
                </div>
                <p className="text-gray-700 font-semibold mb-1">Ask me anything about your finances</p>
                <p className="text-gray-400 text-sm mb-6">I can see your transactions, budgets, and goals.</p>
                <div className="flex flex-wrap gap-2 justify-center max-w-md">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="text-xs sm:text-sm bg-indigo-50 text-indigo-600 hover:bg-indigo-100 px-3 py-1.5 rounded-full transition"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-br-sm'
                      : 'bg-gray-100 text-gray-800 rounded-bl-sm'
                  }`}
                >
                  <MessageText text={m.content} />
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-2.5 flex gap-1">
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" />
                </div>
              </div>
            )}

            {notConfigured && (
              <div className="bg-amber-50 border border-amber-300 text-amber-800 rounded-lg p-4 text-sm">
                The AI Assistant isn't set up yet — the backend needs Ollama running locally (or <code className="bg-amber-100 px-1 rounded">GROQ_API_KEY</code> set in production) to answer questions.
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-300 text-red-700 rounded-lg p-4 text-sm">{error}</div>
            )}

            <div ref={bottomRef} />
          </div>

          <form onSubmit={handleSubmit} className="border-t border-gray-100 p-3 sm:p-4 flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your spending, budgets, or goals..."
              disabled={sending}
              className="flex-1 min-w-0 border border-gray-200 rounded-full px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-50"
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold w-10 h-10 rounded-full flex items-center justify-center shrink-0"
              aria-label="Send"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </Layout>
  );
};

export default AssistantPage;
