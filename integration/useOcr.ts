import { useState, useCallback } from 'react';
import { OCRServiceClient, OCRJobStatus } from './ocr-service';

export interface UseOcrOptions {
  baseUrl?: string;
  apiKey?: string;
  dpi?: number;
  caseContext?: string;
  corrections?: Record<string, string>;
  pollIntervalMs?: number;
}

export function useOcr(options?: UseOcrOptions) {
  const [status, setStatus] = useState<'idle' | 'queued' | 'processing' | 'done' | 'failed'>('idle');
  const [totalPages, setTotalPages] = useState<number | null>(null);
  const [pagesDone, setPagesDone] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const runOcr = useCallback(async (file: File) => {
    setStatus('queued');
    setError(null);
    setResult(null);
    setTotalPages(null);
    setPagesDone(0);

    const client = new OCRServiceClient(options?.baseUrl, options?.apiKey);

    try {
      // 1. Submit Job
      const submitResponse = await client.submitJob(file, {
        dpi: options?.dpi,
        caseContext: options?.caseContext,
        corrections: options?.corrections,
      });

      setJobId(submitResponse.job_id);

      // 2. Poll status until completion
      const markdown = await client.pollJobUntilDone(
        submitResponse.job_id,
        (job: OCRJobStatus) => {
          setStatus(job.status);
          setTotalPages(job.total_pages);
          setPagesDone(job.pages_done);
        },
        options?.pollIntervalMs || 2000
      );

      setResult(markdown);
      setStatus('done');
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred during transcription.');
      setStatus('failed');
    }
  }, [options]);

  const reset = useCallback(() => {
    setStatus('idle');
    setTotalPages(null);
    setPagesDone(0);
    setError(null);
    setResult(null);
    setJobId(null);
  }, []);

  const progressPercent = totalPages
    ? Math.round((pagesDone / totalPages) * 100)
    : status === 'queued' ? 5 : 0;

  return {
    runOcr,
    reset,
    status,
    jobId,
    totalPages,
    pagesDone,
    progressPercent,
    error,
    result,
    isProcessing: status === 'queued' || status === 'processing',
  };
}
