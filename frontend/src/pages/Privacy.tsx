import { api } from "../api";
import { useAuth } from "../auth";
import type { Family } from "../types";
import { Card, Notice, fmtDate, label, useLoad } from "../ui";

export default function Privacy() {
  const { user } = useAuth();
  const fams = useLoad(() => (user?.role === "CITIZEN" ? api<Family[]>("/families") : Promise.resolve([] as Family[])), [user?.role]);
  if (!user) return null;
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Your account and privacy</h1>
      <Card title="Account">
        <dl className="space-y-1 text-sm"><div>Name: {user.full_name}</div><div>Email: {user.email}</div><div>Role: {label(user.role)}</div></dl>
      </Card>
      {user.role === "CITIZEN" && (
        <Card title="Consent you gave">
          {(fams.data ?? []).length === 0 ? <p className="text-sm text-slate-500">No family profile yet.</p> : (
            <ul className="space-y-1 text-sm">{(fams.data ?? []).map((f) => <li key={f.id}>{f.household_name}: agreed on {fmtDate(f.consent_given_at)} (privacy notice {f.privacy_notice_version})</li>)}</ul>)}
        </Card>
      )}
      <Card title="How your information is used">
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>Only you, and support workers you choose to share with, can see your family's records.</li>
          <li>A provider you refer your child to sees only what is needed to respond. Your phone number is shared only after they accept.</li>
          <li>Government planning dashboards show totals only. Small groups are hidden and no names or addresses appear.</li>
          <li>Important changes are recorded in an audit history, without private details.</li>
        </ul>
      </Card>
      <Notice tone="amber">Requests to export or delete your data are not automated yet. Ask your administrator.</Notice>
    </div>
  );
}