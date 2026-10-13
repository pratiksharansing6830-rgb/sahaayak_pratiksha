import { useEffect, useState } from "react";
import type { ButtonHTMLAttributes, ChangeEvent, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { ApiError } from "./api";

// ---------- plain-language labels ----------
export const CATEGORY_LABEL: Record<string, string> = {
  EDUCATION: "Education", HEALTHCARE: "Healthcare", NUTRITION: "Nutrition",
  WELLBEING: "Wellbeing", PROTECTION: "Child protection", INCLUSION: "Disability and inclusion",
};
export const NEED_LABEL: Record<string, string> = {
  NEEDS_ASSESSMENT: "Needs a check", PENDING: "Support still to be arranged", REFERRED: "Referral recorded",
  AWAITING_PROVIDER_RESPONSE: "Waiting for the provider", FOLLOW_UP_REQUIRED: "Follow-up needed",
  BARRIER_IDENTIFIED: "Something is blocking support", REVIEW_REQUIRED: "Needs another look",
  SUPPORT_CONFIRMED: "Support confirmed", NOT_REQUIRED: "Marked as not needed", CLOSED: "Closed",
};
export type Tone = "green" | "amber" | "red" | "slate" | "teal" | "blue";
// Green is used ONLY for confirmed support. Open needs never look like success.
export const NEED_TONE: Record<string, Tone> = {
  NEEDS_ASSESSMENT: "slate", PENDING: "amber", REFERRED: "blue", AWAITING_PROVIDER_RESPONSE: "blue",
  FOLLOW_UP_REQUIRED: "amber", BARRIER_IDENTIFIED: "red", REVIEW_REQUIRED: "amber",
  SUPPORT_CONFIRMED: "green", NOT_REQUIRED: "slate", CLOSED: "slate",
};
// Citizen-allowed moves (the server is the authority; this only keeps the menu short).
export const CITIZEN_MOVES: Record<string, string[]> = {
  NEEDS_ASSESSMENT: ["PENDING", "NOT_REQUIRED"],
  PENDING: ["FOLLOW_UP_REQUIRED", "BARRIER_IDENTIFIED", "NOT_REQUIRED", "CLOSED"],
  REFERRED: ["FOLLOW_UP_REQUIRED", "BARRIER_IDENTIFIED", "PENDING", "CLOSED"],
  AWAITING_PROVIDER_RESPONSE: ["FOLLOW_UP_REQUIRED", "BARRIER_IDENTIFIED", "PENDING", "CLOSED"],
  FOLLOW_UP_REQUIRED: ["PENDING", "BARRIER_IDENTIFIED", "NOT_REQUIRED", "CLOSED"],
  BARRIER_IDENTIFIED: ["PENDING", "FOLLOW_UP_REQUIRED", "NOT_REQUIRED", "CLOSED"],
  REVIEW_REQUIRED: ["PENDING", "FOLLOW_UP_REQUIRED", "NOT_REQUIRED", "CLOSED"],
  SUPPORT_CONFIRMED: [], NOT_REQUIRED: ["NEEDS_ASSESSMENT"], CLOSED: ["NEEDS_ASSESSMENT"],
};
export const EDU_LABEL: Record<string, string> = {
  ENROLLED: "Enrolled in school", NOT_ENROLLED: "Not in school", DROPPED_OUT: "Dropped out", UNKNOWN: "Not known",
};
export const label = (s: string) => s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
export const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "-";
export const opt = (s: string) => (s.trim() === "" ? undefined : s.trim());

// ---------- hooks ----------
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    fn()
      .then((d) => { if (live) { setData(d); setError(null); } })
      .catch((e) => { if (live) setError(e as Error); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try { return await fn(); } catch (e) { setError(e as Error); return undefined; } finally { setBusy(false); }
  }
  return { run, busy, error, setError };
}

export function useForm<T extends Record<string, string | boolean>>(initial: T) {
  const [v, setV] = useState<T>(initial);
  const on = (k: keyof T) => ({
    value: v[k] as string,
    onChange: (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setV((p) => ({ ...p, [k]: e.target.value }) as T),
  });
  return { v, set: setV, on, reset: () => setV(initial) };
}

// ---------- components ----------
const TONES: Record<Tone, string> = {
  green: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  amber: "bg-amber-100 text-amber-900 ring-amber-300",
  red: "bg-red-100 text-red-800 ring-red-300",
  slate: "bg-slate-100 text-slate-700 ring-slate-300",
  teal: "bg-brand-50 text-brand-700 ring-brand-100",
  blue: "bg-sky-100 text-sky-800 ring-sky-300",
};
export function Badge({ tone = "slate", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${TONES[tone]}`}>{children}</span>;
}
export const NeedBadge = ({ status }: { status: string }) => (
  <Badge tone={NEED_TONE[status] ?? "slate"}>{NEED_LABEL[status] ?? label(status)}</Badge>
);
export const Verification = ({ verified }: { verified: boolean }) =>
  verified ? <Badge tone="green">Confirmed by the provider</Badge> : <Badge tone="teal">Reported by the family, not verified</Badge>;

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 ${className}`}>
      {title && <h2 className="mb-3 text-lg font-semibold text-slate-900">{title}</h2>}
      {children}
    </section>
  );
}

export function Btn({ variant = "primary", className = "", ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "link" }) {
  const base = "inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";
  const v = {
    primary: "bg-brand-600 text-white hover:bg-brand-700",
    secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
    danger: "border border-red-300 bg-white text-red-700 hover:bg-red-50",
    link: "px-0 text-brand-700 underline",
  }[variant];
  return <button type="button" className={`${base} ${v} ${className}`} {...p} />;
}

const inputCls = "mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500";
export function Field({ label: l, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      <span>{l}</span>{children}
      {hint && <span className="mt-1 block text-xs font-normal text-slate-500">{hint}</span>}
    </label>
  );
}
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input className={inputCls} {...p} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select className={inputCls} {...p} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea rows={3} className={inputCls} {...p} />;

export function ErrorBox({ error, onPick }: { error: Error | null; onPick?: (s: string) => void }) {
  if (!error) return null;
  const sug = error instanceof ApiError ? error.suggestions : [];
  return (
    <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200">
      {error.message}
      {sug.length > 0 && (
        <div className="mt-1">Did you mean:{" "}
          {sug.map((s) => (
            <button key={s} type="button" onClick={() => onPick?.(s)} className="mr-2 font-medium underline">{s}</button>
          ))}
        </div>
      )}
    </div>
  );
}
export const Notice = ({ children, tone = "teal" }: { children: ReactNode; tone?: "teal" | "amber" }) => (
  <div role="status" className={`rounded-lg p-3 text-sm ring-1 ${tone === "amber" ? "bg-amber-50 text-amber-900 ring-amber-200" : "bg-brand-50 text-brand-700 ring-brand-100"}`}>{children}</div>
);
export const Loading = () => <p className="p-6 text-sm text-slate-500" role="status">Loading...</p>;
export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => (
  <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center">
    <p className="font-medium text-slate-700">{title}</p>
    {children && <div className="mt-1 text-sm text-slate-500">{children}</div>}
  </div>
);
export const PrivateNoteWarning = () => (
  <p className="text-xs text-slate-500">Please do not write medical, safety or other private details here. The people you share this with can read it.</p>
);