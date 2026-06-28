import React, { useState, useRef } from 'react';
import { useOcr } from './useOcr';

interface OcrDashboardProps {
  apiBaseUrl?: string; // e.g. "https://your-domain.com/ocr"
  apiKey?: string;     // Your API token
}

export const OcrDashboard: React.FC<OcrDashboardProps> = ({
  apiBaseUrl = 'https://98.86.63.69/ocr', // Matches Nginx proxy setup
  apiKey = 'f379241418da1092837aaa6b7138e850e4b99b1b2f88ba90d527e6a0b4b4a600',
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dpi, setDpi] = useState<number>(150);
  const [caseContext, setCaseContext] = useState<string>('');
  const [correctionsRaw, setCorrectionsRaw] = useState<string>('');
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const parsedCorrections = React.useMemo(() => {
    if (!correctionsRaw.trim()) return undefined;
    try {
      return JSON.parse(correctionsRaw);
    } catch {
      return undefined;
    }
  }, [correctionsRaw]);

  const {
    runOcr,
    reset,
    status,
    jobId,
    pagesDone,
    totalPages,
    progressPercent,
    error,
    result,
    isProcessing,
  } = useOcr({
    baseUrl: apiBaseUrl,
    apiKey: apiKey,
    dpi,
    caseContext,
    corrections: parsedCorrections,
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedFile) {
      runOcr(selectedFile);
    }
  };

  const copyToClipboard = () => {
    if (result) {
      navigator.clipboard.writeText(result);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans p-6 md:p-12">
      <div className="max-w-5xl mx-auto space-y-8">
        
        {/* Header */}
        <header className="border-b border-slate-800 pb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
              Anti-Corruption Bureau (ACB) OCR Portal
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              High-accuracy scanned case file transcription service with VRAM autoshutoff
            </p>
          </div>
          <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-full px-3 py-1 text-xs text-slate-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Server: Connected
          </div>
        </header>

        {/* Upload & Form Section */}
        {status === 'idle' && (
          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* File Dropzone */}
            <div className="md:col-span-2 space-y-4">
              <label className="block text-sm font-semibold text-slate-300">Select Case Document (PDF / Image)</label>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className="group border-2 border-dashed border-slate-700 hover:border-blue-500 bg-slate-800/50 hover:bg-slate-800/80 rounded-2xl p-12 text-center cursor-pointer transition-all duration-300 flex flex-col items-center justify-center min-h-[300px]"
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  accept="application/pdf,image/*"
                  className="hidden"
                />
                
                <svg className="w-16 h-16 text-slate-500 group-hover:text-blue-400 mb-4 transition-colors duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>

                {selectedFile ? (
                  <div className="space-y-2">
                    <p className="text-lg font-bold text-slate-200">{selectedFile.name}</p>
                    <p className="text-sm text-slate-400">{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-lg font-bold text-slate-300 group-hover:text-slate-200">
                      Drag & Drop file here, or click to browse
                    </p>
                    <p className="text-sm text-slate-500">Supports PDF & image uploads up to 100MB</p>
                  </div>
                )}
              </div>
            </div>

            {/* Config & Parameters */}
            <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-6 space-y-6 flex flex-col justify-between">
              <div className="space-y-4">
                <h3 className="text-lg font-bold text-slate-200">Processing Knobs</h3>
                
                {/* DPI Option */}
                <div className="space-y-2">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">Rendering Quality (DPI)</label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setDpi(150)}
                      className={`py-2 rounded-lg text-sm font-semibold transition-all ${
                        dpi === 150 ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                      }`}
                    >
                      150 DPI (Fastest)
                    </button>
                    <button
                      type="button"
                      onClick={() => setDpi(300)}
                      className={`py-2 rounded-lg text-sm font-semibold transition-all ${
                        dpi === 300 ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                      }`}
                    >
                      300 DPI (Best OCR)
                    </button>
                  </div>
                </div>

                {/* Case Context */}
                <div className="space-y-2">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">Case Context (Optional)</label>
                  <textarea
                    value={caseContext}
                    onChange={(e) => setCaseContext(e.target.value)}
                    placeholder="Enter proper nouns (officer names, sections) to aid OCR disambiguation..."
                    className="w-full h-20 bg-slate-900 border border-slate-700 rounded-lg p-2 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 resize-none"
                  />
                </div>

                {/* Corrections JSON */}
                <div className="space-y-2">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">Auto-Corrections JSON (Optional)</label>
                  <textarea
                    value={correctionsRaw}
                    onChange={(e) => setCorrectionsRaw(e.target.value)}
                    placeholder='{ "Mamsi": "Mamidi", "Sadashivapet": "Sadasivapet" }'
                    className="w-full h-20 bg-slate-900 border border-slate-700 rounded-lg p-2 font-mono text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 resize-none"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={!selectedFile}
                className="w-full bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white font-bold py-3 px-6 rounded-xl transition-all shadow-xl shadow-indigo-500/10 disabled:opacity-50 disabled:cursor-not-allowed mt-4"
              >
                Submit Transcription Job
              </button>
            </div>
          </form>
        )}

        {/* Processing State */}
        {isProcessing && (
          <div className="bg-slate-800/30 border border-slate-800 rounded-3xl p-12 text-center max-w-lg mx-auto space-y-6 shadow-2xl">
            <div className="relative w-24 h-24 mx-auto flex items-center justify-center">
              <span className="absolute inset-0 rounded-full border-4 border-slate-700"></span>
              <span className="absolute inset-0 rounded-full border-4 border-blue-500 border-t-transparent animate-spin"></span>
              <span className="text-xl font-bold text-slate-200">{progressPercent}%</span>
            </div>

            <div className="space-y-2">
              <h3 className="text-xl font-bold text-slate-200">
                {status === 'queued' ? 'Queueing Document...' : 'Transcribing Case File...'}
              </h3>
              <p className="text-slate-400 text-sm">
                {totalPages
                  ? `Processing Page ${pagesDone + 1} of ${totalPages}`
                  : 'Bootstrapping GPU Model Context...'}
              </p>
            </div>

            {/* Custom Progress Bar */}
            <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div
                className="bg-gradient-to-r from-blue-500 to-indigo-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              ></div>
            </div>

            <p className="text-xs text-slate-500 italic">
              Note: Model loads dynamically on execution and autoshuts after job completion to save VRAM.
            </p>
          </div>
        )}

        {/* Done / Markdown Presentation */}
        {status === 'done' && result && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-slate-800/40 p-4 border border-slate-800 rounded-xl">
              <div className="text-sm">
                <span className="text-slate-400">Job ID:</span> <span className="font-mono text-blue-400">{jobId}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={copyToClipboard}
                  className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold py-2 px-4 rounded-lg flex items-center gap-1 transition-all"
                >
                  {isCopied ? 'Copied!' : 'Copy Markdown'}
                </button>
                <button
                  onClick={reset}
                  className="bg-blue-600 hover:bg-blue-700 text-xs font-semibold py-2 px-4 rounded-lg text-white transition-all shadow-md"
                >
                  Transcribe Another File
                </button>
              </div>
            </div>

            {/* Markdown Display */}
            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-8 shadow-2xl">
              <div className="prose prose-invert max-w-none prose-sm prose-slate">
                <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-slate-300">
                  {result}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* Failed State */}
        {status === 'failed' && (
          <div className="bg-red-950/30 border border-red-900/50 rounded-2xl p-8 max-w-xl mx-auto space-y-4 shadow-lg text-center">
            <div className="w-12 h-12 rounded-full bg-red-900/30 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-200">Transcription Failed</h3>
              <p className="text-slate-400 text-sm mt-1">{error}</p>
            </div>
            <button
              onClick={reset}
              className="bg-red-900/50 hover:bg-red-900/80 border border-red-800/80 text-white font-semibold py-2 px-6 rounded-lg text-sm transition-all"
            >
              Try Again
            </button>
          </div>
        )}

      </div>
    </div>
  );
};
