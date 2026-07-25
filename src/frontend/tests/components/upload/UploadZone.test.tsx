import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { UploadZone } from '@/components/upload/UploadZone';
import { TranslationProvider } from '@/i18n';
import { useUploadStore } from '@/store/uploadStore';

function renderWithProviders(ui: React.ReactElement) {
  return render(<TranslationProvider>{ui}</TranslationProvider>);
}

function createFile(name: string, size: number, type = 'text/plain'): File {
  const content = new Uint8Array(size);
  return new File([content], name, { type });
}

describe('UploadZone', () => {
  beforeEach(() => {
    useUploadStore.getState().reset();
  });

  it('renders format instructions and size limits', () => {
    renderWithProviders(<UploadZone />);
    expect(screen.getByText('Drag and drop your file here, or click to browse')).toBeInTheDocument();
    expect(screen.getByText('Supported formats: .md, .txt, .pdf')).toBeInTheDocument();
    expect(screen.getByText('Max size: 1 MB (text), 10 MB (PDF)')).toBeInTheDocument();
  });

  it('opens file picker on click', () => {
    renderWithProviders(<UploadZone />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const clickSpy = vi.spyOn(input, 'click');

    const zone = screen.getByRole('button');
    fireEvent.click(zone);

    expect(clickSpy).toHaveBeenCalled();
  });

  it('accepts a valid file via file input', () => {
    renderWithProviders(<UploadZone />);
    const input = screen.getByTestId('file-input');
    const file = createFile('readme.md', 500);

    fireEvent.change(input, { target: { files: [file] } });

    const store = useUploadStore.getState();
    expect(store.step).toBe('file-selected');
    expect(store.selectedFile?.name).toBe('readme.md');
  });

  it('shows validation error for unsupported file format', () => {
    renderWithProviders(<UploadZone />);
    const input = screen.getByTestId('file-input');
    const file = createFile('document.docx', 500);

    fireEvent.change(input, { target: { files: [file] } });

    expect(
      screen.getByText('This file format is not supported. Please upload a .md, .txt, or .pdf file.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('shows validation error when file exceeds size limit', () => {
    renderWithProviders(<UploadZone />);
    const input = screen.getByTestId('file-input');
    // 1 MB + 1 byte for a text file
    const file = createFile('big.txt', 1_048_577);

    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/File exceeds the size limit/)).toBeInTheDocument();
  });

  it('clears validation error when a valid file is selected', () => {
    renderWithProviders(<UploadZone />);
    const input = screen.getByTestId('file-input');

    // First, trigger an error
    fireEvent.change(input, { target: { files: [createFile('bad.docx', 100)] } });
    expect(screen.getByRole('alert')).toBeInTheDocument();

    // Now select a valid file
    fireEvent.change(input, { target: { files: [createFile('good.md', 100)] } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows visual feedback on drag-over (border highlight)', () => {
    renderWithProviders(<UploadZone />);
    const zone = screen.getByRole('button');

    fireEvent.dragOver(zone);
    expect(zone).toHaveClass('border-primary');

    fireEvent.dragLeave(zone);
    expect(zone).not.toHaveClass('border-primary');
  });

  it('accepts a valid file via drag-and-drop', () => {
    renderWithProviders(<UploadZone />);
    const zone = screen.getByRole('button');
    const file = createFile('notes.txt', 200);

    fireEvent.drop(zone, {
      dataTransfer: { files: [file] },
    });

    const store = useUploadStore.getState();
    expect(store.step).toBe('file-selected');
    expect(store.selectedFile?.name).toBe('notes.txt');
  });

  it('validates file on drag-and-drop and shows error for invalid files', () => {
    renderWithProviders(<UploadZone />);
    const zone = screen.getByRole('button');
    const file = createFile('sheet.xlsx', 200);

    fireEvent.drop(zone, {
      dataTransfer: { files: [file] },
    });

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(
      screen.getByText('This file format is not supported. Please upload a .md, .txt, or .pdf file.'),
    ).toBeInTheDocument();
  });
});
