import { ApplicationTable } from "./components/ApplicationTable";
import { DashboardMetrics } from "./components/DashboardMetrics";
import { FitScoreChart } from "./components/FitScoreChart";
import { LiveFeed } from "./components/LiveFeed";

export default function Home() {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
      <header className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-600">JobPilot</p>
        <h1 className="text-3xl font-bold text-slate-900">Application command center</h1>
        <p className="max-w-3xl text-base text-slate-600">
          Monitor orchestration progress, fit scores, and downstream applications as agents discover roles and
          prepare submissions.
        </p>
      </header>

      <DashboardMetrics />

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="min-h-[28rem]">
          <LiveFeed />
        </div>
        <FitScoreChart />
      </section>

      <ApplicationTable />
    </main>
  );
}
