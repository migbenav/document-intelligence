import { useTranslation } from '@/i18n';

export function LoadingState() {
  const { t } = useTranslation();

  return (
    <div
      className="flex flex-col items-center justify-center gap-3 py-12"
      data-testid="km-loading-state"
    >
      <div
        className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary"
        role="status"
        aria-label={t('km.states.loading')}
      />
      <p className="text-sm text-muted-foreground">{t('km.states.loading')}</p>
    </div>
  );
}
