import { useTranslation } from '@/i18n';

export function EmptyState() {
  const { t } = useTranslation();

  return (
    <div
      className="flex flex-col items-center justify-center gap-2 py-12 text-center"
      data-testid="km-empty-state"
    >
      <p className="text-sm text-muted-foreground">{t('km.states.empty')}</p>
    </div>
  );
}
