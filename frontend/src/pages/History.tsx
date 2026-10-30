import { useState } from "react";
import { num, useApi } from "../lib/api";
import { Badge, Card, Empty, ErrorBox, Loading, Page, Pager, Table } from "../lib/ui";

export default function History() {
  const [page, setPage] = useState(1); const [type, setType] = useState(""); const [open, setOpen] = useState<number | null>(null);
  const { data, loading, error, reload } = useApi<any>("/api/runs", { page, page_size: 15, run_type: type || undefined });
  const detail = useApi<any>(open ? `/api/runs/${open}` : "/api/health");
  return (
    <Page title="Analytics run history" sub="Every import and analysis is stored with its parameters, status and result summary.">
      <Card right={<select aria-label="Run type" className="border rounded px-2 py-1 text-sm" value={type} onChange={e => { setType(e.target.value); setPage(1); }}>
        <option value="">All types</option>{["import", "rfm", "clustering", "basket", "forecast"].map(t => <option key={t}>{t}</option>)}</select>}>
        {loading ? <Loading /> : error ? <ErrorBox msg={error} retry={reload} /> : data.total === 0 ? <Empty>No runs yet.</Empty> : <>
          <Table rows={data.items} cols={[{ key: "id", label: "#" }, { key: "run_type", label: "Type" }, { key: "status", label: "Status", render: (r: any) => <Badge s={r.status} /> },
            { key: "created_at", label: "Created", render: (r: any) => String(r.created_at).replace("T", " ").slice(0, 19) }, { key: "duration_s", label: "Duration (s)", right: true, render: (r: any) => num(r.duration_s, 1) },
            { key: "params", label: "Parameters", render: (r: any) => <code className="text-xs">{JSON.stringify(r.params)}</code> },
            { key: "view", label: "", render: (r: any) => <button className="underline text-teal-dark" onClick={() => setOpen(r.id)}>Details</button> }]} />
          <Pager page={page} size={15} total={data.total} set={setPage} /></>}
      </Card>
      {open && <Card title={`Run #${open}`} right={<button className="text-sm underline" onClick={() => setOpen(null)}>Close</button>}>
        {detail.loading ? <Loading /> : detail.error ? <ErrorBox msg={detail.error} /> : <pre className="text-xs overflow-auto max-h-96 bg-slate-50 p-3 rounded">{JSON.stringify({ error: detail.data.error, result: detail.data.result }, null, 2)}</pre>}</Card>}
    </Page>
  );
}
