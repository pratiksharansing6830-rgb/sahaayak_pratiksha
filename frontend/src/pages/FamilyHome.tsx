import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { AccessRow, Child, Contact, Family, FollowUp, Migration, Referral, Summary } from "../types";
import {
  Badge, Btn, CATEGORY_LABEL, Card, EDU_LABEL, Empty, ErrorBox, Field, Input, Loading, NeedBadge, Notice,
  PrivateNoteWarning, Select, Textarea, Verification, fmtDate, label, opt, useAction, useForm, useLoad,
} from "../ui";

type Tab = "overview" | "children" | "moves" | "followups" | "history" | "sharing";

export default function FamilyHome() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const fam = useLoad(() => api<Family>(`/families/${id}`), [id]);
  const [tab, setTab] = useState<Tab>("overview");
  const canEdit = user?.role === "CITIZEN";
  if (fam.loading) return <Loading />;
  if (fam.error || !fam.data) return <ErrorBox error={fam.error} />;
  const tabs: [Tab, string][] = [["overview", "Summary"], ["children", "Children"], ["moves", "Move plan"], ["followups", "Follow-up tasks"], ["history", "Referrals and contact"]];
  if (canEdit) tabs.push(["sharing", "Sharing"]);
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">{fam.data.household_name}</h1>
        <p className="text-sm text-slate-600">{fam.data.primary_caregiver_name}{fam.data.origin_district ? ` - ${fam.data.origin_district}` : ""}</p>
        {!canEdit && <div className="mt-2"><Notice>You can view this family because they shared it with you. You cannot change it.</Notice></div>}
      </div>
      <div role="tablist" className="flex flex-wrap gap-1 border-b border-slate-200">
        {tabs.map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${tab === k ? "bg-white text-brand-700 ring-1 ring-slate-200" : "text-slate-600 hover:text-slate-900"}`}>{l}</button>
        ))}
      </div>
      {tab === "overview" && <Overview id={id} canEdit={canEdit} go={setTab} />}
      {tab === "children" && <Children id={id} canEdit={canEdit} />}
      {tab === "moves" && <Moves id={id} canEdit={canEdit} defaults={fam.data} />}
      {tab === "followups" && <FollowUps id={id} canEdit={canEdit} />}
      {tab === "history" && <History id={id} canEdit={canEdit} />}
      {tab === "sharing" && canEdit && <Sharing id={id} />}
    </div>
  );
}

// ---------------- Overview ----------------
function Tile({ n, text, tone }: { n: number; text: string; tone: "amber" | "red" | "green" | "slate" }) {
  const c = { amber: "text-amber-700", red: "text-red-700", green: "text-emerald-700", slate: "text-slate-700" }[tone];
  return <div className="rounded-xl bg-white p-4 ring-1 ring-slate-200"><p className={`text-3xl font-bold ${n === 0 && tone !== "slate" ? "text-slate-400" : c}`}>{n}</p><p className="text-sm text-slate-600">{text}</p></div>;
}

function Overview({ id, canEdit, go }: { id: string; canEdit: boolean; go: (t: Tab) => void }) {
  const sum = useLoad(() => api<Summary>(`/families/${id}/continuity-summary`), [id]);
  const migs = useLoad(() => api<Migration[]>(`/families/${id}/migrations`), [id]);
  if (sum.loading || migs.loading) return <Loading />;
  if (sum.error || !sum.data) return <ErrorBox error={sum.error} />;
  const s = sum.data;
  const live = (migs.data ?? []).filter((m) => m.status !== "CANCELLED");
  const dest = live[0]?.destination_district;
  const currentStep = s.children.length === 0 ? 0 : live.length === 0 ? 1 : s.totals.not_assessed > 0 ? 2 : 3;
  const steps = [
    { title: "Add children", detail: "Add each child you want to include.", complete: s.children.length > 0 },
    { title: "Plan your move", detail: "Choose the district you are moving to.", complete: live.length > 0 },
    { title: "Check support needs", detail: "Review what support each child may need.", complete: currentStep > 2 },
    { title: "Follow up on support", detail: "Keep track until each need has an outcome.", complete: false },
  ];
  return (
    <div className="space-y-5">
      {canEdit && (
        <Card title="Your family support plan">
          <p className="mb-4 text-sm text-slate-600">Take it one step at a time. Start with the highlighted step.</p>
          <ol className="space-y-3">
            {steps.map((step, index) => {
              const active = index === currentStep;
              return (
                <li key={step.title} aria-current={active ? "step" : undefined}
                  className={`flex gap-3 rounded-xl p-3 ${active ? "bg-brand-50 ring-1 ring-brand-100" : ""}`}>
                  <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${step.complete ? "bg-emerald-100 text-emerald-800" : active ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-500"}`}>
                    {step.complete ? "✓" : index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className={`font-medium ${active ? "text-brand-800" : "text-slate-800"}`}>{step.title}</h3>
                      <span className="text-xs text-slate-500">{step.complete ? "Done" : active ? "Start here" : index > currentStep ? "Coming up" : "Not started"}</span>
                    </div>
                    <p className="mt-0.5 text-sm text-slate-600">{step.detail}</p>
                    {active && index === 0 && <Btn className="mt-3" onClick={() => go("children")}>Add a child</Btn>}
                    {active && index === 1 && <Btn className="mt-3" onClick={() => go("moves")}>Plan a move</Btn>}
                    {active && index === 2 && <Btn className="mt-3" onClick={() => go("moves")}>Check needs</Btn>}
                    {active && index === 3 && (
                      s.totals.open > 0
                        ? <Btn className="mt-3" onClick={() => go("followups")}>Review open needs</Btn>
                        : dest
                          ? <Link className="mt-3 inline-flex items-center rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700" to={`/services?district=${encodeURIComponent(dest)}`}>Find services near {dest}</Link>
                          : <p className="mt-2 text-sm text-slate-600">Your checked needs have an outcome recorded.</p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>
      )}
      <section aria-label="Family support summary">
        <h2 className="mb-2 text-lg font-semibold text-slate-900">At a glance</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Tile n={s.totals.open} text="needs still open" tone="amber" />
          <Tile n={s.totals.overdue} text="follow-ups past their due date" tone="red" />
          <Tile n={s.totals.not_assessed} text="needs not checked yet" tone="slate" />
        </div>
      </section>
      {s.totals.not_assessed > 0 && s.children.length > 0 && <Notice tone="amber">"Not checked yet" does not mean "no need". It means nobody has looked yet. Use "Check needs" on the Moves tab.</Notice>}
      <Card title="Still to be sorted out">
        {s.unresolved.length === 0 ? (
          <Empty title="No open needs">{s.children.length === 0 ? "Add a child and plan a move to see what support may be needed." : s.totals.not_assessed > 0 ? "Needs have not been checked yet, so this list is not complete." : "Everything that was checked has an outcome recorded."}</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {s.unresolved.map((u) => (
              <li key={u.need_id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{u.child_name} - {CATEGORY_LABEL[u.category]}</span>
                  <NeedBadge status={u.status} />
                  {u.overdue && <Badge tone="red">Overdue</Badge>}
                </div>
                <p className="mt-1 text-sm text-slate-600">{u.why}</p>
                {u.next_action && <p className="text-sm"><b>Next:</b> {u.next_action}{u.due_date ? ` (by ${fmtDate(u.due_date)})` : ""}</p>}
                <Link className="text-sm text-brand-700 underline" to={`/needs/${u.need_id}`}>Open details</Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {s.children.map((c) => (
        <Card key={c.child_id} title={c.child_name}>
          {c.needs.length === 0 ? <p className="text-sm text-slate-500">No needs have been checked for this child yet.</p> : (
            <ul className="grid gap-2 md:grid-cols-2">
              {c.needs.map((n) => (
                <li key={n.need_id} className="rounded-lg bg-slate-50 p-3">
                  <p className="text-sm font-medium">{CATEGORY_LABEL[n.category]}</p>
                  <div className="mt-1 flex flex-wrap gap-1"><NeedBadge status={n.status} />{n.confirmation && <Verification verified={n.confirmation.provider_verified} />}</div>
                  <Link className="text-xs text-brand-700 underline" to={`/needs/${n.need_id}`}>Details</Link>
                </li>
              ))}
            </ul>
          )}
          {c.not_assessed_categories.length > 0 && c.needs.length > 0 && <p className="mt-2 text-xs text-slate-500">Not checked yet: {c.not_assessed_categories.map((x) => CATEGORY_LABEL[x]).join(", ")}</p>}
        </Card>
      ))}
    </div>
  );
}

// ---------------- Children ----------------
function Children({ id, canEdit }: { id: string; canEdit: boolean }) {
  const kids = useLoad(() => api<Child[]>(`/families/${id}/children`), [id]);
  const f = useForm({ full_name: "", date_of_birth: "", approx_age_years: "", education_status: "UNKNOWN", current_school_name: "", accommodations_note: "" });
  const a = useAction();
  const [msg, setMsg] = useState("");
  async function add(e: FormEvent) {
    e.preventDefault();
    if (!f.v.date_of_birth && f.v.approx_age_years === "") { a.setError(new Error("Give a date of birth or an approximate age.")); return; }
    const c = await a.run(() => api<Child>(`/families/${id}/children`, { body: {
      full_name: f.v.full_name, date_of_birth: opt(f.v.date_of_birth),
      approx_age_years: f.v.approx_age_years === "" ? undefined : Number(f.v.approx_age_years),
      education_status: f.v.education_status, current_school_name: opt(f.v.current_school_name),
      accommodations_note: opt(f.v.accommodations_note),
    } }));
    if (c) { f.reset(); setMsg("Child added. Go to the Moves tab and choose \"Check needs\" so this child is included."); kids.reload(); }
  }
  return (
    <div className="space-y-5">
      {msg && <Notice>{msg}</Notice>}
      {kids.loading ? <Loading /> : kids.error ? <ErrorBox error={kids.error} /> : (kids.data ?? []).length === 0
        ? <Empty title="No children added yet">Add each child so Sahaayak can list what support they may need.</Empty>
        : (kids.data ?? []).map((c) => <ChildCard key={c.id} child={c} canEdit={canEdit} onChange={kids.reload} />)}
      {canEdit && (
        <Card title="Add a child">
          <form onSubmit={add} className="grid gap-4 md:grid-cols-2">
            <Field label="Child's name"><Input required maxLength={200} {...f.on("full_name")} /></Field>
            <Field label="Date of birth"><Input type="date" max={new Date().toISOString().slice(0, 10)} {...f.on("date_of_birth")} /></Field>
            <Field label="Or approximate age (years)" hint="Use this if you do not know the date of birth."><Input type="number" min={0} max={17} {...f.on("approx_age_years")} /></Field>
            <Field label="School status"><Select {...f.on("education_status")}>{Object.entries(EDU_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
            <Field label="Current school (optional)"><Input maxLength={200} {...f.on("current_school_name")} /></Field>
            <div><Field label="Support the child needs, if any (optional)"><Textarea maxLength={1000} {...f.on("accommodations_note")} /></Field><PrivateNoteWarning /></div>
            <div className="md:col-span-2 space-y-3"><ErrorBox error={a.error} /><Btn type="submit" disabled={a.busy}>Add child</Btn></div>
          </form>
        </Card>
      )}
    </div>
  );
}

function ChildCard({ child, canEdit, onChange }: { child: Child; canEdit: boolean; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const f = useForm({ education_status: child.education_status, current_school_name: child.current_school_name ?? "", accommodations_note: child.accommodations_note ?? "" });
  const a = useAction();
  async function save(e: FormEvent) {
    e.preventDefault();
    const r = await a.run(() => api(`/children/${child.id}`, { method: "PATCH", body: {
      education_status: f.v.education_status, current_school_name: opt(f.v.current_school_name) ?? null,
      accommodations_note: opt(f.v.accommodations_note) ?? null } }));
    if (r !== undefined) { setEditing(false); onChange(); }
  }
  async function remove() {
    if (!window.confirm(`Remove ${child.full_name} from this family?`)) return;
    await a.run(() => api(`/children/${child.id}`, { method: "DELETE" }));
    onChange();
  }
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-lg font-semibold">{child.full_name}</p>
          <p className="text-sm text-slate-600">{child.date_of_birth ? `Born ${fmtDate(child.date_of_birth)}` : `About ${child.approx_age_years} years old`} - {EDU_LABEL[child.education_status]}{child.current_school_name ? ` - ${child.current_school_name}` : ""}</p>
          {child.accommodations_note && <p className="text-sm text-slate-600">Support needed: {child.accommodations_note}</p>}
        </div>
        {canEdit && <div className="flex gap-2"><Btn variant="secondary" onClick={() => setEditing(!editing)}>{editing ? "Cancel" : "Edit"}</Btn><Btn variant="danger" onClick={() => void remove()}>Remove</Btn></div>}
      </div>
      {editing && (
        <form onSubmit={save} className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="School status"><Select {...f.on("education_status")}>{Object.entries(EDU_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <Field label="Current school"><Input maxLength={200} {...f.on("current_school_name")} /></Field>
          <div className="md:col-span-2"><Field label="Support the child needs"><Textarea maxLength={1000} {...f.on("accommodations_note")} /></Field><PrivateNoteWarning /></div>
          <div className="md:col-span-2 space-y-2"><ErrorBox error={a.error} /><Btn type="submit" disabled={a.busy}>Save</Btn></div>
        </form>
      )}
      {!editing && <ErrorBox error={a.error} />}
    </Card>
  );
}

// ---------------- Moves ----------------
function Moves({ id, canEdit, defaults }: { id: string; canEdit: boolean; defaults: Family }) {
  const migs = useLoad(() => api<Migration[]>(`/families/${id}/migrations`), [id]);
  const f = useForm({ origin_district: defaults.origin_district ?? "", origin_state: defaults.origin_state ?? "Maharashtra", destination_district: "", planned_date: "", work_category: "", notes: "" });
  const a = useAction();
  async function add(e: FormEvent) {
    e.preventDefault();
    const m = await a.run(() => api<Migration>(`/families/${id}/migrations`, { body: {
      origin_district: f.v.origin_district, origin_state: f.v.origin_state,
      destination_district: f.v.destination_district, destination_state: "Maharashtra",
      planned_date: opt(f.v.planned_date), work_category: opt(f.v.work_category), notes: opt(f.v.notes) } }));
    if (m) { f.set({ ...f.v, destination_district: "", planned_date: "", work_category: "", notes: "" }); migs.reload(); }
  }
  return (
    <div className="space-y-5">
      {migs.loading ? <Loading /> : migs.error ? <ErrorBox error={migs.error} /> : (migs.data ?? []).length === 0
        ? <Empty title="No moves recorded">Plan a move below. Sahaayak will then list what each child may need at the destination.</Empty>
        : (migs.data ?? []).map((m) => <MoveCard key={m.id} m={m} canEdit={canEdit} onChange={migs.reload} />)}
      {canEdit && (
        <Card title="Plan a move">
          <form onSubmit={add} className="grid gap-4 md:grid-cols-2">
            <Field label="Moving from (district)"><Input required list="districts" {...f.on("origin_district")} /></Field>
            <Field label="State you are leaving"><Input required {...f.on("origin_state")} /></Field>
            <Field label="Moving to (district)" hint="Destinations in Maharashtra only for now."><Input required list="districts" {...f.on("destination_district")} /></Field>
            <Field label="Planned move date (optional)"><Input type="date" {...f.on("planned_date")} /></Field>
            <Field label="Type of work (optional)"><Input maxLength={100} {...f.on("work_category")} /></Field>
            <div><Field label="Notes (optional)"><Textarea maxLength={1000} {...f.on("notes")} /></Field><PrivateNoteWarning /></div>
            <div className="space-y-3 md:col-span-2"><ErrorBox error={a.error} onPick={(s) => f.set({ ...f.v, destination_district: s })} /><Btn type="submit" disabled={a.busy}>Save plan</Btn></div>
          </form>
        </Card>
      )}
    </div>
  );
}

function MoveCard({ m, canEdit, onChange }: { m: Migration; canEdit: boolean; onChange: () => void }) {
  const a = useAction();
  const [info, setInfo] = useState("");
  const [editing, setEditing] = useState(false);
  const f = useForm({ destination_district: m.destination_district, planned_date: m.planned_date ?? "", notes: m.notes ?? "" });
  const tone = m.status === "ACTIVE" ? "blue" : m.status === "CANCELLED" ? "slate" : m.status === "COMPLETED" ? "teal" : "amber";
  async function setStatus(status: string) {
    if (status === "CANCELLED" && !window.confirm("Cancel this move?")) return;
    if (await a.run(() => api(`/migrations/${m.id}/status`, { body: { status } }))) onChange();
  }
  async function assess() {
    const r = await a.run(() => api<{ created_needs: number; existing_needs: number }>(`/migrations/${m.id}/assess`, { method: "POST" }));
    if (r) setInfo(r.created_needs ? `Checked: ${r.created_needs} new need(s) added. They are open until an outcome is recorded.` : "Nothing new to add. All needs for this move were already checked.");
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    const r = await a.run(() => api(`/migrations/${m.id}`, { method: "PATCH", body: {
      destination_district: f.v.destination_district, planned_date: opt(f.v.planned_date) ?? null, notes: opt(f.v.notes) ?? null } }));
    if (r) { setEditing(false); onChange(); }
  }
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-lg font-semibold">{m.origin_district} to {m.destination_district}</p><Badge tone={tone}>{label(m.status)}</Badge>
      </div>
      <p className="text-sm text-slate-600">Planned {fmtDate(m.planned_date)}{m.actual_date ? ` - moved ${fmtDate(m.actual_date)}` : ""}</p>
      {canEdit && m.status !== "CANCELLED" && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Btn onClick={() => void assess()} disabled={a.busy}>Check needs for this move</Btn>
          {m.status === "PLANNED" && <><Btn variant="secondary" onClick={() => setEditing(!editing)}>Edit plan</Btn><Btn variant="secondary" onClick={() => void setStatus("ACTIVE")}>We have started the move</Btn></>}
          {m.status === "ACTIVE" && <Btn variant="secondary" onClick={() => void setStatus("COMPLETED")}>We have arrived</Btn>}
          {m.status !== "COMPLETED" && <Btn variant="danger" onClick={() => void setStatus("CANCELLED")}>Cancel move</Btn>}
          <Link className="inline-flex items-center rounded-lg border border-slate-300 px-4 py-2 text-sm" to={`/services?district=${encodeURIComponent(m.destination_district)}`}>Find services</Link>
        </div>
      )}
      {editing && (
        <form onSubmit={save} className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Moving to (district)"><Input required list="districts" {...f.on("destination_district")} /></Field>
          <Field label="Planned date"><Input type="date" {...f.on("planned_date")} /></Field>
          <div className="md:col-span-2"><Field label="Notes"><Textarea maxLength={1000} {...f.on("notes")} /></Field></div>
          <div className="space-y-2 md:col-span-2"><p className="text-xs text-amber-800">Changing the destination withdraws any referrals made for the old one.</p><ErrorBox error={a.error} onPick={(s) => f.set({ ...f.v, destination_district: s })} /><Btn type="submit">Save</Btn></div>
        </form>
      )}
      {info && <div className="mt-3"><Notice>{info}</Notice></div>}
      {!editing && <div className="mt-3"><ErrorBox error={a.error} /></div>}
      {m.status === "COMPLETED" && <p className="mt-3 text-xs text-slate-500">Arriving does not mean services are in place. Open needs stay open until an outcome is recorded.</p>}
    </Card>
  );
}

// ---------------- Follow-ups ----------------
function FollowUps({ id, canEdit }: { id: string; canEdit: boolean }) {
  const q = useLoad(() => api<FollowUp[]>(`/families/${id}/follow-ups`, { query: { limit: 100 } }), [id]);
  const a = useAction();
  if (q.loading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const all = q.data ?? [];
  const active = all.filter((x) => x.status === "OPEN" || x.status === "IN_PROGRESS");
  const done = all.filter((x) => !active.includes(x));
  async function act(fuId: string, what: "complete" | "cancel") {
    if (await a.run(() => api(`/follow-ups/${fuId}/${what}`, { method: "POST", body: what === "complete" ? {} : undefined }))) q.reload();
  }
  return (
    <div className="space-y-5">
      <Notice>Finishing a follow-up task does not mean the need is solved. Record the outcome on the need itself.</Notice>
      <ErrorBox error={a.error} />
      <Card title="Open follow-ups">
        {active.length === 0 ? <Empty title="Nothing to follow up right now">Follow-ups appear when needs are checked or when a provider asks for something.</Empty> : (
          <ul className="divide-y divide-slate-100">
            {active.map((x) => (
              <li key={x.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{x.description}</span>{x.is_overdue && <Badge tone="red">Overdue</Badge>}<Badge tone={x.priority === "HIGH" || x.priority === "URGENT" ? "amber" : "slate"}>{label(x.priority)}</Badge></div>
                <p className="text-sm text-slate-600">Due {fmtDate(x.due_date)}</p>
                <div className="mt-1 flex flex-wrap items-center gap-3">
                  <Link className="text-sm text-brand-700 underline" to={`/needs/${x.need_id}`}>Open the need</Link>
                  {canEdit && <><Btn variant="secondary" onClick={() => void act(x.id, "complete")}>Mark task done</Btn><Btn variant="link" onClick={() => void act(x.id, "cancel")}>Cancel task</Btn></>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {done.length > 0 && <Card title="Finished"><ul className="space-y-1 text-sm text-slate-600">{done.map((x) => <li key={x.id}>{x.description} - {label(x.status)}</li>)}</ul></Card>}
    </div>
  );
}

// ---------------- Referrals and contacts ----------------
function History({ id, canEdit }: { id: string; canEdit: boolean }) {
  const refs = useLoad(() => api<Referral[]>(`/families/${id}/referrals`), [id]);
  const cons = useLoad(() => api<Contact[]>(`/families/${id}/contact-attempts`), [id]);
  const a = useAction();
  async function act(refId: string, what: "withdraw" | "no-response") {
    if (await a.run(() => api(`/referrals/${refId}/${what}`, { method: "POST" }))) refs.reload();
  }
  if (refs.loading || cons.loading) return <Loading />;
  if (refs.error) return <ErrorBox error={refs.error} />;
  const active = ["RECORDED", "ACCEPTED", "INFO_REQUESTED"];
  return (
    <div className="space-y-5">
      <ErrorBox error={a.error} />
      <Card title="Referrals">
        <p className="mb-3 text-sm text-slate-500">A referral is not acceptance, and acceptance is not support received. Each step is shown as it happens.</p>
        {(refs.data ?? []).length === 0 ? <Empty title="No referrals yet">Search for a service and record a referral from a need's page.</Empty> : (
          <ul className="divide-y divide-slate-100">
            {(refs.data ?? []).map((r) => (
              <li key={r.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{r.service_name}</span><Badge tone={r.status === "DECLINED" ? "red" : r.status === "ACCEPTED" ? "blue" : "slate"}>{label(r.status)}</Badge>{r.service_verification_status === "SAMPLE" && <Badge tone="amber">Sample listing</Badge>}</div>
                <p className="text-sm text-slate-600">{r.plain_status} Recorded {fmtDate(r.referred_at)}.</p>
                {r.provider_responses.map((p) => <p key={p.id} className="text-sm"><b>{label(p.response_type)}:</b> {p.message ?? p.barrier ?? ""} <span className="text-slate-400">({fmtDate(p.responded_at)})</span></p>)}
                <div className="mt-1 flex gap-3"><Link className="text-sm text-brand-700 underline" to={`/needs/${r.need_id}`}>Open the need</Link>
                  {canEdit && active.includes(r.status) && <Btn variant="link" onClick={() => void act(r.id, "withdraw")}>Withdraw</Btn>}
                  {canEdit && r.status === "RECORDED" && <Btn variant="link" onClick={() => void act(r.id, "no-response")}>No reply after a week</Btn>}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Contact attempts">
        {(cons.data ?? []).length === 0 ? <Empty title="No contact attempts recorded" /> : (
          <ul className="space-y-2 text-sm">{(cons.data ?? []).map((c) => <li key={c.id}>{fmtDate(c.attempted_at)} - {label(c.method)} - {c.service_name ?? "service"}: {label(c.result)}{c.note ? ` (${c.note})` : ""}</li>)}</ul>
        )}
      </Card>
    </div>
  );
}

// ---------------- Sharing ----------------
function Sharing({ id }: { id: string }) {
  const rows = useLoad(() => api<AccessRow[]>(`/families/${id}/access`), [id]);
  const f = useForm({ email: "" });
  const a = useAction();
  async function grant(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api(`/families/${id}/access`, { body: { email: f.v.email } }))) { f.reset(); rows.reload(); }
  }
  async function revoke(accessId: string) {
    if (await a.run(() => api(`/families/${id}/access/${accessId}`, { method: "DELETE" }))) rows.reload();
  }
  return (
    <div className="space-y-5">
      <Card title="Who can see this family">
        {rows.loading ? <Loading /> : rows.error ? <ErrorBox error={rows.error} /> : (
          <ul className="divide-y divide-slate-100">
            {(rows.data ?? []).map((r) => (
              <li key={r.id} className="flex items-center justify-between py-2 text-sm">
                <span>{r.user_name} - {r.access_level === "OWNER" ? "you" : "support worker (view only)"}</span>
                {r.access_level !== "OWNER" && <Btn variant="danger" onClick={() => void revoke(r.id)}>Remove access</Btn>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Share with a support worker">
        <form onSubmit={grant} className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1"><Field label="Their email address"><Input type="email" required {...f.on("email")} /></Field></div>
          <Btn type="submit" disabled={a.busy}>Share</Btn>
        </form>
        <div className="mt-3"><ErrorBox error={a.error} /></div>
        <p className="mt-2 text-xs text-slate-500">They can view your family, children, moves and needs, but cannot change anything. You can remove access at any time.</p>
      </Card>
    </div>
  );
}