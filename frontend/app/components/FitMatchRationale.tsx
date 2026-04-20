"use client";

export type FitDetails = {
  reasoning?: string;
  red_flags?: string[];
  scores?: Record<string, { score?: number; reason?: string }>;
};

const DIM_ORDER = [
  "skills_match",
  "experience_level",
  "location_fit",
  "visa_compatible",
  "salary_likely",
] as const;

const DIM_LABEL: Record<string, string> = {
  skills_match: "Skills match",
  experience_level: "Experience level",
  location_fit: "Location & work mode",
  visa_compatible: "Work authorization",
  salary_likely: "Compensation fit",
};

function dimLabel(key: string): string {
  return DIM_LABEL[key] ?? key.replace(/_/g, " ");
}

export function FitMatchRationale({ details }: { details: FitDetails | null | undefined }) {
  const has =
    details &&
    (details.reasoning?.trim() ||
      (details.red_flags && details.red_flags.length > 0) ||
      (details.scores && Object.keys(details.scores).length > 0));

  if (!has) {
    return (
      <p className="text-sm text-slate-500">
        No match rationale stored yet. It appears after the scorer runs on this job.
      </p>
    );
  }

  const scores = details?.scores ?? {};
  const orderedKeys = [
    ...DIM_ORDER.filter((k) => k in scores),
    ...Object.keys(scores).filter((k) => !DIM_ORDER.includes(k as (typeof DIM_ORDER)[number])),
  ];

  return (
    <div className="space-y-4 text-sm text-slate-700">
      {details?.reasoning?.trim() ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Summary</p>
          <p className="mt-1 leading-relaxed">{details.reasoning.trim()}</p>
        </div>
      ) : null}

      {orderedKeys.length > 0 ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Dimensions</p>
          <ul className="mt-2 space-y-3">
            {orderedKeys.map((key) => {
              const block = scores[key];
              const s = block?.score;
              return (
                <li key={key} className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-medium text-slate-900">{dimLabel(key)}</span>
                    {s != null && !Number.isNaN(Number(s)) ? (
                      <span className="text-xs font-medium tabular-nums text-slate-600">
                        {Number(s)}/10
                      </span>
                    ) : null}
                  </div>
                  {block?.reason?.trim() ? (
                    <p className="mt-1 text-slate-600 leading-relaxed">{block.reason.trim()}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {details?.red_flags && details.red_flags.length > 0 ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">Red flags</p>
          <ul className="mt-1 list-inside list-disc text-amber-900/90">
            {details.red_flags.map((f, i) => (
              <li key={`${i}-${f}`}>{f}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
