import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

export function ConsentDialog() {
  const { t } = useTranslation();
  const step = useUploadStore((s) => s.step);
  const acceptConsent = useUploadStore((s) => s.acceptConsent);
  const declineConsent = useUploadStore((s) => s.declineConsent);

  const isOpen = step === 'consent-pending';

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      declineConsent();
    }
  };

  const handleAccept = () => {
    acceptConsent();
  };

  const handleCancel = () => {
    declineConsent();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('consent.title')}</DialogTitle>
          <DialogDescription>{t('consent.body')}</DialogDescription>
        </DialogHeader>
        <ul className="space-y-2 text-sm text-muted-foreground list-disc pl-5">
          <li>{t('consent.details.sent')}</li>
          <li>{t('consent.details.noPersonalData')}</li>
          <li>{t('consent.details.retention')}</li>
        </ul>
        <DialogFooter>
          <Button variant="secondary" onClick={handleCancel}>
            {t('consent.decline')}
          </Button>
          <Button onClick={handleAccept}>
            {t('consent.accept')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
