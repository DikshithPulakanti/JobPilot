"use client";

import { useEffect, useState } from "react";
import { MetricCard } from "./MetricCard";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Metrics = {
  jobs_total: number;
  jobs_scored: number;
  applications_total: number;
  rec_apply: number;
  rec_review: number;
  rec_skip: number;
};

const empty: Metrics = {
  jobs_total: 0,
  jobs_scored: 0,
  applications_total: 0,
  rec_apply: 0,
  rec_review: 0,
  rec_skip: 0,
};

export function DashboardMetrics() {
  const [m, setM] = useState<Metrics>(empty);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/metrics`);
        if (!res.ok) return;
        const data = (await res.json()) as Metrics;
        if (!cancelled) setM({ ...empty, ...data });
      } catch {
        /* backend down */
      }
    };

    load();
    const t = setInterval(load, 8000);

    const es = new EventSource(`${API_BASE}/events`);
    const onJobpilot = () => {
      void load();
    };
    es.addEventListener("jobpilot", onJobpilot as EventListener);

    return () => {
      cancelled = true;
      clearInterval(t);
      es.removeEventListener("jobpilot", onJobpilot as EventListener);
      es.close();
    };
  }, []);

  return (
    <section className="grid gap-4 md:grid-cols-3">
      <MetricCard label="Jobs tracked" value={String(m.jobs_total)} hint="Rows in jobs table" />
      <MetricCard label="Jobs scored" value={String(m.jobs_scored)} hint="Fit score present" />
      <MetricCard
        label="Applications"
        value={String(m.applications_total)}
        hint="Saved application rows"
      />
    </section>
  );
}
