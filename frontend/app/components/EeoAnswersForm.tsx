"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Answers = {
  race_ethnicity?: string;
  gender?: string;
  veteran_status?: string;
  disability_status?: string;
  work_authorization?: string;
  legally_authorized?: string;
  requires_sponsorship?: string;
  pronouns?: string;
};

/* ── Option lists ─────────────────────────────────────────────── */

const RACE_OPTIONS = [
  "Hispanic or Latino",
  "White (Not Hispanic or Latino)",
  "Black or African American (Not Hispanic or Latino)",
  "Asian (Not Hispanic or Latino)",
  "Native Hawaiian or Other Pacific Islander (Not Hispanic or Latino)",
  "American Indian or Alaska Native (Not Hispanic or Latino)",
  "Two or More Races (Not Hispanic or Latino)",
  "Decline to answer",
];

const GENDER_OPTIONS = [
  "Male",
  "Female",
  "Non-binary / Third gender",
  "Prefer to self-describe",
  "Decline to answer",
];

const VETERAN_OPTIONS = [
  "Not a veteran",
  "Veteran (honorably discharged)",
  "Active duty wartime or campaign badge veteran",
  "Disabled veteran",
  "Recently separated veteran (within 3 years)",
  "Armed Forces Service Medal veteran",
  "Protected veteran (VEVRAA)",
  "Decline to answer",
];

const DISABILITY_OPTIONS = [
  "No, I do not have a disability",
  "Yes, I have a disability (or previously had one)",
  "Decline to answer",
];

const WORK_AUTH_OPTIONS = [
  "US Citizen",
  "Lawful Permanent Resident (Green Card)",
  "H-1B visa holder",
  "OPT – Optional Practical Training",
  "STEM OPT extension",
  "CPT – Curricular Practical Training",
  "TN visa (Canada / Mexico)",
  "E-3 visa (Australia)",
  "O-1 visa (extraordinary ability)",
  "L-1 visa (intracompany transfer)",
  "Other work-authorized visa",
  "Decline to answer",
];

const YES_NO_OPTIONS = ["Yes", "No", "Decline to answer"];

const SPONSORSHIP_OPTIONS = [
  "No – I do not require sponsorship now or in the future",
  "No – I do not require sponsorship now, but may in the future",
  "Yes – I currently require sponsorship",
  "Yes – I will require sponsorship in the future",
  "Decline to answer",
];

const PRONOUN_OPTIONS = [
  "He / Him / His",
  "She / Her / Hers",
  "They / Them / Theirs",
  "Ze / Zir / Zirs",
  "Prefer not to say",
];

/* ── SelectField helper ───────────────────────────────────────── */

function SelectField({
  label,
  hint,
  fieldKey,
  value,
  options,
  onChange,
}: {
  label: string;
  hint?: string;
  fieldKey: keyof Answers;
  value: string;
  options: string[];
  onChange: (key: keyof Answers, val: string) => void;
}) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      {label}
      {hint ? <span className="ml-1 font-normal text-slate-400">({hint})</span> : null}
      <select
        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
        value={value}
        onChange={(e) => onChange(fieldKey, e.target.value)}
      >
        <option value="">— select —</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}

/* ── Main component ───────────────────────────────────────────── */

export function EeoAnswersForm() {
  const [answers, setAnswers] = useState<Answers>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/candidate/latest`);
      if (res.status === 404) {
        setAnswers({});
        setErr("Save a resume first (Resume & preferences tab) before filling EEO answers.");
        return;
      }
      if (!res.ok) {
        setErr(`HTTP ${res.status}`);
        return;
      }
      const data = (await res.json()) as { application_answers?: Answers };
      setAnswers((data.application_answers as Answers) || {});
    } catch {
      setErr("Could not reach API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onField = (key: keyof Answers, val: string) => {
    setAnswers((prev) => ({ ...prev, [key]: val }));
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);
    setErr(null);
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/candidate/application-answers`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) {
        setErr(typeof data.detail === "string" ? data.detail : "Save failed");
        return;
      }
      setMsg(
        "Answers saved. These are used when auto-filling standard EEO, veteran, disability, and work-authorization questions. Company-specific essays are left blank for you to complete.",
      );
    } catch {
      setErr("Network error.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-slate-600">Loading saved answers…</p>;
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Application & EEO answers</h2>
      <p className="mt-1 text-sm text-slate-600">
        Fill once. JobPilot uses these standard answers when auto-filling EEO, veteran, disability,
        and work-authorization fields across all applications.{" "}
        <strong className="font-medium text-slate-800">
          "Why this company?" and other role-specific essays are left blank
        </strong>{" "}
        for you to review and complete before submitting.
      </p>

      <form onSubmit={save} className="mt-5 flex max-w-2xl flex-col gap-5">
        {/* ── EEO section ── */}
        <fieldset className="rounded-lg border border-slate-100 p-4">
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            EEO / Demographic
          </legend>
          <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <SelectField
              label="Race / Ethnicity"
              hint="EEOC self-identification"
              fieldKey="race_ethnicity"
              value={answers.race_ethnicity ?? ""}
              options={RACE_OPTIONS}
              onChange={onField}
            />
            <SelectField
              label="Gender"
              fieldKey="gender"
              value={answers.gender ?? ""}
              options={GENDER_OPTIONS}
              onChange={onField}
            />
            <SelectField
              label="Pronouns"
              hint="optional"
              fieldKey="pronouns"
              value={answers.pronouns ?? ""}
              options={PRONOUN_OPTIONS}
              onChange={onField}
            />
          </div>
        </fieldset>

        {/* ── Veteran & disability ── */}
        <fieldset className="rounded-lg border border-slate-100 p-4">
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Veteran & Disability
          </legend>
          <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <SelectField
              label="Veteran status"
              hint="VEVRAA"
              fieldKey="veteran_status"
              value={answers.veteran_status ?? ""}
              options={VETERAN_OPTIONS}
              onChange={onField}
            />
            <SelectField
              label="Disability status"
              hint="Section 503"
              fieldKey="disability_status"
              value={answers.disability_status ?? ""}
              options={DISABILITY_OPTIONS}
              onChange={onField}
            />
          </div>
        </fieldset>

        {/* ── Work authorization ── */}
        <fieldset className="rounded-lg border border-slate-100 p-4">
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Work Authorization
          </legend>
          <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <SelectField
                label="Work authorization / visa status"
                fieldKey="work_authorization"
                value={answers.work_authorization ?? ""}
                options={WORK_AUTH_OPTIONS}
                onChange={onField}
              />
            </div>
            <SelectField
              label="Legally authorized to work in the US?"
              fieldKey="legally_authorized"
              value={answers.legally_authorized ?? ""}
              options={YES_NO_OPTIONS}
              onChange={onField}
            />
            <SelectField
              label="Require visa sponsorship?"
              fieldKey="requires_sponsorship"
              value={answers.requires_sponsorship ?? ""}
              options={SPONSORSHIP_OPTIONS}
              onChange={onField}
            />
          </div>
        </fieldset>

        <button
          type="submit"
          disabled={saving}
          className="w-fit rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save answers"}
        </button>
      </form>

      {msg ? <p className="mt-3 text-sm text-green-700">{msg}</p> : null}
      {err ? <p className="mt-3 text-sm text-red-600">{err}</p> : null}
    </section>
  );
}
