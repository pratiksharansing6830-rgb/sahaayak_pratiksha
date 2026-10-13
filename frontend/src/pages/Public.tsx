import type { FormEvent } from "react";
import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, HeartHandshake, MapPin, ShieldCheck, UsersRound } from "lucide-react";
import { HOME } from "../App";
import { useAuth } from "../auth";
import { Btn, Card, ErrorBox, Field, Input, useAction, useForm } from "../ui";

export function Landing() {
  const { user } = useAuth();
  const [step, setStep] = useState(0);
  const journey = [
    {
      title: "Tell us about your family",
      detail: "Create a family profile and add the children you want to plan for. You choose what information to share.",
      icon: UsersRound,
    },
    {
      title: "Plan for the move",
      detail: "Add your destination district. Sahaayak helps you review possible support needs for each child.",
      icon: MapPin,
    },
    {
      title: "Keep support moving",
      detail: "Track follow-ups, look for listed services and record what happens next, all in one place.",
      icon: HeartHandshake,
    },
  ];
  const activeStep = journey[step];
  const StepIcon = activeStep.icon;
  return (
    <div className="space-y-12 pb-6">
      <section className="relative isolate overflow-hidden rounded-[2rem] bg-gradient-to-br from-brand-50 via-white to-warm-100 px-6 py-10 ring-1 ring-brand-100 sm:px-10 sm:py-14 lg:px-14">
        <div className="pointer-events-none absolute -right-20 -top-24 -z-10 h-80 w-80 rounded-full bg-brand-100/70 blur-3xl" />
        <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1.5 text-sm font-medium text-brand-700 ring-1 ring-brand-100">
              <HeartHandshake size={16} aria-hidden="true" /> Support that moves with your family
            </div>
            <h1 className="max-w-2xl text-4xl font-bold leading-tight tracking-tight text-brand-700 sm:text-5xl">
              A new place shouldn't mean starting support from scratch.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-700 sm:text-lg">
              Sahaayak helps families plan for a move, keep track of children's needs, and follow up with services — step by step.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              {user ? (
                <Link to={HOME[user.role]} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 py-3 font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2">
                  Go to your dashboard <ArrowRight size={18} aria-hidden="true" />
                </Link>
              ) : (
                <>
                  <Link to="/register" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 py-3 font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2">
                    Get started <ArrowRight size={18} aria-hidden="true" />
                  </Link>
                  <Link to="/login" className="inline-flex min-h-12 items-center justify-center rounded-xl border border-slate-300 bg-white/80 px-5 py-3 font-semibold text-slate-700 transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2">
                    I already have an account
                  </Link>
                </>
              )}
            </div>
            <p className="mt-4 text-sm text-slate-500">Simple to use. You stay in control of what you share.</p>
          </div>

          <div id="journey-guide" className="rounded-3xl border border-white bg-white/90 p-5 shadow-xl shadow-brand-900/5 sm:p-7">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-700">Your support journey</p>
            <h2 className="mt-2 text-xl font-bold text-slate-900">A few clear steps. One place to keep track.</h2>
            <div className="mt-5 grid grid-cols-3 gap-2" role="group" aria-label="Choose a step">
              {journey.map((item, index) => (
                <button key={item.title} type="button"
                  aria-pressed={step === index} onClick={() => setStep(index)}
                  className={`min-h-11 rounded-lg px-2 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${step === index ? "bg-brand-600 text-white shadow-sm" : "bg-slate-50 text-slate-600 hover:bg-brand-50 hover:text-brand-700"}`}>
                  Step {index + 1}
                </button>
              ))}
            </div>
            <div aria-live="polite" className="mt-5 min-h-36 rounded-2xl bg-warm-50 p-5">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-700">
                <StepIcon size={21} aria-hidden="true" />
              </div>
              <h3 className="mt-3 font-semibold text-slate-900">{activeStep.title}</h3>
              <p className="mt-1 text-sm leading-6 text-slate-600">{activeStep.detail}</p>
            </div>
            <div className="mt-4 flex items-center gap-2 text-sm text-slate-600">
              <ShieldCheck size={18} className="shrink-0 text-brand-600" aria-hidden="true" />
              Your information is shared only with people you choose and providers you refer to.
            </div>
          </div>
        </div>
      </section>

      <section aria-labelledby="benefits-title">
        <div className="mb-5 max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-wider text-brand-700">Made for families on the move</p>
          <h2 id="benefits-title" className="mt-2 text-2xl font-bold text-slate-900 sm:text-3xl">Know what to do next — and what has happened so far.</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {journey.map((item, index) => {
            const Icon = item.icon;
            return (
              <button key={item.title} type="button" onClick={() => { setStep(index); document.getElementById("journey-guide")?.scrollIntoView({ behavior: "smooth", block: "center" }); }}
                className="group rounded-2xl bg-white p-5 text-left shadow-sm ring-1 ring-slate-200 transition hover:-translate-y-1 hover:shadow-md hover:ring-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 sm:p-6">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-700 transition group-hover:bg-brand-100"><Icon size={22} aria-hidden="true" /></span>
                <span className="mt-4 block text-lg font-semibold text-slate-900">{item.title}</span>
                <span className="mt-2 block text-sm leading-6 text-slate-600">{item.detail}</span>
                <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand-700">See step {index + 1} <ArrowRight size={16} aria-hidden="true" /></span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="grid gap-5 rounded-3xl bg-white p-6 ring-1 ring-slate-200 sm:grid-cols-[1fr_auto] sm:items-center sm:p-8">
        <div>
          <h2 className="text-xl font-bold text-slate-900">A service listing is a starting point, not a promise.</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Sahaayak helps you keep information together. It does not decide eligibility or confirm that a service is available. A referral, provider response and confirmed support are recorded as different steps.
          </p>
        </div>
        {!user && <Link to="/register" className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-brand-200 px-4 py-2.5 text-sm font-semibold text-brand-700 transition hover:bg-brand-50">
          Start with your family <ArrowRight size={17} aria-hidden="true" />
        </Link>}
      </section>
    </div>
  );
}

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const f = useForm({ email: "", password: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const u = await a.run(() => login(f.v.email, f.v.password));
    if (u) nav((loc.state as { from?: string } | null)?.from ?? HOME[u.role], { replace: true });
  }
  return (
    <Card title="Log in" className="mx-auto max-w-md">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email"><Input type="email" required autoComplete="username" {...f.on("email")} /></Field>
        <Field label="Password"><Input type="password" required autoComplete="current-password" {...f.on("password")} /></Field>
        <ErrorBox error={a.error} />
        <Btn type="submit" disabled={a.busy} className="w-full">{a.busy ? "Logging in..." : "Log in"}</Btn>
        <p className="text-sm text-slate-600">New here? <Link className="text-brand-700 underline" to="/register">Create a family account</Link></p>
      </form>
    </Card>
  );
}

export function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const f = useForm({ full_name: "", email: "", phone: "", password: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const u = await a.run(() => register({
      full_name: f.v.full_name, email: f.v.email, password: f.v.password, phone: f.v.phone.trim() || undefined,
    }));
    if (u) nav("/family/new", { replace: true });
  }
  return (
    <Card title="Create a family account" className="mx-auto max-w-md">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Your name"><Input required maxLength={200} {...f.on("full_name")} /></Field>
        <Field label="Email"><Input type="email" required autoComplete="username" {...f.on("email")} /></Field>
        <Field label="Phone (optional)"><Input type="tel" maxLength={20} {...f.on("phone")} /></Field>
        <Field label="Password" hint="At least 8 characters."><Input type="password" required minLength={8} maxLength={72} autoComplete="new-password" {...f.on("password")} /></Field>
        <ErrorBox error={a.error} />
        <Btn type="submit" disabled={a.busy} className="w-full">{a.busy ? "Creating..." : "Create account"}</Btn>
        <p className="text-xs text-slate-500">Accounts for schools, health providers, support workers and officials are created by an administrator.</p>
      </form>
    </Card>
  );
}

export const Forbidden = () => <Card title="No access"><p>Your account does not have access to this page.</p></Card>;
export function NotFound() {
  const { user } = useAuth();
  if (user === undefined) return <Navigate to="/" />;
  return <Card title="Page not found"><p className="text-sm">We could not find that page. <Link className="text-brand-700 underline" to="/app">Go back</Link></p></Card>;
}