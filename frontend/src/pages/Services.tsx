import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Need, SearchResult, Service } from "../types";
import { Badge, Btn, CATEGORY_LABEL, Card, Empty, ErrorBox, Field, Input, Notice, Select, Textarea, label, opt, useAction, useForm, useLoad } from "../ui";

const COLOR: Record<string, string> = { VERIFIED: "#0f7567", UNVERIFIED: "#b45309", SAMPLE: "#64748b" };

export default function Services() {
  const [params] = useSearchParams();
  const needId = params.get("need");
  const { user } = useAuth();
  const need = useLoad(() => (needId ? api<Need>(`/needs/${needId}`) : Promise.resolve(null)), [needId]);
  const f = useForm({ district: params.get("district") ?? "", category: "", sample: false as boolean });
  const a = useAction();
  const [res, setRes] = useState<SearchResult | null>(null);

  async function search(e?: FormEvent) {
    e?.preventDefault();
    const r = await a.run(() => api<SearchResult>("/services", { query: { district: f.v.district, category: f.v.category || need.data?.category, include_sample: f.v.sample } }));
    if (r) setRes(r);
  }
  useEffect(() => {
    if (!need.loading && f.v.district) void search();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [need.loading]);

  const category = f.v.category || need.data?.category || "";
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Find services</h1>
      {need.data && <Notice>Looking for <b>{CATEGORY_LABEL[need.data.category]}</b> services for the need "{need.data.need_description}". <Link className="underline" to={`/needs/${need.data.id}`}>Back to the need</Link></Notice>}
      <Notice tone="amber">These are potentially suitable services. Sahaayak does not confirm that a service is open, has places or will accept your child.</Notice>
      <Card>
        <form onSubmit={search} className="grid gap-3 md:grid-cols-4">
          <Field label="District"><Input required list="districts" {...f.on("district")} /></Field>
          <Field label="Type of service"><Select {...f.on("category")}><option value="">{need.data ? `${CATEGORY_LABEL[need.data.category]} (for this need)` : "All"}</option>{Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={f.v.sample} onChange={(e) => f.set({ ...f.v, sample: e.target.checked })} />Include sample listings</label>
          <div className="flex items-end"><Btn type="submit" disabled={a.busy}>{a.busy ? "Searching..." : "Search"}</Btn></div>
        </form>
        <div className="mt-3"><ErrorBox error={a.error} onPick={(s) => f.set({ ...f.v, district: s })} /></div>
      </Card>

      {res && (
        <>
          {res.results.some((service) => service.data_source?.startsWith("© OpenStreetMap contributors")) && (
            <Notice tone="amber">
              Some locations are community-mapped OpenStreetMap candidates and have not been independently verified.
              Data © OpenStreetMap contributors, available under the{" "}
              <a className="font-medium underline" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">Open Database License</a>.
            </Notice>
          )}
          <p className="text-sm text-slate-600">{res.total} service(s) listed in {res.location.district}{category ? ` for ${CATEGORY_LABEL[category]}` : ""}. {res.distance_note}</p>
          {res.results.length === 0
            ? <Empty title="No services listed here yet">The directory only contains services that an administrator has added. That does not mean no service exists. Ask your local school, health centre or support worker.</Empty>
            : (
              <>
                <MapContainer key={res.location.district + category} center={[res.location.latitude, res.location.longitude]} zoom={11} scrollWheelZoom={false} className="h-80 w-full rounded-2xl">
                  <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  <CircleMarker center={[res.location.latitude, res.location.longitude]} radius={5} pathOptions={{ color: "#334155", fillOpacity: 0.3 }}><Popup>District centre (approximate)</Popup></CircleMarker>
                  {res.results.filter((s) => s.latitude !== null && s.longitude !== null).map((s) => (
                    <CircleMarker key={s.id} center={[s.latitude as number, s.longitude as number]} radius={9} pathOptions={{ color: COLOR[s.verification_status], fillOpacity: 0.7 }}>
                      <Popup><b>{s.name}</b><br />{s.coordinates_approximate ? "Approximate location" : "Location"}</Popup>
                    </CircleMarker>
                  ))}
                </MapContainer>
                <p className="text-xs text-slate-500">Map markers use the coordinates in the directory. Where marked approximate, the true location may differ. Services without coordinates are listed but not shown on the map.</p>
                <div className="grid gap-4 md:grid-cols-2">{res.results.map((s) => <ServiceCard key={s.id} s={s} need={need.data} canAct={user?.role === "CITIZEN"} />)}</div>
              </>
            )}
        </>
      )}
    </div>
  );
}

function ServiceCard({ s, need, canAct }: { s: Service; need: Need | null; canAct: boolean }) {
  const a = useAction();
  const [done, setDone] = useState("");
  const [open, setOpen] = useState(false);
  const f = useForm({ method: "PHONE", result: "REACHED", note: "" });
  const osmFeatureUrl = s.data_source?.match(/https:\/\/www\.openstreetmap\.org\/(?:node|way|relation)\/\d+/)?.[0];

  async function refer() {
    if (!need) return;
    if (await a.run(() => api(`/needs/${need.id}/referrals`, { body: { service_listing_id: s.id } }))) setDone("Referral recorded. The provider has not responded yet.");
  }

  async function contact(e: FormEvent) {
    e.preventDefault();
    if (!need) return;
    if (await a.run(() => api(`/needs/${need.id}/contact-attempts`, { body: { service_listing_id: s.id, method: f.v.method, result: f.v.result, note: opt(f.v.note) } }))) { setDone("Contact attempt recorded."); setOpen(false); }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{s.name}</h3>
        {s.is_verified ? <Badge tone="green">Verified listing</Badge> : s.is_sample ? <Badge tone="amber">Sample, not a real service</Badge> : osmFeatureUrl ? <Badge tone="amber">Unverified OSM candidate</Badge> : <Badge>Not verified</Badge>}
      </div>
      <p className="text-sm text-slate-600">{CATEGORY_LABEL[s.category]} - {s.district}</p>
      {s.description && <p className="mt-1 text-sm">{s.description}</p>}
      <dl className="mt-2 space-y-0.5 text-sm text-slate-600">
        {s.address && <div>Address: {s.address}</div>}
        {s.contact_phone && <div>Phone: {s.contact_phone}</div>}
        {s.operating_hours && <div>Hours: {s.operating_hours}</div>}
        {s.distance_km_approx !== null && <div>About {s.distance_km_approx} km from the district centre</div>}
        <div className="text-xs text-slate-500">
          {osmFeatureUrl ? <>Source: <a className="underline" href={osmFeatureUrl} target="_blank" rel="noreferrer">OpenStreetMap element</a>. </> : s.data_source ? `Source: ${s.data_source}. ` : ""}
          {s.last_verified_at ? `Last verified ${new Date(s.last_verified_at).toLocaleDateString("en-IN")}.` : "Never verified."}
        </div>
      </dl>
      {s.latitude !== null && s.longitude !== null && <a className="mt-2 inline-block text-sm text-brand-700 underline" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${s.latitude}&mlon=${s.longitude}#map=16/${s.latitude}/${s.longitude}`}>View on OpenStreetMap</a>}
      {canAct && need && !done && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Btn onClick={() => void refer()} disabled={a.busy}>Record a referral</Btn>
          <Btn variant="secondary" onClick={() => setOpen(!open)}>Record a contact attempt</Btn>
        </div>
      )}
      {canAct && !need && <p className="mt-3 text-xs text-slate-500">To record a referral, open a need and choose "Find a service".</p>}
      {open && (
        <form onSubmit={contact} className="mt-3 grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="How"><Select {...f.on("method")}>{["PHONE", "VISIT", "MESSAGE", "OTHER"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select></Field>
            <Field label="What happened"><Select {...f.on("result")}>{["REACHED", "NO_ANSWER", "INFO_REQUESTED", "OTHER"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select></Field>
          </div>
          <Field label="Note (optional)"><Textarea maxLength={500} {...f.on("note")} /></Field>
          <Btn type="submit" disabled={a.busy}>Save</Btn>
        </form>
      )}
      {done && <div className="mt-3"><Notice>{done} {need && <Link className="underline" to={`/needs/${need.id}`}>View the need</Link>}</Notice></div>}
      <div className="mt-2"><ErrorBox error={a.error} /></div>
    </Card>
  );
}