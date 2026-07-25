import { useCallback } from 'react';
import { useTranslation } from '@/i18n';
import { useKnowledgeModelStore } from '@/store/knowledgeModelStore';
import type { ViewMode } from '@/store/knowledgeModelStore';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface KMHeaderProps {
  verificationRate: number;
}

/**
 * KMHeader displays the page title, overall verification rate, and view mode toggle buttons.
 * The verification rate is a value between 0 and 1, displayed as a rounded percentage.
 */
export function KMHeader({ verificationRate }: KMHeaderProps) {
  const { t } = useTranslation();
  const viewMode = useKnowledgeModelStore((s) => s.viewMode);
  const setViewMode = useKnowledgeModelStore((s) => s.setViewMode);

  const handleSetList = useCallback(() => {
    setViewMode('list');
  }, [setViewMode]);

  const handleSetGraph = useCallback(() => {
    setViewMode('graph');
  }, [setViewMode]);

  const displayRate = Math.round(verificationRate * 100).toString();

  return (
    <header
      className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
      data-testid="km-header"
    >
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{t('km.title')}</h1>
        <p className="text-sm text-muted-foreground">
          {t('km.verificationRate', { rate: displayRate })}
        </p>
      </div>

      <div className="flex items-center gap-1" role="group" aria-label={t('km.title')}>
        <ViewModeButton
          mode="list"
          currentMode={viewMode}
          label={t('km.viewMode.list')}
          onClick={handleSetList}
        />
        <ViewModeButton
          mode="graph"
          currentMode={viewMode}
          label={t('km.viewMode.graph')}
          onClick={handleSetGraph}
        />
      </div>
    </header>
  );
}

interface ViewModeButtonProps {
  mode: ViewMode;
  currentMode: ViewMode;
  label: string;
  onClick: () => void;
}

function ViewModeButton({ mode, currentMode, label, onClick }: ViewModeButtonProps) {
  const isActive = mode === currentMode;

  return (
    <Button
      variant={isActive ? 'default' : 'outline'}
      size="sm"
      onClick={onClick}
      aria-pressed={isActive}
      className={cn(!isActive && 'text-muted-foreground')}
    >
      {mode === 'list' ? <ListIcon /> : <GraphIcon />}
      {label}
    </Button>
  );
}

function ListIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M2 4.75A.75.75 0 0 1 2.75 4h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 4.75Zm0 5A.75.75 0 0 1 2.75 9h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 9.75Zm0 5a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1-.75-.75Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function GraphIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="h-4 w-4"
      aria-hidden="true"
    >
      <path d="M15.5 2A1.5 1.5 0 0 0 14 3.5v13a1.5 1.5 0 0 0 3 0v-13A1.5 1.5 0 0 0 15.5 2ZM10 6a1.5 1.5 0 0 0-1.5 1.5v9a1.5 1.5 0 0 0 3 0v-9A1.5 1.5 0 0 0 10 6ZM4.5 10A1.5 1.5 0 0 0 3 11.5v5a1.5 1.5 0 0 0 3 0v-5A1.5 1.5 0 0 0 4.5 10Z" />
    </svg>
  );
}
