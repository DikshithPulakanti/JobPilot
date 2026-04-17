type ApplicationRow = {
  company: string;
  title: string;
  status: string;
  appliedAt: string;
  fitScore: number;
};

const demoRows: ApplicationRow[] = [
  {
    company: "Northwind Labs",
    title: "ML Engineer",
    status: "Draft",
    appliedAt: "—",
    fitScore: 0.82,
  },
  {
    company: "Contoso AI",
    title: "Applied Scientist",
    status: "Queued",
    appliedAt: "—",
    fitScore: 0.76,
  },
];

export function ApplicationTable() {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-semibold text-slate-900">Applications</p>
        <p className="text-xs text-slate-500">Placeholder rows until the API exposes real data.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Company</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Applied</th>
              <th className="px-4 py-3">Fit</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {demoRows.map((row) => (
              <tr key={`${row.company}-${row.title}`} className="hover:bg-slate-50/80">
                <td className="px-4 py-3 font-medium text-slate-900">{row.company}</td>
                <td className="px-4 py-3 text-slate-700">{row.title}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
                    {row.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">{row.appliedAt}</td>
                <td className="px-4 py-3 text-slate-900">{(row.fitScore * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
