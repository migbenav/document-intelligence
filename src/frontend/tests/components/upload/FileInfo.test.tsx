import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { FileInfo } from '@/components/upload/FileInfo';
import { TranslationProvider } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function createFile(name: string, size: number, type = 'text/plain'): File {
  const content = new Uint8Array(size);
  return new File([content], name, { type });
}

describe('FileInfo', () => {
  beforeEach(() => {
    useUploadStore.getState().reset();
  });

  it('renders nothing when no file is selected', () => {
    const { container } = renderWithProviders(<FileInfo />);
    expect(container.firstChild).toBeNull();
  });

  it('displays the filename', () => {
    const file = createFile('report.md', 2048);
    useUploadStore.getState().selectFile(file);

    renderWithProviders(<FileInfo />);
    expect(screen.getByText('report.md')).toBeInTheDocument();
  });

  it('displays the format badge for markdown', () => {
    const file = createFile('doc.md', 1024);
    useUploadStore.getState().selectFile(file);

    renderWithProviders(<FileInfo />);
    expect(screen.getByText('Markdown')).toBeInTheDocument();
  });

  it('displays the format badge for plain text', () => {
    const file = createFile('notes.txt', 512);
    useUploadStore.getState().selectFile(file);

    renderWithProviders(<FileInfo />);
    expect(screen.getByText('Text')).toBeInTheDocument();
  });

  it('displays the format badge for PDF', () => {
    const file = createFile('paper.pdf', 4096);
    useUploadStore.getState().selectFile(file);

    renderWithProviders(<FileInfo />);
    expect(screen.getByText('PDF')).toBeInTheDocument();
  });

  it('displays the formatted file size', () => {
    // 2048 bytes = 2 KB
    const file = createFile('data.txt', 2048);
    useUploadStore.getState().selectFile(file);

    renderWithProviders(<FileInfo />);
    expect(screen.getByText('2 KB')).toBeInTheDocument();
  });

  it('displays size for larger files', () => {
    // 1,048,576 bytes = 1 MB
    const file = createFile('big.pdf', 1_048_576);
    useUploadStore.getState().selectFile(file);

    renderWithProviders(<FileInfo />);
    expect(screen.getByText('1 MB')).toBeInTheDocument();
  });
});
