"use client";

import { useState } from "react";
import { ApplicationTable } from "./ApplicationTable";
import { DashboardMetrics } from "./DashboardMetrics";
import { EeoAnswersForm } from "./EeoAnswersForm";
import { FitScoreChart } from "./FitScoreChart";
import { JobReviewAndApply } from "./JobReviewAndApply";
import { LiveFeed } from "./LiveFeed";
import { StartResumeForm } from "./StartResumeForm";

const tabs = [
  { id: "profile", label: "Resume & preferences" },
  { id: "eoe", label: "Application & EEO answers" },
  { id: "jobs", label: "Review jobs & apply" },
  { id: "dash", label: "Dashboard" },
] as const;

export function DashboardTabs() {
  const [tab, setTab] = useState<(typeof tabs)[number]["id"]>("profile");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={
              tab === t.id
                ? "rounded-t-lg border border-b-0 border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-900"
                : "rounded-t-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "profile" ? (
        <StartResumeForm />
      ) : null}
      {tab === "eoe" ? (
        <EeoAnswersForm />
      ) : null}
      {tab === "jobs" ? (
        <div className="flex flex-col gap-6">
          <JobReviewAndApply />
          <ApplicationTable />
        </div>
      ) : null}
      {tab === "dash" ? (
        <div className="flex flex-col gap-8">
          <DashboardMetrics />
          <section className="grid gap-6 lg:grid-cols-2">
            <div className="min-h-[28rem]">
              <LiveFeed />
            </div>
            <FitScoreChart />
          </section>
        </div>
      ) : null}
    </div>
  );
}
