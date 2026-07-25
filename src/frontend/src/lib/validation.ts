/**
 * Client-side file validation.
 * Mirrors backend validation for instant user feedback.
 */

export const SUPPORTED_EXTENSIONS = ['.md', '.txt', '.pdf'] as const;
export type SupportedExtension = (typeof SUPPORTED_EXTENSIONS)[number];

/** 1 MB — inclusive (files at exactly this size are accepted) */
export const SIZE_LIMIT_TEXT = 1_048_576;
/** 10 MB — inclusive (files at exactly this size are accepted) */
export const SIZE_LIMIT_PDF = 10_485_760;

export type FileFormat = 'markdown' | 'plain_text' | 'pdf';

export type ValidationResult =
  | { valid: true; format: FileFormat }
  | { valid: false; errorKey: string; metadata: { filename: string; size: number; limit: number } };

const EXTENSION_FORMAT_MAP: Record<SupportedExtension, FileFormat> = {
  '.md': 'markdown',
  '.txt': 'plain_text',
  '.pdf': 'pdf',
};

function getExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.');
  if (lastDot === -1) return '';
  return filename.slice(lastDot).toLowerCase();
}

function getSizeLimit(format: FileFormat): number {
  return format === 'pdf' ? SIZE_LIMIT_PDF : SIZE_LIMIT_TEXT;
}

/**
 * Validates a file for upload eligibility.
 *
 * Checks:
 * 1. File extension is one of .md, .txt, .pdf
 * 2. File size does not exceed the format-specific limit (boundary is inclusive/accepted)
 *
 * Returns a discriminated union:
 * - `{ valid: true, format }` when the file passes all checks
 * - `{ valid: false, errorKey, metadata }` when validation fails
 */
export function validateFile(file: File): ValidationResult {
  const extension = getExtension(file.name);

  // Check if extension is supported
  if (!SUPPORTED_EXTENSIONS.includes(extension as SupportedExtension)) {
    return {
      valid: false,
      errorKey: 'errors.unsupportedFormat',
      metadata: {
        filename: file.name,
        size: file.size,
        limit: 0,
      },
    };
  }

  const format = EXTENSION_FORMAT_MAP[extension as SupportedExtension];
  const limit = getSizeLimit(format);

  // Size check: strictly greater than limit = rejected
  if (file.size > limit) {
    return {
      valid: false,
      errorKey: 'errors.fileTooLarge',
      metadata: {
        filename: file.name,
        size: file.size,
        limit,
      },
    };
  }

  return { valid: true, format };
}
