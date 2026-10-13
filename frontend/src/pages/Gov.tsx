import { useState } from "react";
import type { FormEvent } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { District } from "../types";
import { Badge, Btn, CATEGORY_LABEL, Card, Empty, ErrorBox, Field, Input, Loading, Notice, Select, label, opt, useForm, useLoad } from "../ui";

type N = number | null;
interface Privacy { min_group_size: number; rule: string; data_basis: string }
interface Overview { privacy: Privacy; families_registered: N; children_registered: N; migrations_by_status: Record<string, N>; children_with_open_needs: N; open_needs: N; children_with_overdue_needs: N; children_with_overdue_followups: N; children_with_followups_due: N; children_support_confirmed_by_provider: N; children_support_confirmed_by_family_only: N; confirmation_rate: { rate_percent: N; note: string }; notes: string[] }
interface CatRow { category: string; children_with_open_needs: number; open_needs: number; children_overdue: N; children_awaiting_provider: N }
interface DestRow { destination_district: string; families_moving: number; planned: N; active: N; completed: N; children_with_open_needs: N }
interface TrendPt { month: string; new_families: N; families_with_new_migrations: N; children_with_provider_confirmed_outcomes: N }
interface GapRow { destination_district: string; category: string; children_with_open_needs: number; directory_listings: number; coverage: string; potential_gap: boolean; explanation: string }
interface PriRow { destination_district: string; category: string; score: number; band: string; children_with_open_needs: number; factors: { name: string; points: number; max_points: number; detail: string }[] }
interface AlertRow { code: string; severity: string; title: string; children_count: number; observation: string; window: string; limitations: string; suggested_action: string; basis: string }
interface Data {
  overview: Overview; cat: { rows: CatRow[]; groups_hidden: number }; dest: { rows: DestRow[]; groups_hidden: number };
  trends: { points: TrendPt[]; note: string }; gaps: { rows: GapRow[]; groups_hidden: number; note: string };
  pri: { rows: PriRow[]; disclaimer: string }; alerts: { alerts: AlertRow[]; note: string };
}

const Hidden = () => <span className="text-sm font-normal text-slate-400" title="Fewer people than the privacy threshold">hidden</span>;
const Stat = ({ text, n }: { text: string; n: N }) => (
  <div className="rounded-xl bg-white p-4 ring-1 ring-slate-200"><p className="text-3xl font-bold text-slate-800">{n === null ? <Hidden /> : n}</p><p className="text-sm text-slate-600">{text}</p></div>
);
const tone = (b: string) => (b === "HIGH" ? "red" : b === "MEDIUM" ? "amber" : "slate");

export default function Gov() {
  const f = useForm({ from_date: "", to_date: "", district: "", category: "" });
  const [applied, setApplied] = useState(f.v);
  const districts = useLoad(() => api<District[]>("/services/districts"), []);
  const q = useLoad<Data>(async () => {
    const dates = { from_date: opt(applied.from_date), to_date: opt(applied.to_date) };
    const area = { ...dates, district: opt(applied.district), category: opt(applied.category) };
    const [overview, cat, dest, trends, gaps, pri, alerts] = await Promise.all([
      api<Data["overview"]>("/gov/overview", { query: dates }),
      api<Data["cat"]>("/gov/unresolved-by-category", { query: area }),
      api<Data["dest"]>("/gov/destinations", { query: area }),
      api<Data["trends"]>("/gov/trends", { query: { months: 12 } }),
      api<Data["gaps"]>("/gov/service-gaps", { query: area }),
      api<Data["pri"]>("/gov/priority", { query: area }),
      api<Data["alerts"]>("/gov/alerts", { query: area }),
    ]);
    return { overview, cat, dest, trends, gaps, pri, alerts };
  }, [applied]);

  function apply(e: FormEvent) { e.preventDefault(); setApplied({ ...f.v }); }
  const d = q.data;
  const coords = new Map((districts.data ?? []).map((x) => [x.name, x]));

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Planning dashboard</h1>
      <Card>
        <form onSubmit={apply} className="grid gap-3 md:grid-cols-5">
          <Field label="From"><Input type="date" {...f.on("from_date")} /></Field>
          <Field label="To"><Input type="date" {...f.on("to_date")} /></Field>
          <Field label="Destination district"><Input list="districts" {...f.on("district")} /></Field>
          <Field label="Service"><Select {...f.on("category")}><option value="">All</option>{Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <div className="flex items-end"><Btn type="submit">Apply filters</Btn></div>
        </form>
        <p className="mt-2 text-xs text-slate-500">Date filters apply to every section. District and service filters apply to all sections except the overview.</p>
      </Card>
      {q.loading && !d ? <Loading /> : q.error || !d ? <ErrorBox error={q.error} /> : (
        <>
          <Notice>
            <b>Privacy:</b> {d.overview.privacy.rule} {d.overview.privacy.data_basis}
          </Notice>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat text="families registered" n={d.overview.families_registered} />
            <Stat text="children registered" n={d.overview.children_registered} />
            <Stat text="children with open needs" n={d.overview.children_with_open_needs} />
            <Stat text="children with overdue needs" n={d.overview.children_with_overdue_needs} />
            <Stat text="children with overdue follow-ups" n={d.overview.children_with_overdue_followups} />
            <Stat text="children confirmed by a provider" n={d.overview.children_support_confirmed_by_provider} />
            <Stat text="children reported by family only" n={d.overview.children_support_confirmed_by_family_only} />
            <div className="rounded-xl bg-white p-4 ring-1 ring-slate-200"><p className="text-3xl font-bold text-slate-800">{d.overview.confirmation_rate.rate_percent === null ? <Hidden /> : `${d.overview.confirmation_rate.rate_percent}%`}</p><p className="text-sm text-slate-600">referred children with provider-confirmed support</p></div>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            {Object.entries(d.overview.migrations_by_status).map(([k, v]) => <Badge key={k}>{label(k)} moves: {v === null ? "hidden" : v}</Badge>)}
          </div>
          <p className="text-xs text-slate-500">{d.overview.notes.join(" ")}</p>

          <Card title="Open needs by service">
            {d.cat.rows.length === 0 ? <Empty title="No groups large enough to show">{d.cat.groups_hidden > 0 ? `${d.cat.groups_hidden} smaller group(s) are hidden to protect privacy.` : "No open needs have been recorded yet."}</Empty> : (
              <div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={d.cat.rows.map((r) => ({ name: CATEGORY_LABEL[r.category], children: r.children_with_open_needs, overdue: r.children_overdue ?? 0 }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
                <Bar dataKey="children" name="Children with open needs" fill="#0f7567" /><Bar dataKey="overdue" name="Overdue (hidden if small)" fill="#b45309" /></BarChart></ResponsiveContainer></div>)}
          </Card>

          <Card title="Where families are moving">
            {d.dest.rows.length === 0 ? <Empty title="No destinations large enough to show">{d.dest.groups_hidden > 0 ? `${d.dest.groups_hidden} smaller group(s) are hidden.` : "No moves have been recorded yet."}</Empty> : (
              <div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={d.dest.rows.map((r) => ({ name: r.destination_district, families: r.families_moving }))}>
                <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="families" name="Families moving" fill="#0f7567" /></BarChart></ResponsiveContainer></div>)}
          </Card>

          <Card title="Trends (last 12 months)">
            <div className="h-64"><ResponsiveContainer width="100%" height="100%"><LineChart data={d.trends.points.map((p) => ({ month: p.month, "New families": p.new_families ?? undefined, "Families with new moves": p.families_with_new_migrations ?? undefined, "Children with provider-confirmed outcomes": p.children_with_provider_confirmed_outcomes ?? undefined }))}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
              <Line dataKey="New families" stroke="#0f7567" /><Line dataKey="Families with new moves" stroke="#b45309" /><Line dataKey="Children with provider-confirmed outcomes" stroke="#2563eb" /></LineChart></ResponsiveContainer></div>
            <p className="text-xs text-slate-500">Gaps in a line mean the figure was too small to show, or zero. {d.trends.note}</p>
          </Card>

          <Card title="Potential service gaps">
            <p className="mb-3 text-sm text-slate-600">{d.gaps.note}</p>
            {d.gaps.rows.length === 0 ? <Empty title="No gaps to show">{d.gaps.groups_hidden > 0 ? `${d.gaps.groups_hidden} smaller group(s) are hidden.` : "No open needs have been recorded yet."}</Empty> : (
              <>
                <MapContainer center={[19.0, 76.0]} zoom={6} scrollWheelZoom={false} className="h-80 w-full rounded-2xl">
                  <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  {d.gaps.rows.map((g) => { const c = coords.get(g.destination_district); return c ? (
                    <CircleMarker key={g.destination_district + g.category} center={[c.latitude, c.longitude]} radius={6 + Math.sqrt(g.children_with_open_needs) * 3} pathOptions={{ color: g.potential_gap ? "#b91c1c" : "#0f7567", fillOpacity: 0.4 }}>
                      <Popup><b>{g.destination_district} - {CATEGORY_LABEL[g.category]}</b><br />{g.explanation}</Popup></CircleMarker>) : null; })}
                </MapContainer>
                <p className="mt-1 text-xs text-slate-500">Markers sit at approximate district centres. Red means a potential gap.</p>
                <ul className="mt-3 divide-y divide-slate-100 text-sm">{d.gaps.rows.map((g) => <li key={g.destination_district + g.category} className="py-2"><b>{g.destination_district} - {CATEGORY_LABEL[g.category]}</b> <Badge tone={g.potential_gap ? "red" : "teal"}>{g.potential_gap ? "Potential gap" : "Listed"}</Badge><br />{g.explanation}</li>)}</ul>
              </>)}
          </Card>

          <Card title="Where to look first (rules-based)">
            <p className="mb-3 text-sm text-slate-600">{d.pri.disclaimer}</p>
            {d.pri.rows.length === 0 ? <Empty title="Nothing to rank yet" /> : d.pri.rows.map((r) => (
              <details key={r.destination_district + r.category} className="border-b border-slate-100 py-2">
                <summary className="cursor-pointer text-sm"><b>{r.destination_district} - {CATEGORY_LABEL[r.category]}</b> <Badge tone={tone(r.band)}>{r.band}</Badge> score {r.score} - {r.children_with_open_needs} children</summary>
                <ul className="mt-2 space-y-1 pl-4 text-sm text-slate-600">{r.factors.map((x) => <li key={x.name}><b>{x.name}:</b> {x.points} of {x.max_points}. {x.detail}</li>)}</ul>
              </details>))}
          </Card>

          <Card title="Early-warning alerts">
            <p className="mb-3 text-sm text-slate-600">{d.alerts.note}</p>
            {d.alerts.alerts.length === 0 ? <Empty title="No alerts">Alerts appear only when a group is large enough to show safely.</Empty> : (
              <ul className="space-y-3">{d.alerts.alerts.map((a, i) => (
                <li key={i} className="rounded-xl bg-slate-50 p-4 text-sm">
                  <p className="font-semibold">{a.title} <Badge tone={a.severity === "ATTENTION" ? "red" : "amber"}>{a.severity}</Badge></p>
                  <p className="mt-1"><b>Observed:</b> {a.observation}</p><p><b>Time window:</b> {a.window}</p>
                  <p><b>Limits:</b> {a.limitations}</p><p><b>Suggested human action:</b> {a.suggested_action}</p>
                </li>))}</ul>)}
          </Card>
        </>
      )}
    </div>
  );
}