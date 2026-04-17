import { ApplicationTable } from "./components/ApplicationTable";
import { FitScoreChart } from "./components/FitScoreChart";
import { LiveFeed } from "./components/LiveFeed";
import { MetricCard } from "./components/MetricCard";

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

      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Active runs" value="1" hint="Background orchestrations" />
        <MetricCard label="Jobs tracked" value="128" hint="Across boards & referrals" />
        <MetricCard label="Avg. fit" value="78%" hint="Rolling 7-day window" />
      </section>

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
