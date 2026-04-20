"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Rec = { apply: number; review: number; skip: number };

export function FitScoreChart() {
  const [rec, setRec] = useState<Rec>({ apply: 0, review: 0, skip: 0 });
  const [hist, setHist] = useState<{ name: string; count: number }[]>([]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [r, h] = await Promise.all([
          fetch(`${API_BASE}/stats/recommendations`),
          fetch(`${API_BASE}/stats/fit-histogram`),
        ]);
        if (r.ok && !cancelled) {
          setRec((await r.json()) as Rec);
        }
        if (h.ok && !cancelled) {
          const rows = (await h.json()) as { bucket_label: string; count: number }[];
          setHist(rows.map((x) => ({ name: x.bucket_label, count: Number(x.count) })));
        }
      } catch {
        /* ignore */
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

  const chartData = useMemo(() => {
    if (hist.length > 0) return hist;
    return [
      { name: "apply", count: rec.apply },
      { name: "review", count: rec.review },
      { name: "skip", count: rec.skip },
    ];
  }, [hist, rec]);

  return (
    <div className="h-72 w-full rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3">
        <p className="text-sm font-semibold text-slate-900">Fit & recommendations</p>
        <p className="text-xs text-slate-500">
          Score buckets when scored jobs exist; otherwise apply / review / skip counts.
        </p>
      </div>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
          <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: "rgba(37, 99, 235, 0.08)" }}
            formatter={(value: number) => [value, "Jobs"]}
          />
          <Bar dataKey="count" fill="#2563eb" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
