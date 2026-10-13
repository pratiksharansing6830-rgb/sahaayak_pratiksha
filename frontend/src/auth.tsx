import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "./api";
import type { User } from "./types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (b: { email: string; password: string; full_name: string; phone?: string }) => Promise<User>;
  logout: () => Promise<void>;
}
const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!tokenStore.get());

  useEffect(() => {
    setUnauthorizedHandler(() => { tokenStore.clear(); setUser(null); });
    if (tokenStore.get()) {
      api<User>("/auth/me").then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false));
    }
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string; user: User }>("/auth/login", {
      form: { username: email.trim(), password },
    });
    tokenStore.set(r.access_token);
    setUser(r.user);
    return r.user;
  }, []);

  const register = useCallback(async (b: { email: string; password: string; full_name: string; phone?: string }) => {
    await api("/auth/register", { body: b });
    return login(b.email, b.password);
  }, [login]);

  const logout = useCallback(async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* token may already be invalid */ }
    tokenStore.clear();
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("AuthProvider is missing");
  return c;
}