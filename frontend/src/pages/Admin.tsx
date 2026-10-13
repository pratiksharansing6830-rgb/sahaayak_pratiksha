import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import type { AuditEvent, Organization, Service, User } from "../types";
import { Badge, Btn, CATEGORY_LABEL, Card, Empty, ErrorBox, Field, Input, Loading, Notice, Select, fmtDate, label, opt, useAction, useForm, useLoad } from "../ui";

type Tab = "users" | "orgs" | "directory" | "audit" | "health";
const ROLES = ["CITIZEN", "SCHOOL", "HEALTHCARE", "NGO", "GOVERNMENT", "ADMIN"];

export default function Admin() {
  const [tab, setTab] = useState<Tab>("users");
  const orgs = useLoad(() => api<Organization[]>("/admin/organizations", { query: { limit: 200 } }), []);
  const tabs: [Tab, string][] = [["users", "Users and roles"], ["orgs", "Organisations"], ["directory", "Service directory"], ["audit", "Audit history"], ["health", "Platform health"]];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Administration</h1>
      <Notice>Administrators manage accounts, organisations and the directory. They cannot see family or child records.</Notice>
      <div role="tablist" className="flex flex-wrap gap-1 border-b border-slate-200">
        {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`rounded-t-lg px-4 py-2 text-sm font-medium ${tab === k ? "bg-white text-brand-700 ring-1 ring-slate-200" : "text-slate-600"}`}>{l}</button>)}
      </div>
      {tab === "users" && <Users orgs={orgs.data ?? []} />}
      {tab === "orgs" && <Orgs q={orgs} />}
      {tab === "directory" && <Directory orgs={orgs.data ?? []} />}
      {tab === "audit" && <Audit />}
      {tab === "health" && <Health />}
    </div>
  );
}

function Users({ orgs }: { orgs: Organization[] }) {
  const q = useLoad(() => api<User[]>("/admin/users", { query: { limit: 200 } }), []);
  const f = useForm({ full_name: "", email: "", password: "", role: "SCHOOL", organization_id: "" });
  const a = useAction();
  async function add(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api("/admin/users", { body: { ...f.v, organization_id: opt(f.v.organization_id) ?? null } }))) { f.reset(); q.reload(); }
  }
  async function patch(id: string, body: object) { if (await a.run(() => api(`/admin/users/${id}`, { method: "PATCH", body }))) q.reload(); }
  return (
    <div className="space-y-5">
      <ErrorBox error={a.error} />
      <Card title="Accounts">
        {q.loading ? <Loading /> : q.error ? <ErrorBox error={q.error} /> : (
          <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="text-slate-500"><th className="py-2">Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead><tbody>
            {(q.data ?? []).map((u) => (
              <tr key={u.id} className="border-t border-slate-100"><td className="py-2">{u.full_name}</td><td>{u.email}</td>
                <td><Select aria-label={`Role for ${u.email}`} value={u.role} onChange={(e) => void patch(u.id, { role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</Select></td>
                <td>{u.is_active ? <Badge tone="teal">Active</Badge> : <Badge>Inactive</Badge>}</td>
                <td><Btn variant="secondary" onClick={() => void patch(u.id, { is_active: !u.is_active })}>{u.is_active ? "Deactivate" : "Activate"}</Btn></td></tr>))}
          </tbody></table></div>)}
      </Card>
      <Card title="Create an account">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-2">
          <Field label="Full name"><Input required {...f.on("full_name")} /></Field>
          <Field label="Email"><Input type="email" required {...f.on("email")} /></Field>
          <Field label="Temporary password" hint="At least 8 characters. Ask the user to keep it private."><Input type="password" required minLength={8} maxLength={72} autoComplete="new-password" {...f.on("password")} /></Field>
          <Field label="Role"><Select {...f.on("role")}>{ROLES.map((r) => <option key={r}>{r}</option>)}</Select></Field>
          <Field label="Organisation (required for school, healthcare and NGO)"><Select {...f.on("organization_id")}><option value="">None</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select></Field>
          <div className="flex items-end"><Btn type="submit" disabled={a.busy}>Create account</Btn></div>
        </form>
      </Card>
    </div>
  );
}

function Orgs({ q }: { q: ReturnType<typeof useLoad<Organization[]>> }) {
  const f = useForm({ name: "", org_type: "SCHOOL", district: "" });
  const a = useAction();
  async function add(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api("/admin/organizations", { body: { name: f.v.name, org_type: f.v.org_type, district: opt(f.v.district), state: "Maharashtra" } }))) { f.reset(); q.reload(); }
  }
  return (
    <div className="space-y-5">
      <Card title="Organisations">{(q.data ?? []).length === 0 ? <Empty title="No organisations yet" /> : <ul className="divide-y divide-slate-100 text-sm">{(q.data ?? []).map((o) => <li key={o.id} className="py-2">{o.name} - {label(o.org_type)}{o.district ? ` - ${o.district}` : ""}</li>)}</ul>}</Card>
      <Card title="Add an organisation"><form onSubmit={add} className="grid gap-3 md:grid-cols-4">
        <Field label="Name"><Input required {...f.on("name")} /></Field>
        <Field label="Type"><Select {...f.on("org_type")}>{["SCHOOL", "HEALTHCARE", "NGO", "GOVERNMENT", "OTHER"].map((k) => <option key={k}>{k}</option>)}</Select></Field>
        <Field label="District"><Input list="districts" {...f.on("district")} /></Field>
        <div className="flex items-end"><Btn type="submit" disabled={a.busy}>Add</Btn></div>
        <div className="md:col-span-4"><ErrorBox error={a.error} /></div></form></Card>
    </div>
  );
}

function Directory({ orgs }: { orgs: Organization[] }) {
  const q = useLoad(() => api<Service[]>("/admin/services", { query: { limit: 200, include_inactive: true } }), []);
  const f = useForm({ name: "", category: "EDUCATION", district: "", address: "", contact_phone: "", operating_hours: "", data_source: "", verification_status: "UNVERIFIED", organization_id: "", latitude: "", longitude: "" });
  const a = useAction();
  async function add(e: FormEvent) {
    e.preventDefault();
    const body = { name: f.v.name, category: f.v.category, district: f.v.district, address: opt(f.v.address), contact_phone: opt(f.v.contact_phone), operating_hours: opt(f.v.operating_hours), data_source: opt(f.v.data_source), verification_status: f.v.verification_status, organization_id: opt(f.v.organization_id), latitude: f.v.latitude ? Number(f.v.latitude) : undefined, longitude: f.v.longitude ? Number(f.v.longitude) : undefined, coordinates_approximate: true };
    if (await a.run(() => api("/admin/services", { body }))) { f.reset(); q.reload(); }
  }
  async function verify(s: Service) {
    const src = window.prompt("How was this verified? (source, required)");
    if (src) { if (await a.run(() => api(`/admin/services/${s.id}`, { method: "PATCH", body: { verification_status: "VERIFIED", data_source: src } }))) q.reload(); }
  }
  async function deactivate(s: Service) { if (window.confirm(`Deactivate ${s.name}?`) && await a.run(() => api(`/admin/services/${s.id}`, { method: "DELETE" }))) q.reload(); }
  return (
    <div className="space-y-5">
      <ErrorBox error={a.error} />
      <Card title="Directory entries">
        {q.loading ? <Loading /> : (q.data ?? []).length === 0 ? <Empty title="The directory is empty">Add real services below. Families see only what is listed here.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">{(q.data ?? []).map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>{s.name} - {CATEGORY_LABEL[s.category]} - {s.district} <Badge tone={s.is_verified ? "green" : "slate"}>{label(s.verification_status)}</Badge> {!s.is_active && <Badge tone="red">Inactive</Badge>}</span>
              <span className="flex gap-2">{!s.is_verified && s.is_active && <Btn variant="secondary" onClick={() => void verify(s)}>Mark verified</Btn>}{s.is_active && <Btn variant="danger" onClick={() => void deactivate(s)}>Deactivate</Btn>}</span>
            </li>))}</ul>)}
      </Card>
      <Card title="Add a service">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-3">
          <Field label="Name"><Input required {...f.on("name")} /></Field>
          <Field label="Type"><Select {...f.on("category")}>{Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <Field label="District"><Input required list="districts" {...f.on("district")} /></Field>
          <Field label="Address"><Input {...f.on("address")} /></Field>
          <Field label="Phone (only if verified)"><Input type="tel" pattern="[+0-9][0-9 \-]{6,19}" {...f.on("contact_phone")} /></Field>
          <Field label="Opening hours (only if known)"><Input {...f.on("operating_hours")} /></Field>
          <Field label="Latitude (optional)"><Input type="number" step="any" {...f.on("latitude")} /></Field>
          <Field label="Longitude (optional)"><Input type="number" step="any" {...f.on("longitude")} /></Field>
          <Field label="Owning organisation" hint="Providers see referrals only for services owned by their organisation."><Select {...f.on("organization_id")}><option value="">None</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</Select></Field>
          <Field label="Data source"><Input {...f.on("data_source")} /></Field>
          <Field label="Status"><Select {...f.on("verification_status")}><option value="UNVERIFIED">Not verified</option><option value="VERIFIED">Verified (needs a data source)</option></Select></Field>
          <div className="flex items-end"><Btn type="submit" disabled={a.busy}>Add service</Btn></div>
        </form>
        <p className="mt-2 text-xs text-slate-500">Only add details you have checked. Do not guess phone numbers, hours or locations.</p>
      </Card>
    </div>
  );
}

function Audit() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const q = useLoad(() => api<AuditEvent[]>("/admin/audit-events", { query: { action, limit: 50, offset: page * 50 } }), [action, page]);
  return (
    <Card title="Audit history">
      <div className="mb-3 max-w-sm"><Field label="Filter by action (exact name)"><Input placeholder="e.g. NEED_STATUS_CHANGED" value={action} onChange={(e) => { setAction(e.target.value.trim()); setPage(0); }} /></Field></div>
      {q.loading ? <Loading /> : q.error ? <ErrorBox error={q.error} /> : (q.data ?? []).length === 0 ? <Empty title="No events" /> : (
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="text-slate-500"><th className="py-2">When</th><th>Who</th><th>Action</th><th>Change</th></tr></thead><tbody>
          {(q.data ?? []).map((e) => <tr key={e.id} className="border-t border-slate-100"><td className="py-1.5">{new Date(e.created_at).toLocaleString("en-IN")}</td><td>{e.actor_role ?? "system"}</td><td>{e.action}</td><td>{e.from_value ? `${e.from_value} to ` : ""}{e.to_value ?? ""}</td></tr>)}
        </tbody></table></div>)}
      <div className="mt-3 flex gap-2"><Btn variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Newer</Btn><Btn variant="secondary" disabled={(q.data ?? []).length < 50} onClick={() => setPage(page + 1)}>Older</Btn></div>
    </Card>
  );
}

function Health() {
  const q = useLoad(() => api<Record<string, unknown>>("/admin/health"), []);
  if (q.loading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  return <Card title="Platform health"><pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify(q.data, null, 2)}</pre><p className="mt-2 text-xs text-slate-500">Counts only. No personal details.</p></Card>;
}