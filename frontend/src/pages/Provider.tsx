import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { ProviderReferral } from "../types";
import { Badge, Btn, CATEGORY_LABEL, Card, EDU_LABEL, Empty, ErrorBox, Field, Input, Loading, Notice, Select, Textarea, fmtDate, label, opt, useAction, useForm, useLoad } from "../ui";

interface Dash { by_status: Record<string, number>; awaiting_response: number; info_requested: number; accepted_awaiting_outcome: number; confirmed_outcomes: number }

export function ProviderList() {
  const [status, setStatus] = useState("");
  const dash = useLoad(() => api<Dash>("/provider/dashboard"), []);
  const list = useLoad(() => api<ProviderReferral[]>("/provider/referrals", { query: { status } }), [status]);
  if (dash.error) return <ErrorBox error={dash.error} />;
  const d = dash.data;
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Referrals to your organisation</h1>
      {d && <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[["Waiting for your response", d.awaiting_response], ["Information requested", d.info_requested], ["Accepted, outcome not yet confirmed", d.accepted_awaiting_outcome], ["Outcomes confirmed", d.confirmed_outcomes]].map(([t, n]) => (
          <div key={t as string} className="rounded-xl bg-white p-4 ring-1 ring-slate-200"><p className="text-3xl font-bold text-slate-800">{n}</p><p className="text-sm text-slate-600">{t}</p></div>))}
      </div>}
      <div className="max-w-xs"><Field label="Show"><Select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All referrals</option>{["RECORDED", "ACCEPTED", "INFO_REQUESTED", "DECLINED", "NO_RESPONSE", "WITHDRAWN"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select></Field></div>
      {list.loading ? <Loading /> : list.error ? <ErrorBox error={list.error} /> : (list.data ?? []).length === 0
        ? <Empty title="No referrals">Families will appear here when they refer a child to a service listed for your organisation.</Empty>
        : <div className="grid gap-4 md:grid-cols-2">{(list.data ?? []).map((r) => (
          <Link key={r.id} to={`/provider/referrals/${r.id}`} className="block rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 hover:ring-brand-500">
            <p className="font-semibold">{r.child_name}{r.child_age_years !== null ? `, ${r.child_age_years}` : ""}</p>
            <p className="text-sm text-slate-600">{CATEGORY_LABEL[r.category]} - {r.service_name}</p>
            <div className="mt-2"><Badge tone={r.status === "RECORDED" ? "amber" : "slate"}>{label(r.status)}</Badge></div>
          </Link>))}</div>}
    </div>
  );
}

export function ProviderDetail() {
  const { id = "" } = useParams();
  const q = useLoad(() => api<ProviderReferral>(`/provider/referrals/${id}`), [id]);
  const rf = useForm({ response_type: "RECEIVED", message: "", barrier: "" });
  const cf = useForm({ outcome: "", reference_note: "" });
  const a = useAction();
  if (q.loading && !q.data) return <Loading />;
  if (q.error || !q.data) return <ErrorBox error={q.error} />;
  const r = q.data;
  async function respond(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api(`/provider/referrals/${id}/respond`, { body: { response_type: rf.v.response_type, message: opt(rf.v.message), barrier: opt(rf.v.barrier) } }))) { rf.reset(); q.reload(); }
  }
  async function confirm(e: FormEvent) {
    e.preventDefault();
    if (!window.confirm("Confirm that this child has actually received this support? This is recorded as confirmed by your organisation.")) return;
    if (await a.run(() => api(`/provider/referrals/${id}/confirm-outcome`, { body: { outcome: cf.v.outcome, reference_note: opt(cf.v.reference_note) } }))) { cf.reset(); q.reload(); }
  }
  const closed = ["DECLINED", "NO_RESPONSE", "WITHDRAWN"].includes(r.status) || !r.need_is_open && r.status !== "ACCEPTED";
  return (
    <div className="space-y-5">
      <Link to="/provider" className="text-sm text-brand-700 underline">All referrals</Link>
      <Card title={`${r.child_name}${r.child_age_years !== null ? `, ${r.child_age_years}` : ""}`}>
        <div className="mb-2 flex gap-2"><Badge>{CATEGORY_LABEL[r.category]}</Badge><Badge tone="amber">{label(r.status)}</Badge></div>
        <p className="text-sm">{r.need_description}</p>
        <dl className="mt-3 space-y-1 text-sm text-slate-600">
          <div>Referred to: {r.service_name} on {fmtDate(r.referred_at)}</div>
          {r.destination_district && <div>Family is moving to {r.destination_district}{r.planned_date ? ` around ${fmtDate(r.planned_date)}` : ""}</div>}
          {r.education_status && <div>School status: {EDU_LABEL[r.education_status]}{r.current_school_name ? ` (${r.current_school_name})` : ""}</div>}
          {r.accommodations_note && <div>Support needed: {r.accommodations_note}</div>}
          <div>Preferred language: {r.preferred_language}</div>
          <div>Family phone: {r.family_contact_phone ?? "shared after you accept the referral"}</div>
          {r.referral_note && <div>Family's note: {r.referral_note}</div>}
        </dl>
        <p className="mt-3 text-xs text-slate-500">You see only what is needed to respond. Other family details are not shared.</p>
      </Card>
      <Card title="What has happened so far">
        {r.responses.length === 0 && r.family_messages.length === 0 ? <p className="text-sm text-slate-500">No responses yet.</p> : (
          <ul className="space-y-1 text-sm">
            {r.responses.map((p) => <li key={p.id}><b>You - {label(p.response_type)}:</b> {p.message ?? p.barrier} <span className="text-slate-400">{fmtDate(p.responded_at)}</span></li>)}
            {r.family_messages.map((m, i) => <li key={i}><b>Family - {label(m.method)}:</b> {m.note ?? label(m.result)} <span className="text-slate-400">{fmtDate(m.attempted_at)}</span></li>)}
          </ul>)}
      </Card>
      <ErrorBox error={a.error} />
      {closed ? <Notice>This referral is {label(r.status).toLowerCase()} or its need is resolved, so it can no longer be answered.</Notice> : (
        <>
          {r.status !== "ACCEPTED" && (
            <Card title="Respond">
              <form onSubmit={respond} className="grid gap-3 md:grid-cols-2">
                <Field label="Your response"><Select {...rf.on("response_type")}><option value="RECEIVED">We have received this</option><option value="ACCEPTED">We accept this referral</option><option value="INFO_REQUESTED">We need more information</option><option value="DECLINED">We cannot help</option></Select></Field>
                {rf.v.response_type === "DECLINED" && <Field label="Reason (required)"><Input required maxLength={300} {...rf.on("barrier")} /></Field>}
                <div className="md:col-span-2"><Field label={rf.v.response_type === "INFO_REQUESTED" ? "What information is needed (required)" : "Message to the family (optional)"}><Textarea required={rf.v.response_type === "INFO_REQUESTED"} maxLength={500} {...rf.on("message")} /></Field></div>
                <div className="md:col-span-2"><Btn type="submit" disabled={a.busy}>Send response</Btn></div>
              </form>
            </Card>)}
          {r.status === "ACCEPTED" && r.need_is_open && (
            <Card title="Confirm the outcome">
              <p className="mb-3 text-sm text-slate-600">Accepting a referral is not the same as providing support. Confirm only once the child has actually received it.</p>
              <form onSubmit={confirm} className="grid gap-3 md:grid-cols-2">
                <div className="md:col-span-2"><Field label="What was provided?"><Input required maxLength={300} {...cf.on("outcome")} /></Field></div>
                <div className="md:col-span-2"><Field label="Reference, for example admission number (optional)"><Input maxLength={500} {...cf.on("reference_note")} /></Field></div>
                <div className="md:col-span-2"><Btn type="submit" disabled={a.busy}>Confirm outcome</Btn></div>
              </form>
            </Card>)}
        </>
      )}
    </div>
  );
}