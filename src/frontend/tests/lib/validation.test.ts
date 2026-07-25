import { describe, it, expect } from 'vitest';
import {
  validateFile,
  SUPPORTED_EXTENSIONS,
  SIZE_LIMIT_TEXT,
  SIZE_LIMIT_PDF,
} from '../../src/lib/validation';
import { formatBytes } from '../../src/lib/utils';

/**
 * Helper to create a mock File object with a given name and size.
 */
function createFile(name: string, size: number): File {
  // Create a Blob of the desired size, then wrap it as a File
  const content = new Uint8Array(size);
  return new File([content], name, { type: 'application/octet-stream' });
}

describe('validateFile', () => {
  describe('supported extensions', () => {
    it('accepts .md files', () => {
      const file = createFile('readme.md', 100);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'markdown' });
    });

    it('accepts .txt files', () => {
      const file = createFile('notes.txt', 100);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'plain_text' });
    });

    it('accepts .pdf files', () => {
      const file = createFile('document.pdf', 100);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'pdf' });
    });

    it('accepts extensions case-insensitively', () => {
      const mdUpper = createFile('README.MD', 100);
      expect(validateFile(mdUpper)).toEqual({ valid: true, format: 'markdown' });

      const txtMixed = createFile('file.TxT', 100);
      expect(validateFile(txtMixed)).toEqual({ valid: true, format: 'plain_text' });

      const pdfUpper = createFile('doc.PDF', 100);
      expect(validateFile(pdfUpper)).toEqual({ valid: true, format: 'pdf' });
    });
  });

  describe('unsupported extensions', () => {
    it('rejects .docx files', () => {
      const file = createFile('report.docx', 100);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.unsupportedFormat');
        expect(result.metadata.filename).toBe('report.docx');
      }
    });

    it('rejects .xlsx files', () => {
      const file = createFile('data.xlsx', 100);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.unsupportedFormat');
      }
    });

    it('rejects .html files', () => {
      const file = createFile('page.html', 100);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.unsupportedFormat');
      }
    });

    it('rejects files with no extension', () => {
      const file = createFile('Makefile', 100);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.unsupportedFormat');
      }
    });

    it('rejects files with similar but wrong extensions', () => {
      const file = createFile('file.markdown', 100);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.unsupportedFormat');
      }
    });
  });

  describe('size limits for markdown/text files', () => {
    it('accepts a .md file at exactly the size limit (1,048,576 bytes)', () => {
      const file = createFile('large.md', SIZE_LIMIT_TEXT);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'markdown' });
    });

    it('rejects a .md file one byte over the limit (1,048,577 bytes)', () => {
      const file = createFile('too-large.md', SIZE_LIMIT_TEXT + 1);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.fileTooLarge');
        expect(result.metadata.filename).toBe('too-large.md');
        expect(result.metadata.size).toBe(SIZE_LIMIT_TEXT + 1);
        expect(result.metadata.limit).toBe(SIZE_LIMIT_TEXT);
      }
    });

    it('accepts a .txt file at exactly the size limit', () => {
      const file = createFile('notes.txt', SIZE_LIMIT_TEXT);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'plain_text' });
    });

    it('rejects a .txt file one byte over the limit', () => {
      const file = createFile('big.txt', SIZE_LIMIT_TEXT + 1);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.fileTooLarge');
        expect(result.metadata.limit).toBe(SIZE_LIMIT_TEXT);
      }
    });
  });

  describe('size limits for PDF files', () => {
    it('accepts a .pdf file at exactly the size limit (10,485,760 bytes)', () => {
      const file = createFile('document.pdf', SIZE_LIMIT_PDF);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'pdf' });
    });

    it('rejects a .pdf file one byte over the limit (10,485,761 bytes)', () => {
      const file = createFile('huge.pdf', SIZE_LIMIT_PDF + 1);
      const result = validateFile(file);
      expect(result.valid).toBe(false);
      if (!result.valid) {
        expect(result.errorKey).toBe('errors.fileTooLarge');
        expect(result.metadata.filename).toBe('huge.pdf');
        expect(result.metadata.size).toBe(SIZE_LIMIT_PDF + 1);
        expect(result.metadata.limit).toBe(SIZE_LIMIT_PDF);
      }
    });
  });

  describe('zero-size files', () => {
    it('accepts a zero-byte .md file (empty but valid)', () => {
      const file = createFile('empty.md', 0);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'markdown' });
    });

    it('accepts a zero-byte .pdf file', () => {
      const file = createFile('empty.pdf', 0);
      const result = validateFile(file);
      expect(result).toEqual({ valid: true, format: 'pdf' });
    });
  });
});

describe('formatBytes', () => {
  it('formats 0 bytes', () => {
    expect(formatBytes(0)).toBe('0 Bytes');
  });

  it('formats bytes under 1 KB', () => {
    expect(formatBytes(500)).toBe('500 Bytes');
  });

  it('formats exactly 1 KB', () => {
    expect(formatBytes(1024)).toBe('1 KB');
  });

  it('formats kilobytes', () => {
    expect(formatBytes(1536)).toBe('1.5 KB');
  });

  it('formats exactly 1 MB', () => {
    expect(formatBytes(1_048_576)).toBe('1 MB');
  });

  it('formats megabytes', () => {
    expect(formatBytes(10_485_760)).toBe('10 MB');
  });

  it('handles negative values gracefully', () => {
    expect(formatBytes(-1)).toBe('0 Bytes');
  });
});

describe('SUPPORTED_EXTENSIONS constant', () => {
  it('contains exactly .md, .txt, and .pdf', () => {
    expect(SUPPORTED_EXTENSIONS).toEqual(['.md', '.txt', '.pdf']);
  });
});
