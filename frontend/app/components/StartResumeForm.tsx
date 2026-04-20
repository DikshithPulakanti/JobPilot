"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Preferences = {
  work_type: string;
  job_type: string;
  experience_level: string;
  target_role: string;
  min_salary: string;
  industry: string;
  company_size: string;
};

const WORK_TYPES = ["Remote", "Hybrid", "On-site", "Flexible / No preference"];
const JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship", "Freelance"];
const EXPERIENCE_LEVELS = [
  "Internship",
  "Entry Level (0–2 yrs)",
  "Mid Level (2–5 yrs)",
  "Senior (5–8 yrs)",
  "Lead / Staff",
  "Principal / Distinguished",
  "Manager / Director",
];
const MIN_SALARIES = [
  "No preference",
  "$40,000+",
  "$60,000+",
  "$80,000+",
  "$100,000+",
  "$120,000+",
  "$150,000+",
  "$180,000+",
  "$200,000+",
];
const INDUSTRIES = [
  "Any industry",
  "Software / Technology",
  "Finance / Fintech",
  "Healthcare / Biotech",
  "E-commerce / Retail",
  "Gaming",
  "EdTech / Education",
  "Government / Defense",
  "Media / Entertainment",
  "Startup / Early-stage",
  "Consulting",
  "Automotive / Hardware",
];
const COMPANY_SIZES = [
  "Any size",
  "Startup (< 50 employees)",
  "Small (50–200)",
  "Mid-size (200–1,000)",
  "Large (1,000–5,000)",
  "Enterprise (5,000+)",
];

function serializePreferences(prefs: Preferences): string {
  const parts: string[] = [];
  if (prefs.target_role) parts.push(`Target role: ${prefs.target_role}`);
  if (prefs.work_type) parts.push(`Work type: ${prefs.work_type}`);
  if (prefs.job_type) parts.push(`Job type: ${prefs.job_type}`);
  if (prefs.experience_level) parts.push(`Experience level: ${prefs.experience_level}`);
  if (prefs.min_salary && prefs.min_salary !== "No preference")
    parts.push(`Minimum salary: ${prefs.min_salary}`);
  if (prefs.industry && prefs.industry !== "Any industry")
    parts.push(`Preferred industry: ${prefs.industry}`);
  if (prefs.company_size && prefs.company_size !== "Any size")
    parts.push(`Company size: ${prefs.company_size}`);
  return parts.join(". ");
}

function SelectField({
  label,
  value,
  onChange,
  options,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  options: string[];
  placeholder: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <select
        value={value}
        onChange={onChange}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="">{placeholder}</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}

export function StartResumeForm() {
  const [file, setFile] = useState<File | null>(null);
  const [prefs, setPrefs] = useState<Preferences>({
    work_type: "",
    job_type: "",
    experience_level: "",
    target_role: "",
    min_salary: "",
    industry: "",
    company_size: "",
  });
  const [runPipeline, setRunPipeline] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setField =
    (key: keyof Preferences) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      setPrefs((prev) => ({ ...prev, [key]: e.target.value }));
    };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setError(null);
    if (!file) {
      setError("Choose a resume file (PDF or .txt).");
      return;
    }
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("resume", file);
      fd.append("preferences", serializePreferences(prefs));
      if (runPipeline) fd.append("run_pipeline", "true");

      const res = await fetch(`${API_BASE}/start/upload`, {
        method: "POST",
        body: fd,
      });
      const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      if (!res.ok) {
        const detail = data.detail;
        setError(typeof detail === "string" ? detail : res.statusText || "Request failed");
        return;
      }
      const id = data.id;
      setMessage(
        `Profile saved to database${id != null ? ` (ID: ${String(id)})` : ""}.` +
          (data.pipeline === "started"
            ? " Pipeline started — discovered jobs will appear in the Review tab shortly."
            : ' Click "Run full pipeline" or go to the Review tab to find and score jobs.'),
      );
    } catch {
      setError("Could not reach the API. Is the backend running on port 8000?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">Resume & job preferences</h2>
      <p className="mt-1 text-sm text-slate-600">
        Upload your resume and set your preferences. JobPilot saves your profile to the database and
        uses it to discover, score, and auto-fill job applications.
      </p>

      <form onSubmit={submit} className="mt-5 flex flex-col gap-6">
        {/* Resume upload */}
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Resume file{" "}
            <span className="font-normal text-slate-400">(PDF or .txt, max 5 MB)</span>
          </label>
          <input
            type="file"
            accept=".pdf,.txt,.text,.md,application/pdf,text/plain"
            className="mt-1 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {/* Job preferences grid */}
        <div>
          <p className="mb-1 text-sm font-semibold text-slate-800">Job preferences</p>
          <p className="mb-3 text-xs text-slate-500">
            These drive job discovery and scoring — the more you fill in, the better the matches.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {/* Target role — text input */}
            <div className="flex flex-col gap-1 sm:col-span-2 lg:col-span-1">
              <label className="text-sm font-medium text-slate-700">Target role / title</label>
              <input
                type="text"
                value={prefs.target_role}
                onChange={setField("target_role")}
                placeholder="e.g. Software Engineer, Data Scientist"
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <SelectField
              label="Work type"
              value={prefs.work_type}
              onChange={setField("work_type")}
              options={WORK_TYPES}
              placeholder="Select work type"
            />
            <SelectField
              label="Job type"
              value={prefs.job_type}
              onChange={setField("job_type")}
              options={JOB_TYPES}
              placeholder="Select job type"
            />
            <SelectField
              label="Experience level"
              value={prefs.experience_level}
              onChange={setField("experience_level")}
              options={EXPERIENCE_LEVELS}
              placeholder="Select level"
            />
            <SelectField
              label="Minimum salary"
              value={prefs.min_salary}
              onChange={setField("min_salary")}
              options={MIN_SALARIES}
              placeholder="Select salary range"
            />
            <SelectField
              label="Preferred industry"
              value={prefs.industry}
              onChange={setField("industry")}
              options={INDUSTRIES}
              placeholder="Select industry"
            />
            <SelectField
              label="Company size"
              value={prefs.company_size}
              onChange={setField("company_size")}
              options={COMPANY_SIZES}
              placeholder="Select company size"
            />
          </div>
        </div>

        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={runPipeline}
            onChange={(e) => setRunPipeline(e.target.checked)}
            className="rounded border-slate-300"
          />
          Run full pipeline after saving (discover → score → apply if enabled in env)
        </label>

        <button
          type="submit"
          disabled={loading}
          className="inline-flex w-fit items-center justify-center rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Saving…" : "Save profile"}
        </button>
      </form>

      {message ? <p className="mt-3 text-sm text-green-700">{message}</p> : null}
      {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
    </section>
  );
}
