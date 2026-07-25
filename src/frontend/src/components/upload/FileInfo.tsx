import { useUploadStore } from '@/store/uploadStore';
import { formatBytes } from '@/lib/utils';
import type { FileFormat } from '@/store/uploadStore';

const FORMAT_LABELS: Record<FileFormat, string> = {
  markdown: 'Markdown',
  plain_text: 'Text',
  pdf: 'PDF',
};

export function FileInfo() {
  const selectedFile = useUploadStore((s) => s.selectedFile);

  if (!selectedFile) return null;

  return (
    <div className="flex items-center gap-3 rounded-md border bg-muted/50 px-4 py-3">
      <span className="truncate text-sm font-medium">{selectedFile.name}</span>
      <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
        {FORMAT_LABELS[selectedFile.format]}
      </span>
      <span className="ml-auto whitespace-nowrap text-xs text-muted-foreground">
        {formatBytes(selectedFile.size)}
      </span>
    </div>
  );
}
