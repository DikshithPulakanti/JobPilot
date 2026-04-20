import { DashboardTabs } from "./components/DashboardTabs";

export default function Home() {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
      <header className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-600">JobPilot</p>
        <h1 className="text-3xl font-bold text-slate-900">Application command center</h1>
        <p className="max-w-3xl text-base text-slate-600">
          Save your profile and EEO answers, review scored roles (fit, description, terms when available), then
          queue fill-only apply flows for the jobs you choose. Submission stays with you.
        </p>
      </header>

      <DashboardTabs />
    </main>
  );
}
