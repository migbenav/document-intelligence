import { useCallback, useRef, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { useTranslation } from '@/i18n';
import { validateFile } from '@/lib/validation';
import { useUploadStore } from '@/store/uploadStore';
import { cn } from '@/lib/utils';

export function UploadZone() {
  const { t } = useTranslation();
  const selectFile = useUploadStore((s) => s.selectFile);
  const [isDragOver, setIsDragOver] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File) => {
      const result = validateFile(file);
      if (result.valid) {
        setValidationError(null);
        selectFile(file);
      } else {
        setValidationError(
          t(result.errorKey, {
            limit: result.metadata.limit > 0 ? `${result.metadata.limit / 1_048_576} MB` : '',
          }),
        );
      }
    },
    [selectFile, t],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile],
  );

  const handleClick = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFile(file);
      }
      // Reset input value so re-selecting the same file triggers change
      e.target.value = '';
    },
    [handleFile],
  );

  return (
    <div>
      <Card
        className={cn(
          'cursor-pointer border-2 border-dashed transition-colors',
          isDragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/25',
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        aria-label={t('upload.dropzone')}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleClick();
          }
        }}
      >
        <CardContent className="flex flex-col items-center justify-center gap-2 py-10">
          <p className="text-sm text-muted-foreground">{t('upload.dropzone')}</p>
          <p className="text-xs text-muted-foreground">{t('upload.formats')}</p>
          <p className="text-xs text-muted-foreground">{t('upload.sizeLimits')}</p>
        </CardContent>
      </Card>

      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".md,.txt,.pdf"
        onChange={handleInputChange}
        aria-hidden="true"
        tabIndex={-1}
        data-testid="file-input"
      />

      {validationError && (
        <p className="mt-2 text-sm text-destructive" role="alert">
          {validationError}
        </p>
      )}
    </div>
  );
}
