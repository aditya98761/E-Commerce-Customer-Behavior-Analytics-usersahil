import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, num, useApi } from "../lib/api";
import { Card, Col, Empty, ErrorBox, Input, Loading, Page, Pager, RunPanel, Table } from "../lib/ui";

export default function Products() {
  const [page, setPage] = useState(1); const [search, setSearch] = useState(""); const [by, setBy] = useState("revenue");
  const [sup, setSup] = useState("0.02"); const [conf, setConf] = useState("0.3");
  const top = useApi<any[]>("/api/dashboard/top-products", { limit: 15, by });
  const source = useApi<any>("/api/data-source");
  const rules = useApi<any>("/api/association-rules", { page, page_size: 20, search: search || undefined });
  const cols: Col<any>[] = [
    { key: "a", label: "If customer buys", render: r => r.antecedents.join(" + ") }, { key: "c", label: "They also buy", render: r => r.consequents.join(" + ") },
    { key: "support", label: "Support", right: true, render: r => r.support.toFixed(3) }, { key: "confidence", label: "Confidence", right: true, render: r => r.confidence.toFixed(2) },
    { key: "lift", label: "Lift", right: true, render: r => r.lift.toFixed(2) }];
  return (
    <Page title="Products & market basket" sub="Apriori finds itemsets that occur together in at least `support` of invoices; rules are kept when confidence and lift (>1 means positive association) pass the thresholds. Analysis uses the 150 most frequently sold products.">
      <Card title="Top products" right={<select aria-label="Rank by" className="border rounded px-2 py-1 text-sm" value={by} onChange={e => setBy(e.target.value)}><option value="revenue">By revenue</option><option value="quantity">By units</option></select>}>
        {top.loading ? <Loading /> : top.error ? <ErrorBox msg={top.error} retry={top.reload} /> : !top.data?.length ? <Empty>No products yet. Import data first.</Empty> :
          <div className="h-96"><ResponsiveContainer><BarChart data={top.data} layout="vertical" margin={{ left: 30 }}><CartesianGrid stroke="#e5e7eb" horizontal={false} /><XAxis type="number" fontSize={12} />
            <YAxis type="category" dataKey="description" width={200} fontSize={11} /><Tooltip formatter={(v: number) => by === "revenue" ? money(v, source.data?.currency) : num(v)} /><Bar dataKey={by} fill="#3A7CA5" /></BarChart></ResponsiveContainer></div>}</Card>
      <Card title="Association rules"><div className="mb-4"><RunPanel runType="basket" label="Run Apriori" params={{ min_support: Number(sup), min_confidence: Number(conf) }} onDone={rules.reload}>
        <label className="text-sm">Min support<br /><Input value={sup} onChange={e => setSup(e.target.value)} className="w-24" /></label>
        <label className="text-sm">Min confidence<br /><Input value={conf} onChange={e => setConf(e.target.value)} className="w-24" /></label></RunPanel></div>
        <Input placeholder="Search products in rules" aria-label="Search rules" className="mb-3 w-full md:w-80" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        {rules.loading ? <Loading /> : rules.error ? <ErrorBox msg={rules.error} retry={rules.reload} /> : rules.data.total === 0 ? <Empty>No rules to show. Run Apriori, or lower the support threshold.</Empty> :
          <><Table cols={cols} rows={rules.data.items} /><Pager page={page} size={20} total={rules.data.total} set={setPage} /></>}</Card>
    </Page>
  );
}
