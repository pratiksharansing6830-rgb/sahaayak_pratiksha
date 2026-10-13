import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Family } from "../types";
import { Btn, Card, Empty, ErrorBox, Field, Input, Loading, Select, opt, useAction, useForm, useLoad } from "../ui";

export function FamilyList() {
  const { user } = useAuth();
  const q = useLoad(() => api<Family[]>("/families"), []);
  if (q.loading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const list = q.data ?? [];
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{user?.role === "NGO" ? "Families shared with you" : "Your family"}</h1>
        {user?.role === "CITIZEN" && <Link to="/family/new" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white">Add a family</Link>}
      </div>
      {list.length === 0 ? (
        user?.role === "CITIZEN"
          ? <Empty title="You have not set up a family profile yet"><Link className="text-brand-700 underline" to="/family/new">Start here</Link>. It takes about two minutes.</Empty>
          : <Empty title="No families have been shared with you yet">A family can share their case with you from their Sharing tab.</Empty>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {list.map((f) => (
            <Link key={f.id} to={`/family/${f.id}`} className="block rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 hover:ring-brand-500">
              <p className="text-lg font-semibold">{f.household_name}</p>
              <p className="text-sm text-slate-600">{f.primary_caregiver_name}{f.origin_district ? ` - from ${f.origin_district}` : ""}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function FamilyNew() {
  const nav = useNavigate();
  const f = useForm({
    household_name: "",
    primary_caregiver_name: "",
    contact_phone: "",
    origin_district: "",
    origin_state: "Maharashtra",
    preferred_language: "en",
    consent: false as boolean,
  });
  const a = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const fam = await a.run(() => api<Family>("/families", { body: {
      household_name: f.v.household_name,
      primary_caregiver_name: f.v.primary_caregiver_name,
      contact_phone: opt(f.v.contact_phone),
      origin_district: opt(f.v.origin_district),
      origin_state: opt(f.v.origin_state),
      preferred_language: f.v.preferred_language,
      consent_given: f.v.consent,
    } }));
    if (fam) nav(`/family/${fam.id}`, { replace: true });
  }

  return (
    <Card title="Set up your family" className="mx-auto max-w-xl">
      <p className="mb-4 text-sm text-slate-600">We only ask for what is needed. You can add your children next.</p>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Family or household name"><Input required maxLength={200} {...f.on("household_name")} /></Field>
        <Field label="Main caregiver's name"><Input required maxLength={200} {...f.on("primary_caregiver_name")} /></Field>
        <Field label="Contact phone (optional)" hint="Providers see it only after they accept a referral."><Input type="tel" pattern="[+0-9][0-9 \-]{6,19}" title="Digits, spaces or dashes, 7 to 20 characters" {...f.on("contact_phone")} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Where you live now (district)"><Input list="districts" maxLength={100} {...f.on("origin_district")} /></Field>
          <Field label="State"><Input maxLength={100} {...f.on("origin_state")} /></Field>
        </div>
        <Field label="Preferred language">
          <Select {...f.on("preferred_language")}><option value="en">English</option><option value="mr">Marathi</option><option value="hi">Hindi</option></Select>
        </Field>
        <label className="flex items-start gap-3 rounded-lg bg-slate-50 p-3 text-sm">
          <input type="checkbox" required className="mt-1 h-4 w-4" checked={f.v.consent} onChange={(e) => f.set({ ...f.v, consent: e.target.checked })} />
          <span>I agree that Sahaayak may store my family's and children's details to help keep their services going after a move. Only people I choose to share with, and providers I refer to, can see the parts they need. (Privacy notice 1.0)</span>
        </label>
        <ErrorBox error={a.error} />
        <Btn type="submit" disabled={a.busy}>{a.busy ? "Saving..." : "Create family profile"}</Btn>
      </form>
    </Card>
  );
}