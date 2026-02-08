import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import zhTranslation from '@/locales/zh.json';
import enTranslation from '@/locales/en.json';

export const resources = {
  zh: {
    translation: zhTranslation,
  },
  en: {
    translation: enTranslation,
  },
} as const;

export const supportedLanguages = [
  { code: 'zh', labelKey: 'language.zh' },
  { code: 'en', labelKey: 'language.en' },
] as const;

export type SupportedLanguage = (typeof supportedLanguages)[number]['code'];

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'zh',
    debug: import.meta.env.DEV,
    
    interpolation: {
      escapeValue: false, // React already escapes by default
    },
    
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'easysql-language',
    },
  });

export default i18n;
