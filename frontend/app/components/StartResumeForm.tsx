"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function StartResumeForm() {
  const [file, setFile] = useState<File | null>(null);
  const [preferences, setPreferences] = useState("");
  const [runPipeline, setRunPipeline] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setError(null);
    if (!file) {
      setError("Choose a resume file (PDF or .txt).");
      return;
    }
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("resume", file);
      fd.append("preferences", preferences);
      if (runPipeline) {
        fd.append("run_pipeline", "true");
      }
      const res = await fetch(`${API_BASE}/start/upload`, {
        method: "POST",
        body: fd,
      });
      const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      if (!res.ok) {
        const detail = data.detail;
        setError(typeof detail === "string" ? detail : res.statusText || "Request failed");
        return;
      }
      const id = data.id;
      const pipeline = data.pipeline;
      setMessage(
        `Profile saved${id != null ? ` (candidate id: ${String(id)})` : ""}.` +
          (pipeline === "started" ? " Pipeline started in the background." : ""),
      );
    } catch {
      setError("Could not reach the API. Is the backend running on port 8000?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Upload resume</h2>
      <p className="mt-1 text-sm text-slate-600">
        PDF (text layer or scanned — we OCR when needed if Tesseract is installed) or plain .txt — max 5 MB.
        Same flow as{" "}
        <code className="rounded bg-slate-100 px-1 text-xs">POST /start</code> with JSON.
      </p>
      <form onSubmit={submit} className="mt-4 flex flex-col gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700">Resume file</label>
          <input
            type="file"
            accept=".pdf,.txt,.text,.md,application/pdf,text/plain"
            className="mt-1 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700">Job preferences (optional)</label>
          <textarea
            value={preferences}
            onChange={(e) => setPreferences(e.target.value)}
            rows={3}
            placeholder="e.g. Remote US, backend/Python roles, $120k+"
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={runPipeline}
            onChange={(e) => setRunPipeline(e.target.checked)}
            className="rounded border-slate-300"
          />
          Run full pipeline after saving (discover → score → apply if enabled in env)
        </label>
        <button
          type="submit"
          disabled={loading}
          className="inline-flex w-fit items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save profile"}
        </button>
      </form>
      {message ? <p className="mt-3 text-sm text-green-700">{message}</p> : null}
      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
    </section>
  );
}
