import { ReactNode, useEffect, useRef, useState } from "react";
import { api, errMsg } from "./api";

export const PALETTE = ["#0E8F7E", "#E7A33E", "#7B4B94", "#C8553D", "#3A7CA5", "#8AA14B", "#B8860B", "#555F6D"];

export const Card = ({ title, children, right }: { title?: string; children: ReactNode; right?: ReactNode }) => (
  <section className="rounded-lg bg-white border border-slate-200 p-4 min-w-0">
    {(title || right) && <div className="flex items-center justify-between mb-3 gap-2"><h2 className="font-semibold">{title}</h2>{right}</div>}
    {children}
  </section>
);
export const Kpi = ({ label, value, hint }: { label: string; value: string; hint?: string }) => (
  <div className="rounded-lg bg-white border-l-4 border-teal border border-slate-200 p-4">
    <div className="text-sm text-slate-500">{label}</div><div className="text-2xl font-semibold mt-1">{value}</div>
    {hint && <div className="text-xs text-slate-400 mt-1">{hint}</div>}
  </div>
);
export const Loading = ({ label = "Loading…" }: { label?: string }) => <div role="status" className="p-6 text-slate-500 animate-pulse">{label}</div>;
export const ErrorBox = ({ msg, retry }: { msg: string; retry?: () => void }) => (
  <div role="alert" className="rounded-md border border-red-200 bg-red-50 text-red-800 p-3 text-sm flex justify-between gap-3">
    <span>{msg}</span>{retry && <button className="underline" onClick={retry}>Retry</button>}</div>
);
export const Empty = ({ children }: { children: ReactNode }) => <div className="rounded-md border border-dashed border-slate-300 p-6 text-slate-500 text-sm">{children}</div>;
export const Page = ({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) => (
  <div className="space-y-4"><header><h1 className="text-2xl font-semibold">{title}</h1>{sub && <p className="text-slate-500 text-sm mt-1 max-w-3xl">{sub}</p>}</header>{children}</div>
);
export const Badge = ({ s }: { s: string }) => {
  const c = s === "completed" ? "bg-teal/10 text-teal-dark" : s === "failed" ? "bg-red-100 text-red-700" : "bg-amber/20 text-amber-900";
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${c}`}>{s}</span>;
};

export type Col<T> = { key: string; label: string; render?: (r: T) => ReactNode; sort?: string; right?: boolean };
export function Table<T extends Record<string, any>>({ cols, rows, sort, desc, onSort }:
  { cols: Col<T>[]; rows: T[]; sort?: string; desc?: boolean; onSort?: (k: string) => void }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-sm">
      <thead><tr className="text-left text-slate-500 border-b">{cols.map(c => (
        <th key={c.key} className={`py-2 pr-4 font-medium ${c.right ? "text-right" : ""}`}>
          {c.sort && onSort ? <button onClick={() => onSort(c.sort!)} className="hover:text-ink">{c.label}{sort === c.sort ? (desc ? " ▼" : " ▲") : ""}</button> : c.label}</th>))}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className="border-b last:border-0 hover:bg-slate-50">{cols.map(c => (
        <td key={c.key} className={`py-2 pr-4 ${c.right ? "text-right" : ""}`}>{c.render ? c.render(r) : String(r[c.key] ?? "–")}</td>))}</tr>)}</tbody>
    </table></div>
  );
}
export const Pager = ({ page, size, total, set }: { page: number; size: number; total: number; set: (p: number) => void }) => {
  const last = Math.max(1, Math.ceil(total / size));
  return <div className="flex items-center justify-between pt-3 text-sm text-slate-500">
    <span>{total.toLocaleString()} rows</span>
    <div className="flex gap-2 items-center">
      <button disabled={page <= 1} onClick={() => set(page - 1)} className="px-2 py-1 border rounded disabled:opacity-40">Prev</button>
      <span>Page {page} of {last}</span>
      <button disabled={page >= last} onClick={() => set(page + 1)} className="px-2 py-1 border rounded disabled:opacity-40">Next</button>
    </div></div>;
};
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`border rounded px-3 py-1.5 text-sm bg-white ${p.className ?? ""}`} />;

/** Starts a background analytics run, polls until finished, then calls onDone. */
export function RunPanel({ runType, params = {}, label, onDone, children }:
  { runType: string; params?: Record<string, any>; label: string; onDone: () => void; children?: ReactNode }) {
  const [state, setState] = useState<{ status: string; error?: string } | null>(null);
  const timer = useRef<number>();
  useEffect(() => () => window.clearInterval(timer.current), []);
  const start = async () => {
    try {
      setState({ status: "starting" });
      const { data } = await api.post("/api/runs", { run_type: runType, params });
      timer.current = window.setInterval(async () => {
        const r = (await api.get(`/api/runs/${data.id}`)).data;
        if (r.status === "completed" || r.status === "failed") {
          window.clearInterval(timer.current);
          setState({ status: r.status, error: r.error?.split("\n")[0] });
          if (r.status === "completed") onDone();
        } else setState({ status: r.status });
      }, 1500);
    } catch (e) { setState({ status: "failed", error: errMsg(e) }); }
  };
  const busy = state?.status === "starting" || state?.status === "pending" || state?.status === "running";
  return <div className="flex flex-wrap items-end gap-3">
    {children}
    <button onClick={start} disabled={busy} className="bg-teal hover:bg-teal-dark text-white px-4 py-2 rounded text-sm font-medium disabled:opacity-60">
      {busy ? "Running…" : label}</button>
    {state && <span className="text-sm" role="status">{busy ? `Status: ${state.status}` : state.status === "failed" ? <span className="text-red-700">Failed: {state.error}</span> : <span className="text-teal-dark">Completed</span>}</span>}
  </div>;
}
