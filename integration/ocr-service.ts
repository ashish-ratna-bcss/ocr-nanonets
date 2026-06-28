/**
 * OCR Service API Client
 * Hand-crafted for integration with Next.js and React applications.
 */

export interface OCRJobStatus {
  id: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  total_pages: number | null;
  pages_done: number;
  error: string | null;
  created_at: string;
}

export interface SubmitJobResponse {
  job_id: string;
  status: 'queued' | 'processing';
  total_pages: number | null;
}

export class OCRServiceClient {
  private baseUrl: string;
  private apiKey: string;

  constructor(baseUrl: string = '/api/ocr', apiKey?: string) {
    // If running in Next.js, you can proxy requests to avoid CORS, or call the backend directly
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.apiKey = apiKey || '';
  }

  private getHeaders(isMultipart = false): HeadersInit {
    const headers: Record<string, string> = {};
    if (this.apiKey) {
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    }
    if (!isMultipart) {
      headers['Content-Type'] = 'application/json';
    }
    return headers;
  }

  /**
   * Submit a PDF or Image for OCR transcription
   */
  async submitJob(
    file: File,
    options?: { dpi?: number; caseContext?: string; corrections?: Record<string, string> }
  ): Promise<SubmitJobResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (options?.dpi) {
      formData.append('dpi', options.dpi.toString());
    }
    if (options?.caseContext) {
      formData.append('case_context', options.caseContext);
    }
    if (options?.corrections) {
      formData.append('corrections', JSON.stringify(options.corrections));
    }

    const response = await fetch(`${this.baseUrl}/jobs`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: formData,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.detail || `Failed to submit OCR job: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get the current status of an OCR job
   */
  async getJobStatus(jobId: string): Promise<OCRJobStatus> {
    const response = await fetch(`${this.baseUrl}/jobs/${jobId}`, {
      method: 'GET',
      headers: this.getHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job status: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Retrieve the final transcribed Markdown content
   */
  async getJobResult(jobId: string): Promise<string> {
    const response = await fetch(`${this.baseUrl}/jobs/${jobId}/result`, {
      method: 'GET',
      headers: this.getHeaders(),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch job result: ${response.statusText}`);
    }

    return response.text();
  }

  /**
   * Helper method to poll a job until completion
   */
  async pollJobUntilDone(
    jobId: string,
    onProgress?: (status: OCRJobStatus) => void,
    intervalMs = 2000,
    timeoutMs = 600000 // 10 minutes default
  ): Promise<string> {
    const startTime = Date.now();

    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          if (Date.now() - startTime > timeoutMs) {
            reject(new Error('OCR transcription timed out.'));
            return;
          }

          const job = await this.getJobStatus(jobId);
          if (onProgress) {
            onProgress(job);
          }

          if (job.status === 'done') {
            const markdown = await this.getJobResult(jobId);
            resolve(markdown);
          } else if (job.status === 'failed') {
            reject(new Error(job.error || 'OCR job execution failed on the server.'));
          } else {
            setTimeout(poll, intervalMs);
          }
        } catch (error) {
          reject(error);
        }
      };

      setTimeout(poll, intervalMs);
    });
  }
}
