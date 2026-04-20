"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Row = {
  application_id: number;
  job_id: number;
  status: string;
  applied_at: string | null;
  form_filled: boolean | null;
  error_message: string | null;
  title: string;
  company: string;
  fit_score: number | null;
  recommendation: string | null;
  url: string;
};

export function ApplicationTable() {
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/applications?limit=50`);
        if (!res.ok) {
          setErr(`HTTP ${res.status}`);
          return;
        }
        const data = (await res.json()) as Row[];
        if (!cancelled) {
          setRows(data);
          setErr(null);
        }
      } catch {
        if (!cancelled) setErr("Could not reach API (is uvicorn running?)");
      }
    };

    void load();
    const t = setInterval(load, 12000);
    const es = new EventSource(`${API_BASE}/events`);
    const bump = () => void load();
    es.addEventListener("jobpilot", bump as EventListener);
    return () => {
      cancelled = true;
      clearInterval(t);
      es.removeEventListener("jobpilot", bump as EventListener);
      es.close();
    };
  }, []);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-semibold text-slate-900">Applications</p>
        <p className="text-xs text-slate-500">
          From GET /applications · {err ? <span className="text-amber-700">{err}</span> : "Live data"}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Company</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Recommendation</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Applied</th>
              <th className="px-4 py-3">Fit</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-slate-500" colSpan={6}>
                  No applications yet. Run the pipeline after scraping jobs.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.application_id} className="hover:bg-slate-50/80">
                  <td className="px-4 py-3 font-medium text-slate-900">{row.company}</td>
                  <td className="px-4 py-3 text-slate-700">{row.title}</td>
                  <td className="px-4 py-3 text-slate-600">{row.recommendation ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                      {row.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{row.applied_at ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-900">
                    {row.fit_score != null
                      ? `${((row.fit_score / 10) * 100).toFixed(0)}%`
                      : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
