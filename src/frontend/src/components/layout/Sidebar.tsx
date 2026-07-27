import { useState } from 'react';
import { ChevronLeft, ChevronRight, Globe, Cpu, RefreshCw } from 'lucide-react';
import { useTranslation } from '@/i18n';
import { usePreferencesStore } from '@/store/preferencesStore';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

// --- Available Models Configuration ---

const AVAILABLE_MODELS = [
  {
    id: 'default',
    nameKey: 'sidebar.model.options.default',
    descriptionKey: 'sidebar.model.options.defaultDesc',
  },
  {
    id: 'gemini/gemini-2.5-flash',
    nameKey: 'sidebar.model.options.gemini',
    descriptionKey: 'sidebar.model.options.geminiDesc',
  },
  {
    id: 'gemini/gemini-2.5-pro',
    nameKey: 'sidebar.model.options.geminiPro',
    descriptionKey: 'sidebar.model.options.geminiProDesc',
  },
  {
    id: 'groq/llama-3.3-70b-versatile',
    nameKey: 'sidebar.model.options.groq',
    descriptionKey: 'sidebar.model.options.groqDesc',
  },
  {
    id: 'groq/meta-llama/llama-4-maverick-17b-128e',
    nameKey: 'sidebar.model.options.groqMaverick',
    descriptionKey: 'sidebar.model.options.groqMaverickDesc',
  },
] as const;

const LANGUAGES = [
  { id: 'es' as const, nameKey: 'sidebar.language.options.es' },
  { id: 'en' as const, nameKey: 'sidebar.language.options.en' },
] as const;

// --- Sidebar Component ---

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { t } = useTranslation();
  const language = usePreferencesStore((s) => s.language);
  const model = usePreferencesStore((s) => s.model);
  const autoFallback = usePreferencesStore((s) => s.autoFallback);
  const setLanguage = usePreferencesStore((s) => s.setLanguage);
  const setModel = usePreferencesStore((s) => s.setModel);
  const setAutoFallback = usePreferencesStore((s) => s.setAutoFallback);

  return (
    <TooltipProvider delayDuration={300}>
      <aside
        role="complementary"
        aria-label={t('sidebar.title')}
        className={cn(
          'flex shrink-0 flex-col border-r border-border bg-muted/30 transition-[width] duration-200 ease-in-out',
          collapsed ? 'w-12' : 'w-[260px]',
        )}
      >
        {/* Toggle button */}
        <div className="flex items-center justify-end border-b p-2">
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            aria-expanded={!collapsed}
            aria-label={collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Content */}
        <div className={cn('flex-1 overflow-y-auto', collapsed ? 'px-2 py-4' : 'px-4 py-4')}>
          {collapsed ? (
            <CollapsedContent t={t} language={language} model={model} autoFallback={autoFallback} />
          ) : (
            <ExpandedContent
              t={t}
              language={language}
              model={model}
              autoFallback={autoFallback}
              setLanguage={setLanguage}
              setModel={setModel}
              setAutoFallback={setAutoFallback}
            />
          )}
        </div>
      </aside>
    </TooltipProvider>
  );
}

// --- Collapsed State: Icon Indicators with Tooltips ---

interface CollapsedContentProps {
  t: (key: string) => string;
  language: string;
  model: string;
  autoFallback: boolean;
}

function CollapsedContent({ t, language, model, autoFallback }: CollapsedContentProps) {
  return (
    <div className="flex flex-col items-center gap-4">
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground">
            <Globe className="h-4 w-4" />
          </div>
        </TooltipTrigger>
        <TooltipContent side="right">
          <p>
            {t('sidebar.language.label')}: {language.toUpperCase()}
          </p>
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground">
            <Cpu className="h-4 w-4" />
          </div>
        </TooltipTrigger>
        <TooltipContent side="right">
          <p>
            {t('sidebar.model.label')}:{' '}
            {model === 'default' ? t('sidebar.model.options.default') : model}
          </p>
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground">
            <RefreshCw className={cn('h-4 w-4', !autoFallback && 'opacity-40')} />
          </div>
        </TooltipTrigger>
        <TooltipContent side="right">
          <p>
            {t('sidebar.fallback.label')}:{' '}
            {autoFallback ? t('sidebar.fallback.enabled') : t('sidebar.fallback.disabled')}
          </p>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

// --- Expanded State: Full Preference Controls ---

interface ExpandedContentProps {
  t: (key: string) => string;
  language: 'es' | 'en';
  model: string;
  autoFallback: boolean;
  setLanguage: (lang: 'es' | 'en') => void;
  setModel: (model: string) => void;
  setAutoFallback: (enabled: boolean) => void;
}

function ExpandedContent({
  t,
  language,
  model,
  autoFallback,
  setLanguage,
  setModel,
  setAutoFallback,
}: ExpandedContentProps) {
  return (
    <div className="space-y-6">
      {/* Preferences heading */}
      <h2 className="text-sm font-semibold text-foreground">
        {t('sidebar.preferences.title')}
      </h2>

      {/* Language selector */}
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Globe className="h-4 w-4 text-muted-foreground" />
          {t('sidebar.language.label')}
        </label>
        <Select value={language} onValueChange={(val) => setLanguage(val as 'es' | 'en')}>
          <SelectTrigger aria-label={t('sidebar.language.label')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LANGUAGES.map((lang) => (
              <SelectItem key={lang.id} value={lang.id}>
                {t(lang.nameKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Model selector */}
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Cpu className="h-4 w-4 text-muted-foreground" />
          {t('sidebar.model.label')}
        </label>
        <Select value={model} onValueChange={setModel}>
          <SelectTrigger aria-label={t('sidebar.model.label')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AVAILABLE_MODELS.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {t(m.nameKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {/* Brief description below model selector */}
        <p className="text-xs text-muted-foreground">
          {t(
            AVAILABLE_MODELS.find((m) => m.id === model)?.descriptionKey ??
              'sidebar.model.options.defaultDesc',
          )}
        </p>
      </div>

      {/* Auto-fallback switch */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label
            htmlFor="sidebar-auto-fallback"
            className="flex items-center gap-2 text-sm font-medium text-foreground"
          >
            <RefreshCw className="h-4 w-4 text-muted-foreground" />
            {t('sidebar.fallback.label')}
          </label>
          <Switch
            id="sidebar-auto-fallback"
            checked={autoFallback}
            onCheckedChange={setAutoFallback}
            aria-label={t('sidebar.fallback.label')}
          />
        </div>
        <p className="text-xs text-muted-foreground">{t('sidebar.fallback.description')}</p>
      </div>
    </div>
  );
}
