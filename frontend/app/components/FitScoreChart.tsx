"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const data = [
  { role: "MLE", score: 82 },
  { role: "SWE", score: 74 },
  { role: "Data", score: 68 },
  { role: "PM", score: 55 },
];

export function FitScoreChart() {
  return (
    <div className="h-72 w-full rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3">
        <p className="text-sm font-semibold text-slate-900">Fit score preview</p>
        <p className="text-xs text-slate-500">Sample distribution by role family.</p>
      </div>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="role" stroke="#94a3b8" fontSize={12} />
          <YAxis stroke="#94a3b8" fontSize={12} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip
            cursor={{ fill: "rgba(37, 99, 235, 0.08)" }}
            formatter={(value: number) => [`${value}%`, "Fit"]}
          />
          <Bar dataKey="score" fill="#2563eb" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
