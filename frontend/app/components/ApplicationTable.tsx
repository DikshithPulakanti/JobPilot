"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { FitMatchRationale, type FitDetails } from "./FitMatchRationale";

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
  fit_details?: FitDetails | null;
};

type SortKey = "company" | "title" | "recommendation" | "status" | "applied_at" | "fit_score";

function compareForSort(a: Row, b: Row, key: SortKey, dir: "asc" | "desc"): number {
  const mult = dir === "asc" ? 1 : -1;

  if (key === "fit_score") {
    const na = a.fit_score;
    const nb = b.fit_score;
    if (na == null && nb == null) return 0;
    if (na == null) return 1;
    if (nb == null) return -1;
    return (na - nb) * mult;
  }

  const sa =
    key === "company"
      ? a.company
      : key === "title"
        ? a.title
        : key === "recommendation"
          ? a.recommendation ?? ""
          : key === "status"
            ? a.status
            : a.applied_at ?? "";

  const sb =
    key === "company"
      ? b.company
      : key === "title"
        ? b.title
        : key === "recommendation"
          ? b.recommendation ?? ""
          : key === "status"
            ? b.status
            : b.applied_at ?? "";

  const va = sa.toLowerCase();
  const vb = sb.toLowerCase();
  if (va < vb) return -1 * mult;
  if (va > vb) return 1 * mult;
  return 0;
}

function SortTh({
  label,
  columnKey,
  sort,
  onSort,
}: {
  label: string;
  columnKey: SortKey;
  sort: { key: SortKey; dir: "asc" | "desc" };
  onSort: (k: SortKey) => void;
}) {
  const active = sort.key === columnKey;
  return (
    <th
      className="px-4 py-3"
      scope="col"
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        className="inline-flex items-center gap-1 font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-800"
        onClick={() => onSort(columnKey)}
      >
        {label}
        {active ? (
          <span aria-hidden className="text-slate-700">
            {sort.dir === "asc" ? "↑" : "↓"}
          </span>
        ) : null}
      </button>
    </th>
  );
}

export function ApplicationTable() {
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [openApplicationId, setOpenApplicationId] = useState<number | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "applied_at",
    dir: "desc",
  });

  const sortedRows = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const c = compareForSort(a, b, sort.key, sort.dir);
      return c !== 0 ? c : a.application_id - b.application_id;
    });
    return copy;
  }, [rows, sort]);

  const toggleSort = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );
  };

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
              <SortTh label="Company" columnKey="company" sort={sort} onSort={toggleSort} />
              <SortTh label="Role" columnKey="title" sort={sort} onSort={toggleSort} />
              <SortTh label="Recommendation" columnKey="recommendation" sort={sort} onSort={toggleSort} />
              <SortTh label="Status" columnKey="status" sort={sort} onSort={toggleSort} />
              <SortTh label="Applied" columnKey="applied_at" sort={sort} onSort={toggleSort} />
              <SortTh label="Fit" columnKey="fit_score" sort={sort} onSort={toggleSort} />
              <th className="px-4 py-3 font-semibold uppercase tracking-wide text-slate-500" scope="col">
                Why
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-slate-500" colSpan={7}>
                  No applications yet. Run the pipeline after scraping jobs.
                </td>
              </tr>
            ) : (
              sortedRows.map((row) => {
                const expanded = openApplicationId === row.application_id;
                return (
                  <Fragment key={row.application_id}>
                    <tr className="hover:bg-slate-50/80">
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
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          className="text-sm font-medium text-blue-600 hover:text-blue-800"
                          onClick={() =>
                            setOpenApplicationId(expanded ? null : row.application_id)
                          }
                          aria-expanded={expanded}
                        >
                          {expanded ? "Hide" : "Show reasons"}
                        </button>
                      </td>
                    </tr>
                    {expanded ? (
                      <tr className="bg-slate-50/50">
                        <td className="px-4 py-4" colSpan={7}>
                          <FitMatchRationale details={row.fit_details} />
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
