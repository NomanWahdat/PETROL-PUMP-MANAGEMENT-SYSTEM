import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import en from './en.json';
import fa from './fa.json';
import ps from './ps.json';
import type { Language } from '../types/api';

export type TranslationKey = keyof typeof en;
const dictionaries: Record<Language, Record<TranslationKey, string>> = { en, fa, ps };
const localeCodes: Record<Language, string> = { en: 'en', fa: 'fa-AF', ps: 'ps-AF' };
interface I18nContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: TranslationKey) => string;
}
const I18nContext = createContext<I18nContextValue | null>(null);

function savedLanguage(): Language {
  try {
    const language = localStorage.getItem('station-language');
    return language === 'en' || language === 'ps' ? language : 'fa';
  } catch { return 'fa'; }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(savedLanguage);
  useEffect(() => {
    document.documentElement.lang = localeCodes[language];
    document.documentElement.dir = language === 'en' ? 'ltr' : 'rtl';
    document.title = dictionaries[language].appName;
    try { localStorage.setItem('station-language', language); } catch { /* Storage is optional. */ }
  }, [language]);
  return <I18nContext.Provider value={{ language, setLanguage, t: key => dictionaries[language][key] }}>
    {children}
  </I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error('I18nProvider is required');
  return value;
}
