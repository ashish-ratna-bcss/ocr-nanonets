# React & Next.js API Integration Guide

This directory contains the files needed to seamlessly integrate the OCR service into your React or Next.js application.

## Files Included
1. `ocr-service.ts`: A raw TypeScript client handling job submission (`POST /jobs`), polling status (`GET /jobs/{id}`), and result retrieval (`GET /jobs/{id}/result`).
2. `useOcr.ts`: A React custom hook wrapping the client to manage state, errors, progress percentages, and async polling logic.
3. `OcrDashboard.tsx`: A self-contained, interactive frontend dashboard styled with Tailwind CSS, supporting drag-and-drop file upload, advanced configs (DPI, Context, Corrections), dynamic progress tracking, and markdown rendering.

---

## 1. Quick Integration

Copy `ocr-service.ts`, `useOcr.ts`, and `OcrDashboard.tsx` into your React/Next.js project (e.g., in a `components/ocr/` folder).

Then, instantiate the dashboard component in any of your pages:

```tsx
import { OcrDashboard } from '@/components/ocr/OcrDashboard';

export default function Page() {
  return (
    <OcrDashboard 
      apiBaseUrl="http://98.86.63.69/ocr" // Your AWS API domain
      apiKey="f379241418da1092837aaa6b7138e850e4b99b1b2f88ba90d527e6a0b4b4a600"
    />
  );
}
```

---

## 2. Setting Up an API Proxy (Recommended to Avoid CORS)

If your frontend is running on a different domain or port than `98.86.63.69` and you want to avoid browser CORS issues or hide your backend API key, you can proxy requests through your Next.js server:

### For Next.js (App Router - API Routes)
Create a file at `src/app/api/ocr/[[...path]]/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = 'http://98.86.63.69/ocr';
const API_KEY = 'f379241418da1092837aaa6b7138e850e4b99b1b2f88ba90d527e6a0b4b4a600';

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  
  const response = await fetch(`${BACKEND_URL}/jobs`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
    },
    body: formData,
  });

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function GET(req: NextRequest, { params }: { params: { path?: string[] } }) {
  const subpath = params.path?.join('/') || '';
  
  const response = await fetch(`${BACKEND_URL}/${subpath}`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
    },
  });

  if (subpath.endsWith('/result')) {
    const text = await response.text();
    return new NextResponse(text, { status: response.status });
  }

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
```

Now, in your frontend, you can pass `/api/ocr` as the `apiBaseUrl` and leave `apiKey` blank since Next.js will append the authorization header:
```tsx
<OcrDashboard apiBaseUrl="/api/ocr" />
```

---

## 3. Direct Client Integration (Custom UI)

If you prefer to build your own custom React UI instead of using the pre-built `OcrDashboard`, you can leverage the `useOcr` hook directly:

```tsx
import { useOcr } from './useOcr';

export function CustomOcrUI() {
  const { runOcr, status, progressPercent, result, error } = useOcr({
    baseUrl: 'http://98.86.63.69/ocr',
    apiKey: 'f379241418da1092837aaa6b7138e850e4b99b1b2f88ba90d527e6a0b4b4a600',
    dpi: 150,
  });

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) runOcr(file);
  };

  return (
    <div>
      <input type="file" onChange={handleUpload} />
      <p>Status: {status}</p>
      <p>Progress: {progressPercent}%</p>
      {error && <p className="text-red-500">Error: {error}</p>}
      {result && <pre>{result}</pre>}
    </div>
  );
}
```
