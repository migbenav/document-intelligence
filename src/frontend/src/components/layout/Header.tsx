import { useTranslation } from '@/i18n';

export function Header() {
  const { t } = useTranslation();

  return (
    <header className="border-b px-4 py-4 sm:px-6">
      <h1 className="text-xl font-semibold">{t('app.name')}</h1>
    </header>
  );
}
