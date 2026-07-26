import { createContext, useContext, useMemo, createElement } from 'react';
import type { ReactNode } from 'react';
import en from './en.json';
import es from './es.json';

type TranslationMap = Record<string, unknown>;

const translations: Record<string, TranslationMap> = { en, es };

interface TranslationContextValue {
  t: (key: string, params?: Record<string, string>) => string;
  locale: string;
}

const TranslationContext = createContext<TranslationContextValue | null>(null);

function getNestedValue(obj: TranslationMap, path: string): string | undefined {
  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return undefined;
    }
    current = (current as Record<string, unknown>)[key];
  }

  return typeof current === 'string' ? current : undefined;
}

function interpolate(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    return key in params ? params[key]! : match;
  });
}

interface TranslationProviderProps {
  locale?: string;
  children: ReactNode;
}

export function TranslationProvider({ locale = 'es', children }: TranslationProviderProps) {
  const value = useMemo<TranslationContextValue>(() => {
    const messages = translations[locale] ?? translations['es']!;

    const t = (key: string, params?: Record<string, string>): string => {
      const raw = getNestedValue(messages, key);
      if (raw === undefined) {
        return key;
      }
      return params ? interpolate(raw, params) : raw;
    };

    return { t, locale };
  }, [locale]);

  return createElement(TranslationContext.Provider, { value }, children);
}

export function useTranslation(): TranslationContextValue {
  const context = useContext(TranslationContext);
  if (!context) {
    throw new Error('useTranslation must be used within a TranslationProvider');
  }
  return context;
}
