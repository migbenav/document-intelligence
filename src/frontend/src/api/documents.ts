import { API_BASE_URL, UPLOAD_TIMEOUT_MS, SLOW_CONNECTION_THRESHOLD_MS, apiFetch, getPreferenceHeaders } from './client';
import type { UploadResponse, StatusResponse, ApiErrorResponse } from '@/types/api';

/**
 * Typed API error carrying structured error information from the backend.
 */
export class ApiError extends Error {
  public readonly error: string;
  public readonly supportedFormats?: string[];
  public readonly maxSizeBytes?: number;
  public readonly requiredEncoding?: string;

  constructor(response: ApiErrorResponse) {
    super(response.message);
    this.name = 'ApiError';
    this.error = response.error;
    this.supportedFormats = response.supported_formats;
    this.maxSizeBytes = response.max_size_bytes;
    this.requiredEncoding = response.required_encoding;
  }
}

export interface UploadDocumentOptions {
  /** Called with progress 0–100 as upload bytes are sent */
  onProgress?: (percent: number) => void;
  /** Called if the request takes longer than 3 seconds */
  onSlowConnection?: () => void;
}

/**
 * Upload a document file to the backend using XMLHttpRequest for progress tracking.
 * Returns UploadResponse on success or throws ApiError / Error on failure.
 */
export function uploadDocument(
  file: File,
  options: UploadDocumentOptions = {},
): Promise<UploadResponse> {
  const { onProgress, onSlowConnection } = options;

  return new Promise<UploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const url = `${API_BASE_URL}/api/v1/documents/upload`;

    xhr.open('POST', url);
    xhr.timeout = UPLOAD_TIMEOUT_MS;

    // Inject preference headers
    const prefHeaders = getPreferenceHeaders();
    for (const [key, value] of Object.entries(prefHeaders)) {
      xhr.setRequestHeader(key, value);
    }

    // Slow connection detection
    let slowTimer: ReturnType<typeof setTimeout> | undefined;
    if (onSlowConnection) {
      slowTimer = setTimeout(() => {
        onSlowConnection();
      }, SLOW_CONNECTION_THRESHOLD_MS);
    }

    const clearSlowTimer = () => {
      if (slowTimer !== undefined) {
        clearTimeout(slowTimer);
        slowTimer = undefined;
      }
    };

    // Progress tracking
    if (onProgress) {
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      });
    }

    xhr.addEventListener('load', () => {
      clearSlowTimer();

      if (xhr.status >= 200 && xhr.status < 300) {
        const data = JSON.parse(xhr.responseText) as UploadResponse;
        resolve(data);
      } else {
        try {
          const errorData = JSON.parse(xhr.responseText) as ApiErrorResponse;
          reject(new ApiError(errorData));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    });

    xhr.addEventListener('error', () => {
      clearSlowTimer();
      reject(new Error('Network error during upload'));
    });

    xhr.addEventListener('timeout', () => {
      clearSlowTimer();
      reject(new Error('Upload timed out'));
    });

    xhr.addEventListener('abort', () => {
      clearSlowTimer();
      reject(new Error('Upload aborted'));
    });

    const formData = new FormData();
    formData.append('file', file);
    xhr.send(formData);
  });
}

export interface GetDocumentStatusOptions {
  /** AbortSignal for cancelling the request */
  signal?: AbortSignal;
  /** Called if the request takes longer than 3 seconds */
  onSlowConnection?: () => void;
}

/**
 * Fetch the processing status for a document.
 * Uses the Fetch API with AbortController support.
 */
export async function getDocumentStatus(
  documentId: string,
  options: GetDocumentStatusOptions = {},
): Promise<StatusResponse> {
  const { signal, onSlowConnection } = options;
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/status`;

  // Slow connection detection
  let slowTimer: ReturnType<typeof setTimeout> | undefined;
  if (onSlowConnection) {
    slowTimer = setTimeout(() => {
      onSlowConnection();
    }, SLOW_CONNECTION_THRESHOLD_MS);
  }

  const clearSlowTimer = () => {
    if (slowTimer !== undefined) {
      clearTimeout(slowTimer);
      slowTimer = undefined;
    }
  };

  try {
    const response = await apiFetch(url, { signal });
    clearSlowTimer();

    if (!response.ok) {
      const errorData = (await response.json()) as ApiErrorResponse;
      throw new ApiError(errorData);
    }

    return (await response.json()) as StatusResponse;
  } catch (error) {
    clearSlowTimer();
    throw error;
  }
}
