import { useEffect, useState } from "react";

export default function App() {
  const [status, setStatus] = useState("checking...");

  useEffect(() => {
    fetch("http://localhost:8000/api/v1/health")
      .then((r) => r.json())
      .then((d) => setStatus(`API ${d.status}, DB ${d.database}`))
      .catch(() => setStatus("API unreachable"));
  }, []);

  return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="rounded-2xl bg-white p-8 shadow">
        <h1 className="text-3xl font-bold text-brand-600">Sahaayak</h1>
        <p className="mt-2 text-slate-600">{status}</p>
      </div>
    </main>
  );
}