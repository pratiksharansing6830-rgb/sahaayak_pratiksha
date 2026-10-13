import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import { t } from "./i18n";
import type { District, Role } from "./types";
import { Btn, Loading, useLoad } from "./ui";
import { Forbidden, Landing, Login, NotFound, Register } from "./pages/Public";
import { FamilyList, FamilyNew } from "./pages/Family";
import FamilyHome from "./pages/FamilyHome";
import NeedPage from "./pages/NeedPage";
import Services from "./pages/Services";
import { ProviderDetail, ProviderList } from "./pages/Provider";
import Gov from "./pages/Gov";
import Admin from "./pages/Admin";
import Privacy from "./pages/Privacy";

const NAV: Record<Role, { to: string; label: string }[]> = {
  CITIZEN: [{ to: "/family", label: "My family" }, { to: "/services", label: "Find services" }, { to: "/privacy", label: "Privacy" }],
  NGO: [{ to: "/family", label: "Shared families" }, { to: "/provider", label: "Referrals" }, { to: "/services", label: "Directory" }, { to: "/privacy", label: "Account" }],
  SCHOOL: [{ to: "/provider", label: "Referrals" }, { to: "/privacy", label: "Account" }],
  HEALTHCARE: [{ to: "/provider", label: "Referrals" }, { to: "/privacy", label: "Account" }],
  GOVERNMENT: [{ to: "/gov", label: "Planning dashboard" }, { to: "/privacy", label: "Account" }],
  ADMIN: [{ to: "/admin", label: "Administration" }, { to: "/privacy", label: "Account" }],
};
export const HOME: Record<Role, string> = {
  CITIZEN: "/family", NGO: "/family", SCHOOL: "/provider", HEALTHCARE: "/provider", GOVERNMENT: "/gov", ADMIN: "/admin",
};

function Districts() {
  const d = useLoad(() => api<District[]>("/services/districts"), []);
  return <datalist id="districts">{(d.data ?? []).map((x) => <option key={x.name} value={x.name} />)}</datalist>;
}

function Layout() {
  const { user, logout } = useAuth();
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-brand-100 text-brand-700" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:p-2">Skip to content</a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
          <Link to={user ? HOME[user.role] : "/"} className="mr-4 text-xl font-bold text-brand-600">Sahaayak</Link>
          <nav aria-label="Main" className="flex flex-1 flex-wrap gap-1">
            {user && NAV[user.role].map((n) => <NavLink key={n.to} to={n.to} className={link}>{t(n.label)}</NavLink>)}
          </nav>
          {user ? (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-slate-600">{user.full_name}</span>
              <Btn variant="secondary" onClick={() => void logout()}>{t("Log out")}</Btn>
            </div>
          ) : (
            <div className="flex gap-2">
              <Link to="/login" className={link({ isActive: false })}>{t("Log in")}</Link>
              <Link to="/register" className="rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700">{t("Register")}</Link>
            </div>
          )}
        </div>
      </header>
      {user && <Districts />}
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6"><Outlet /></main>
      <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-500">
        Sahaayak helps families keep track of support. It does not replace official school, health or welfare processes, and it does not confirm that any service is available.
      </footer>
    </div>
  );
}

function Guard({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname + loc.search }} replace />;
  if (roles && !roles.includes(user.role)) return <Forbidden />;
  return <>{children}</>;
}
function AppHome() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return <Navigate to={user ? HOME[user.role] : "/login"} replace />;
}

export default function App() {
  const FAM: Role[] = ["CITIZEN", "NGO"];
  const PROV: Role[] = ["SCHOOL", "HEALTHCARE", "NGO"];
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/app" element={<AppHome />} />
        <Route path="/family" element={<Guard roles={FAM}><FamilyList /></Guard>} />
        <Route path="/family/new" element={<Guard roles={["CITIZEN"]}><FamilyNew /></Guard>} />
        <Route path="/family/:id" element={<Guard roles={FAM}><FamilyHome /></Guard>} />
        <Route path="/needs/:id" element={<Guard roles={FAM}><NeedPage /></Guard>} />
        <Route path="/services" element={<Guard><Services /></Guard>} />
        <Route path="/provider" element={<Guard roles={PROV}><ProviderList /></Guard>} />
        <Route path="/provider/referrals/:id" element={<Guard roles={PROV}><ProviderDetail /></Guard>} />
        <Route path="/gov" element={<Guard roles={["GOVERNMENT"]}><Gov /></Guard>} />
        <Route path="/admin" element={<Guard roles={["ADMIN"]}><Admin /></Guard>} />
        <Route path="/privacy" element={<Guard><Privacy /></Guard>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}