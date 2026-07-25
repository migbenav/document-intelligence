import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { uploadDocument, getDocumentStatus, ApiError } from '@/api/documents';
import type { UploadResponse, StatusResponse } from '@/types/api';

// --- XMLHttpRequest mock ---

interface MockXHR {
  open: ReturnType<typeof vi.fn>;
  send: ReturnType<typeof vi.fn>;
  addEventListener: ReturnType<typeof vi.fn>;
  timeout: number;
  status: number;
  responseText: string;
  upload: {
    addEventListener: ReturnType<typeof vi.fn>;
  };
  _listeners: Record<string, (() => void)[]>;
  _uploadListeners: Record<string, ((e: unknown) => void)[]>;
  _trigger: (event: string) => void;
  _triggerUpload: (event: string, payload: unknown) => void;
}

function createMockXHR(): MockXHR {
  const xhr: MockXHR = {
    open: vi.fn(),
    send: vi.fn(),
    addEventListener: vi.fn(),
    timeout: 0,
    status: 0,
    responseText: '',
    upload: {
      addEventListener: vi.fn(),
    },
    _listeners: {},
    _uploadListeners: {},
    _trigger(event: string) {
      const handlers = this._listeners[event] ?? [];
      handlers.forEach((h) => h());
    },
    _triggerUpload(event: string, payload: unknown) {
      const handlers = this._uploadListeners[event] ?? [];
      handlers.forEach((h) => h(payload));
    },
  };

  xhr.addEventListener.mockImplementation((event: string, handler: () => void) => {
    if (!xhr._listeners[event]) xhr._listeners[event] = [];
    xhr._listeners[event]!.push(handler);
  });

  xhr.upload.addEventListener.mockImplementation((event: string, handler: (e: unknown) => void) => {
    if (!xhr._uploadListeners[event]) xhr._uploadListeners[event] = [];
    xhr._uploadListeners[event]!.push(handler);
  });

  return xhr;
}

let mockXHR: MockXHR;

beforeEach(() => {
  mockXHR = createMockXHR();
  vi.stubGlobal('XMLHttpRequest', vi.fn(() => mockXHR));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// --- Tests ---

describe('uploadDocument', () => {
  const mockUploadResponse: UploadResponse = {
    document_id: 'doc-123',
    status: 'processing',
    filename: 'test.md',
    format: 'markdown',
    language: null,
    chunk_count: null,
    warnings: [],
    error_message: null,
  };

  it('sends file as multipart/form-data and resolves with UploadResponse', async () => {
    const file = new File(['# Hello'], 'test.md', { type: 'text/markdown' });

    const promise = uploadDocument(file);

    // Simulate successful response
    mockXHR.status = 202;
    mockXHR.responseText = JSON.stringify(mockUploadResponse);
    mockXHR._trigger('load');

    const result = await promise;
    expect(result).toEqual(mockUploadResponse);

    // Verify correct URL and method
    expect(mockXHR.open).toHaveBeenCalledWith(
      'POST',
      'http://localhost:8000/api/v1/documents/upload',
    );

    // Verify FormData was sent with the file
    const sendArg = mockXHR.send.mock.calls[0]![0] as FormData;
    expect(sendArg).toBeInstanceOf(FormData);
    expect(sendArg.get('file')).toBe(file);
  });

  it('sets timeout to 30 seconds', async () => {
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });

    const promise = uploadDocument(file);

    mockXHR.status = 202;
    mockXHR.responseText = JSON.stringify(mockUploadResponse);
    mockXHR._trigger('load');

    await promise;
    expect(mockXHR.timeout).toBe(30_000);
  });

  it('calls onProgress callback with upload percentage', async () => {
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });
    const onProgress = vi.fn();

    const promise = uploadDocument(file, { onProgress });

    // Simulate progress event
    mockXHR._triggerUpload('progress', { lengthComputable: true, loaded: 50, total: 100 });

    expect(onProgress).toHaveBeenCalledWith(50);

    // Finish
    mockXHR.status = 202;
    mockXHR.responseText = JSON.stringify(mockUploadResponse);
    mockXHR._trigger('load');
    await promise;
  });

  it('throws ApiError on 400 response with error body', async () => {
    const file = new File(['content'], 'test.docx', { type: 'application/octet-stream' });

    const promise = uploadDocument(file);

    mockXHR.status = 400;
    mockXHR.responseText = JSON.stringify({
      error: 'unsupported_format',
      message: 'File format not supported',
      supported_formats: ['.md', '.txt', '.pdf'],
    });
    mockXHR._trigger('load');

    await expect(promise).rejects.toThrow(ApiError);
    await expect(promise).rejects.toMatchObject({
      error: 'unsupported_format',
      message: 'File format not supported',
      supportedFormats: ['.md', '.txt', '.pdf'],
    });
  });

  it('throws generic Error on network failure', async () => {
    const file = new File(['content'], 'test.md', { type: 'text/markdown' });

    const promise = uploadDocument(file);
    mockXHR._trigger('error');

    await expect(promise).rejects.toThrow('Network error during upload');
  });

  it('throws Error on timeout', async () => {
    const file = new File(['content'], 'test.md', { type: 'text/markdown' });

    const promise = uploadDocument(file);
    mockXHR._trigger('timeout');

    await expect(promise).rejects.toThrow('Upload timed out');
  });

  it('calls onSlowConnection after 3 seconds', async () => {
    vi.useFakeTimers();
    const file = new File(['content'], 'test.md', { type: 'text/markdown' });
    const onSlowConnection = vi.fn();

    uploadDocument(file, { onSlowConnection });

    expect(onSlowConnection).not.toHaveBeenCalled();

    vi.advanceTimersByTime(3000);
    expect(onSlowConnection).toHaveBeenCalledTimes(1);

    // Cleanup
    mockXHR.status = 202;
    mockXHR.responseText = JSON.stringify(mockUploadResponse);
    mockXHR._trigger('load');

    vi.useRealTimers();
  });

  it('clears slow connection timer on successful response before 3s', async () => {
    vi.useFakeTimers();
    const file = new File(['content'], 'test.md', { type: 'text/markdown' });
    const onSlowConnection = vi.fn();

    const promise = uploadDocument(file, { onSlowConnection });

    // Respond before the 3s threshold
    vi.advanceTimersByTime(1000);
    mockXHR.status = 202;
    mockXHR.responseText = JSON.stringify(mockUploadResponse);
    mockXHR._trigger('load');

    await promise;

    vi.advanceTimersByTime(5000);
    expect(onSlowConnection).not.toHaveBeenCalled();

    vi.useRealTimers();
  });
});

describe('getDocumentStatus', () => {
  const mockStatusResponse: StatusResponse = {
    document_id: 'doc-123',
    status: 'ready',
    filename: 'test.md',
    format: 'markdown',
    language: 'en',
    chunk_count: 5,
    warnings: [],
    error_message: null,
  };

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('fetches document status and returns StatusResponse', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(mockStatusResponse), { status: 200 }),
    );

    const result = await getDocumentStatus('doc-123');

    expect(result).toEqual(mockStatusResponse);
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/documents/doc-123/status',
      { signal: undefined },
    );
  });

  it('throws ApiError on non-ok response', async () => {
    const errorBody = { error: 'not_found', message: 'Document not found' };

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(errorBody), { status: 404 }),
    );

    const error = await getDocumentStatus('doc-999').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      error: 'not_found',
      message: 'Document not found',
    });
  });

  it('supports AbortController signal', async () => {
    const controller = new AbortController();
    controller.abort();

    vi.mocked(fetch).mockRejectedValue(new DOMException('Aborted', 'AbortError'));

    await expect(
      getDocumentStatus('doc-123', { signal: controller.signal }),
    ).rejects.toThrow('Aborted');
  });

  it('calls onSlowConnection after 3 seconds', async () => {
    vi.useFakeTimers();
    const onSlowConnection = vi.fn();

    // Make fetch hang (never resolves until we let it)
    let resolveFetch!: (value: Response) => void;
    vi.mocked(fetch).mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveFetch = resolve;
      }),
    );

    const promise = getDocumentStatus('doc-123', { onSlowConnection });

    expect(onSlowConnection).not.toHaveBeenCalled();

    vi.advanceTimersByTime(3000);
    expect(onSlowConnection).toHaveBeenCalledTimes(1);

    // Resolve
    resolveFetch(new Response(JSON.stringify(mockStatusResponse), { status: 200 }));
    await promise;

    vi.useRealTimers();
  });

  it('clears slow connection timer when fetch resolves before 3s', async () => {
    vi.useFakeTimers();
    const onSlowConnection = vi.fn();

    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(mockStatusResponse), { status: 200 }),
    );

    await getDocumentStatus('doc-123', { onSlowConnection });

    vi.advanceTimersByTime(5000);
    expect(onSlowConnection).not.toHaveBeenCalled();

    vi.useRealTimers();
  });
});
