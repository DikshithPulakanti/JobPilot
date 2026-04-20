"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { FitMatchRationale, type FitDetails } from "./FitMatchRationale";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type JobRow = {
  id: number;
  title: string;
  company: string;
  description: string | null;
  fit_score: number | null;
  recommendation: string | null;
  url: string;
  fit_details?: FitDetails | null;
  terms_snippet?: string | null;
};

export function JobReviewAndApply() {
  const [rows, setRows] = useState<JobRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [queueing, setQueueing] = useState(false);
  const [queueMsg, setQueueMsg] = useState<string | null>(null);

  const scored = useMemo(
    () => rows.filter((r) => r.fit_score != null).sort((a, b) => (b.fit_score ?? 0) - (a.fit_score ?? 0)),
    [rows],
  );

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/jobs?limit=100`);
      if (!res.ok) {
        setErr(`HTTP ${res.status}`);
        return;
      }
      const data = (await res.json()) as JobRow[];
      setRows(data);
      setErr(null);
    } catch {
      setErr("Could not reach API");
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(load, 15000);
    const es = new EventSource(`${API_BASE}/events`);
    const bump = () => void load();
    es.addEventListener("jobpilot", bump as EventListener);
    return () => {
      clearInterval(t);
      es.removeEventListener("jobpilot", bump as EventListener);
      es.close();
    };
  }, [load]);

  const toggleSelect = (id: number, rec: string | null) => {
    const r = (rec || "").toLowerCase();
    if (r !== "apply" && r !== "review") return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllRecommendations = () => {
    setSelected(new Set(scored.filter((j) => /apply|review/i.test(j.recommendation || "")).map((j) => j.id)));
  };

  const clearSelection = () => setSelected(new Set());

  const runApply = async () => {
    const ids = [...selected];
    if (ids.length === 0) {
      setQueueMsg("Select at least one job with Apply or Review.");
      return;
    }
    setQueueing(true);
    setQueueMsg(null);
    try {
      const res = await fetch(`${API_BASE}/apply/selected`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: ids }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) {
        setQueueMsg(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
        return;
      }
      setQueueMsg(
        `Queued ${ids.length} job(s). A Chromium window will open for each (fill-only; you submit manually).`,
      );
    } catch {
      setQueueMsg("Could not reach API.");
    } finally {
      setQueueing(false);
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-semibold text-slate-900">Review jobs & queue apply</p>
        <p className="text-xs text-slate-500">
          Read fit scores, job description, and any captured terms text. Select rows, then queue the browser
          helper (fill-only, no submit).
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-100"
            onClick={selectAllRecommendations}
          >
            Select all Apply / Review
          </button>
          <button
            type="button"
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-800 hover:bg-slate-100"
            onClick={clearSelection}
          >
            Clear
          </button>
          <button
            type="button"
            disabled={queueing || selected.size === 0}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            onClick={() => void runApply()}
          >
            {queueing ? "Queueing…" : `Fill selected (${selected.size})`}
          </button>
        </div>
        {queueMsg ? <p className="mt-2 text-sm text-slate-700">{queueMsg}</p> : null}
        {err ? <p className="mt-1 text-xs text-amber-800">{err}</p> : null}
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-2 py-3" scope="col">
                Pick
              </th>
              <th className="px-4 py-3" scope="col">
                Company
              </th>
              <th className="px-4 py-3" scope="col">
                Role
              </th>
              <th className="px-4 py-3" scope="col">
                Rec
              </th>
              <th className="px-4 py-3" scope="col">
                Fit
              </th>
              <th className="px-4 py-3" scope="col">
                Details
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {scored.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-slate-500" colSpan={6}>
                  No scored jobs yet. Run the pipeline after saving your profile.
                </td>
              </tr>
            ) : (
              scored.map((row) => {
                const expanded = openId === row.id;
                const canPick = /apply|review/i.test(row.recommendation || "");
                return (
                  <Fragment key={row.id}>
                    <tr className="hover:bg-slate-50/80">
                      <td className="px-2 py-3 text-center">
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded border-slate-300"
                          checked={selected.has(row.id)}
                          disabled={!canPick}
                          onChange={() => toggleSelect(row.id, row.recommendation)}
                          title={canPick ? "Include in fill queue" : "Skip-only: not selectable"}
                        />
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-900">{row.company}</td>
                      <td className="px-4 py-3 text-slate-700">{row.title}</td>
                      <td className="px-4 py-3 text-slate-600">{row.recommendation ?? "—"}</td>
                      <td className="px-4 py-3 tabular-nums text-slate-900">
                        {row.fit_score != null ? `${((row.fit_score / 10) * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          className="text-sm font-medium text-blue-600 hover:text-blue-800"
                          onClick={() => setOpenId(expanded ? null : row.id)}
                        >
                          {expanded ? "Hide" : "Description, terms & rationale"}
                        </button>
                      </td>
                    </tr>
                    {expanded ? (
                      <tr className="bg-slate-50/50">
                        <td className="px-4 py-4" colSpan={6}>
                          {row.description ? (
                            <div className="mb-4">
                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                                Job description
                              </p>
                              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-100 bg-white p-3 text-xs text-slate-700">
                                {row.description}
                              </pre>
                            </div>
                          ) : (
                            <p className="mb-4 text-xs text-slate-500">No job description stored for this listing.</p>
                          )}
                          {row.terms_snippet ? (
                            <div className="mb-4">
                              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                                Terms / legal text (best-effort from apply page)
                              </p>
                              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-xs text-slate-800">
                                {row.terms_snippet}
                              </pre>
                            </div>
                          ) : (
                            <p className="mb-4 text-xs text-slate-500">
                              Terms not captured yet — they appear after you run fill for this job (we scrape the
                              application view).
                            </p>
                          )}
                          <FitMatchRationale details={row.fit_details} />
                          {row.url ? (
                            <p className="mt-3 text-xs">
                              <a
                                href={row.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:underline"
                              >
                                Open listing on Indeed
                              </a>
                            </p>
                          ) : null}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
