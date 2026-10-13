import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Contact, Migration, NeedDetail, Referral } from "../types";
import {
  Badge, Btn, CATEGORY_LABEL, CITIZEN_MOVES, Card, Empty, ErrorBox, Field, Input, Loading, NEED_LABEL, NeedBadge,
  Notice, PrivateNoteWarning, Select, Textarea, Verification, fmtDate, label, opt, useAction, useForm, useLoad,
} from "../ui";

const ACTIVE_REF = ["RECORDED", "ACCEPTED", "INFO_REQUESTED"];

export default function NeedPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const canEdit = user?.role === "CITIZEN";
  const q = useLoad(() => api<NeedDetail>(`/needs/${id}`), [id]);
  const refs = useLoad(() => api<Referral[]>(`/needs/${id}/referrals`), [id]);
  const cons = useLoad(() => api<Contact[]>(`/needs/${id}/contact-attempts`), [id]);
  const mig = useLoad(() => (q.data?.migration_id ? api<Migration>(`/migrations/${q.data.migration_id}`) : Promise.resolve(null)), [q.data?.migration_id]);
  const a = useAction();
  const reloadAll = () => { q.reload(); refs.reload(); cons.reload(); };

  if (q.loading && !q.data) return <Loading />;
  if (q.error || !q.data) return <ErrorBox error={q.error} />;
  const n = q.data;
  const activeFu = n.follow_ups.filter((f) => f.status === "OPEN" || f.status === "IN_PROGRESS");
  const dest = mig.data?.destination_district;

  async function fu(fuId: string, what: "complete" | "cancel") {
    if (await a.run(() => api(`/follow-ups/${fuId}/${what}`, { method: "POST", body: what === "complete" ? {} : undefined }))) reloadAll();
  }
  async function refAct(refId: string, what: "withdraw" | "no-response") {
    if (await a.run(() => api(`/referrals/${refId}/${what}`, { method: "POST" }))) reloadAll();
  }

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm text-slate-500">{CATEGORY_LABEL[n.category]}{dest ? ` - move to ${dest}` : ""}</p>
        <h1 className="text-2xl font-bold">{n.need_description}</h1>
        <div className="mt-2 flex flex-wrap gap-2"><NeedBadge status={n.status} />{n.due_date && n.is_open && <Badge>Due {fmtDate(n.due_date)}</Badge>}</div>
      </div>
      <Card title="Where this stands">
        <p className="text-sm">{n.status_explanation}</p>
        {n.next_action && <p className="mt-2 text-sm"><b>What to do next:</b> {n.next_action}</p>}
        {n.closure_reason && <p className="mt-2 text-sm"><b>Reason recorded:</b> {n.closure_reason}</p>}
        {n.confirmations.map((c, i) => (
          <div key={i} className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
            <Verification verified={c.provider_verified} />
            <p className="mt-1">{c.outcome}</p>
            <p className="text-xs text-slate-500">{label(c.method)} by {label(c.confirmed_by_role)} on {fmtDate(c.confirmed_at)}{c.reference_note ? ` - ${c.reference_note}` : ""}</p>
          </div>
        ))}
      </Card>
      <ErrorBox error={a.error} />

      <Card title="Follow-up tasks">
        {activeFu.length === 0 ? <p className="text-sm text-slate-500">No open tasks.</p> : (
          <ul className="divide-y divide-slate-100">{activeFu.map((f) => (
            <li key={f.id} className="py-2">
              <p className="text-sm font-medium">{f.description} {f.is_overdue && <Badge tone="red">Overdue</Badge>}</p>
              <p className="text-xs text-slate-500">Due {fmtDate(f.due_date)}</p>
              {canEdit && <div className="mt-1 flex gap-3"><Btn variant="secondary" onClick={() => void fu(f.id, "complete")}>Mark task done</Btn><Btn variant="link" onClick={() => void fu(f.id, "cancel")}>Cancel</Btn></div>}
            </li>))}</ul>
        )}
        <p className="mt-2 text-xs text-slate-500">Finishing a task does not solve the need.</p>
        {canEdit && n.is_open && <AddFollowUp needId={n.id} protection={n.category === "PROTECTION"} onDone={reloadAll} />}
      </Card>

      <Card title="Referrals">
        {(refs.data ?? []).length === 0 ? <Empty title="No referral recorded">{canEdit && n.is_open ? "Find a service at the destination and record a referral." : ""}</Empty> : (
          <ul className="divide-y divide-slate-100">{(refs.data ?? []).map((r) => (
            <li key={r.id} className="py-3 text-sm">
              <p className="font-medium">{r.service_name} <Badge>{label(r.status)}</Badge> {r.service_verification_status === "SAMPLE" && <Badge tone="amber">Sample listing</Badge>}</p>
              <p className="text-slate-600">{r.plain_status}</p>
              {r.provider_responses.map((p) => <p key={p.id}><b>{label(p.response_type)}:</b> {p.message ?? p.barrier}</p>)}
              {canEdit && <div className="mt-1 flex gap-3">
                {ACTIVE_REF.includes(r.status) && <Btn variant="link" onClick={() => void refAct(r.id, "withdraw")}>Withdraw</Btn>}
                {r.status === "RECORDED" && <Btn variant="link" onClick={() => void refAct(r.id, "no-response")}>No reply after a week</Btn>}</div>}
            </li>))}</ul>
        )}
        {canEdit && n.is_open && n.status !== "NEEDS_ASSESSMENT" && (
          <div className="mt-3"><Link className="inline-flex rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white" to={`/services?need=${n.id}${dest ? `&district=${encodeURIComponent(dest)}` : ""}`}>Find a service</Link></div>
        )}
        {n.status === "NEEDS_ASSESSMENT" && <p className="mt-3 text-sm text-slate-500">Confirm that the child needs this support (change status below) before recording a referral.</p>}
      </Card>

      <Card title="Contact attempts and messages">
        {(cons.data ?? []).length === 0 ? <p className="text-sm text-slate-500">None recorded.</p> :
          <ul className="space-y-1 text-sm">{(cons.data ?? []).map((c) => <li key={c.id}>{fmtDate(c.attempted_at)} - {label(c.method)} - {c.service_name}: {label(c.result)}{c.note ? ` (${c.note})` : ""}</li>)}</ul>}
        {canEdit && n.is_open && (refs.data ?? []).some((r) => ACTIVE_REF.includes(r.status)) &&
          <ContactForm needId={n.id} refs={(refs.data ?? []).filter((r) => ACTIVE_REF.includes(r.status))} onDone={reloadAll} />}
      </Card>

      {canEdit && n.is_open && <StatusForm need={n} onDone={reloadAll} />}
      {canEdit && n.is_open && n.status !== "NEEDS_ASSESSMENT" && (n.category === "PROTECTION"
        ? <Notice>Outcomes for child protection can only be confirmed by an authorised provider or support worker.</Notice>
        : <ConfirmForm needId={n.id} onDone={reloadAll} />)}

      <Card title="History">
        <ol className="space-y-2 text-sm">{n.history.map((h, i) => (
          <li key={i}><span className="text-slate-400">{fmtDate(h.created_at)}</span> - {h.from_status ? `${NEED_LABEL[h.from_status]} to ` : "Started as "}<b>{NEED_LABEL[h.to_status]}</b>{h.changed_by_role ? ` (${label(h.changed_by_role)})` : ""}{h.reason ? ` - ${h.reason}` : ""}</li>))}</ol>
      </Card>
    </div>
  );
}

function AddFollowUp({ needId, protection, onDone }: { needId: string; protection: boolean; onDone: () => void }) {
  const f = useForm({ action_type: "REQUEST_MISSING_INFO", description: "", priority: "MEDIUM", due_date: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api(`/needs/${needId}/follow-ups`, { body: { ...f.v, due_date: opt(f.v.due_date) } }))) { f.reset(); onDone(); }
  }
  return (
    <form onSubmit={submit} className="mt-4 grid gap-3 border-t border-slate-100 pt-4 md:grid-cols-2">
      <Field label="Type of task"><Select {...f.on("action_type")}>
        {["CONTACT_SCHOOL", "REQUEST_TRANSFER_UPDATE", "CONTACT_HEALTHCARE", "EXPLORE_ALTERNATIVE", "REQUEST_MISSING_INFO", "SCHEDULE_FOLLOW_UP", ...(protection ? ["ESCALATE_SAFEGUARDING"] : [])].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select></Field>
      <Field label="Due date (optional)"><Input type="date" min={new Date().toISOString().slice(0, 10)} {...f.on("due_date")} /></Field>
      <div className="md:col-span-2"><Field label="What needs to happen"><Input required maxLength={500} {...f.on("description")} /></Field></div>
      <div className="space-y-2 md:col-span-2"><ErrorBox error={a.error} /><Btn type="submit" variant="secondary" disabled={a.busy}>Add task</Btn></div>
    </form>
  );
}

function ContactForm({ needId, refs, onDone }: { needId: string; refs: Referral[]; onDone: () => void }) {
  const f = useForm({ referral_id: refs[0]?.id ?? "", method: "MESSAGE", result: "OTHER", note: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api(`/needs/${needId}/contact-attempts`, { body: { referral_id: f.v.referral_id, method: f.v.method, result: f.v.result, note: opt(f.v.note) } }))) { f.set({ ...f.v, note: "" }); onDone(); }
  }
  return (
    <form onSubmit={submit} className="mt-4 grid gap-3 border-t border-slate-100 pt-4 md:grid-cols-3">
      <Field label="Service"><Select {...f.on("referral_id")}>{refs.map((r) => <option key={r.id} value={r.id}>{r.service_name}</option>)}</Select></Field>
      <Field label="How"><Select {...f.on("method")}>{["PHONE", "VISIT", "MESSAGE", "OTHER"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select></Field>
      <Field label="What happened"><Select {...f.on("result")}>{["REACHED", "NO_ANSWER", "INFO_REQUESTED", "OTHER"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select></Field>
      <div className="md:col-span-3"><Field label="Note or reply to the provider (optional)"><Textarea maxLength={500} {...f.on("note")} /></Field><PrivateNoteWarning /></div>
      <div className="space-y-2 md:col-span-3"><ErrorBox error={a.error} /><Btn type="submit" variant="secondary" disabled={a.busy}>Record contact</Btn></div>
    </form>
  );
}

function StatusForm({ need, onDone }: { need: NeedDetail; onDone: () => void }) {
  const options = CITIZEN_MOVES[need.status] ?? [];
  const f = useForm({ status: options[0] ?? "", reason: "" });
  const a = useAction();
  if (options.length === 0) return null;
  const needsReason = f.v.status === "NOT_REQUIRED" || f.v.status === "CLOSED";
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api(`/needs/${need.id}/status`, { body: { status: f.v.status, reason: opt(f.v.reason) } }))) { f.reset(); onDone(); }
  }
  return (
    <Card title="Update this need">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
        <Field label="Change status to"><Select {...f.on("status")}>{options.map((k) => <option key={k} value={k}>{NEED_LABEL[k]}</option>)}</Select></Field>
        <Field label={needsReason ? "Reason (required)" : "Reason (optional)"}><Input minLength={needsReason ? 5 : undefined} required={needsReason} maxLength={500} {...f.on("reason")} /></Field>
        <div className="space-y-2 md:col-span-2">
          {needsReason && <p className="text-xs text-amber-800">"Not needed" and "Closed" are not the same as support received.</p>}
          <ErrorBox error={a.error} /><Btn type="submit" variant="secondary" disabled={a.busy}>Update</Btn></div>
      </form>
    </Card>
  );
}

function ConfirmForm({ needId, onDone }: { needId: string; onDone: () => void }) {
  const f = useForm({ outcome: "", method: "FAMILY_REPORTED", reference_note: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!window.confirm("Record that this support was received? It will be shown as reported by the family, not verified by a provider.")) return;
    if (await a.run(() => api(`/needs/${needId}/confirm`, { body: { outcome: f.v.outcome, method: f.v.method, reference_note: opt(f.v.reference_note) } }))) onDone();
  }
  return (
    <Card title="Support received?">
      <p className="mb-3 text-sm text-slate-600">Only record this once the child has actually received the support. It will be labelled as reported by your family until a provider confirms it.</p>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-2">
        <div className="md:col-span-2"><Field label="What did the child receive?"><Input required maxLength={300} {...f.on("outcome")} /></Field></div>
        <Field label="How do you know?"><Select {...f.on("method")}><option value="FAMILY_REPORTED">I am telling you</option><option value="DOCUMENT_SEEN">I have seen a document</option></Select></Field>
        <Field label={f.v.method === "DOCUMENT_SEEN" ? "Which document (required)" : "Reference (optional)"}><Input required={f.v.method === "DOCUMENT_SEEN"} maxLength={500} {...f.on("reference_note")} /></Field>
        <div className="space-y-2 md:col-span-2"><ErrorBox error={a.error} /><Btn type="submit" disabled={a.busy}>Record outcome</Btn></div>
      </form>
    </Card>
  );
}