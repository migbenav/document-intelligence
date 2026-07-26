import { API_BASE_URL } from './client';

/** Timeout for analysis operations (LLM calls can take 60-90s for large docs) */
const ANALYSIS_TIMEOUT_MS = 180_000;

export interface AnalyzeResponse {
  session_id: string;
  document_id: string;
  status: string;
  suggested_type: string | null;
  suggested_type_justification: string | null;
}

export interface ConfirmTypeResponse {
  session_id: string;
  document_id: string;
  status: string;
  confirmed_type: string;
}

/**
 * Start analysis for a document. Returns the session with a suggested type.
 */
export async function startAnalysis(documentId: string): Promise<AnalyzeResponse> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/analyze`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ANALYSIS_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'POST',
      signal: controller.signal,
    });

    if (response.ok) {
      return (await response.json()) as AnalyzeResponse;
    }

    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `Analysis request failed with status ${response.status}`);
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Confirm the document type and trigger extraction.
 */
export async function confirmType(
  documentId: string,
  documentType: string,
): Promise<ConfirmTypeResponse> {
  const url = `${API_BASE_URL}/api/v1/documents/${documentId}/confirm-type`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ANALYSIS_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_type: documentType }),
      signal: controller.signal,
    });

    if (response.ok) {
      return (await response.json()) as ConfirmTypeResponse;
    }

    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `Confirm type failed with status ${response.status}`);
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Run the full analysis pipeline for a document:
 * 1. Start analysis (type inference)
 * 2. Auto-confirm the suggested type
 *
 * After this completes, the knowledge model should be available.
 * If analysis already exists, attempts to continue from where it left off.
 */
export async function runFullAnalysis(documentId: string): Promise<void> {
  // Step 1: Start analysis (type inference)
  let session: AnalyzeResponse | null = null;
  try {
    session = await startAnalysis(documentId);
  } catch (err) {
    // If analysis already exists, try to continue with confirm-type
    if (err instanceof Error && err.message.includes('already exists')) {
      // Try confirming as generic in case session is stuck in awaiting_confirmation
      try {
        await confirmType(documentId, 'generic');
      } catch {
        // If confirm also fails, the KM might already be ready — let polling handle it
      }
      return;
    }
    throw err;
  }

  // Step 2: Auto-confirm the suggested type (or default to 'generic')
  const typeToConfirm = session.suggested_type || 'generic';
  await confirmType(documentId, typeToConfirm);
}
