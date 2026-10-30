import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, num, useApi } from "../lib/api";
import { Card, Col, Empty, ErrorBox, Input, Loading, PALETTE, Page, Pager, RunPanel, Table } from "../lib/ui";

const SEGMENTS = ["Champions", "Loyal Customers", "Potential Loyalists", "New Customers", "Need Attention", "About to Sleep", "At Risk", "Can't Lose Them", "Hibernating"];

export default function Customers() {
  const [page, setPage] = useState(1); const [search, setSearch] = useState(""); const [segment, setSegment] = useState("");
  const [sort, setSort] = useState("total_spent"); const [desc, setDesc] = useState(true);
  const [engine, setEngine] = useState("auto");
  const rfm = useApi<any>("/api/rfm/summary");
  const list = useApi<any>("/api/customers", { page, page_size: 25, search: search || undefined, segment: segment || undefined, sort, desc });
  const cols: Col<any>[] = [
    { key: "customer_id", label: "Customer", sort: "customer_id" }, { key: "country", label: "Country" },
    { key: "order_count", label: "Orders", sort: "order_count", right: true },
    { key: "total_spent", label: "Spent", sort: "total_spent", right: true, render: r => money(r.total_spent, list.data?.currency) },
    { key: "recency", label: "Recency (d)", sort: "recency", right: true, render: r => num(r.recency) },
    { key: "rfm", label: "R-F-M", render: r => r.r_score ? `${r.r_score}-${r.f_score}-${r.m_score}` : "–" },
    { key: "segment", label: "Segment", render: r => r.segment ?? "–" },
  ];
  const reload = () => { rfm.reload(); list.reload(); };
  const segs = rfm.data?.run?.result?.segments ?? [];
  return (
    <Page title="Customers & RFM" sub={`Recency (days since last order), Frequency (distinct orders) and Monetary (${list.data?.currency ?? rfm.data?.currency ?? "GBP"}) are scored 1-5 by quintile and mapped to named segments. Customers without a delivered purchase are excluded.`}>
      <Card title="Scoring">
        <RunPanel runType="rfm" params={{ engine }} label="Run RFM analysis" onDone={reload}>
          <label className="text-sm">Processing engine
            <select className="border rounded px-2 py-1 ml-2" value={engine} onChange={e => setEngine(e.target.value)}>
              <option value="auto">Automatic (Spark for Olist)</option>
              <option value="spark">Apache Spark (Olist)</option>
              <option value="pandas">Pandas</option>
            </select>
          </label>
        </RunPanel>
        {rfm.data?.run?.result?.engine && <p className="text-sm text-slate-500 mt-2">
          Latest completed run: {rfm.data.run.result.engine === "spark" ? "Apache Spark" : "Pandas"}
          {rfm.data.run.result.spark_version ? ` ${rfm.data.run.result.spark_version}` : ""}
        </p>}
      </Card>
      {rfm.error ? <ErrorBox msg={rfm.error} retry={rfm.reload} /> : segs.length === 0 ? <Empty>No RFM run yet. Import data, then run the analysis.</Empty> :
      <Card title="Customers per segment"><div className="h-64"><ResponsiveContainer><BarChart data={segs}><CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
          <XAxis dataKey="segment" fontSize={11} interval={0} angle={-20} textAnchor="end" height={60} /><YAxis fontSize={12} /><Tooltip />
          <Bar dataKey="customers">{segs.map((_: any, i: number) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Bar></BarChart></ResponsiveContainer></div>
          <Table cols={[{ key: "segment", label: "Segment" }, { key: "customers", label: "Customers", right: true }, { key: "avg_recency", label: "Avg recency (d)", right: true },
            { key: "avg_frequency", label: "Avg orders", right: true }, { key: "revenue", label: "Revenue", right: true, render: (r: any) => money(r.revenue, rfm.data?.currency) }]} rows={segs} /></Card>}
      <Card title="Customer records" right={<div className="flex gap-2">
        <Input placeholder="Search customer ID" aria-label="Search customer ID" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        <select aria-label="Segment filter" className="border rounded px-2 text-sm" value={segment} onChange={e => { setSegment(e.target.value); setPage(1); }}>
          <option value="">All segments</option>{SEGMENTS.map(s => <option key={s}>{s}</option>)}</select></div>}>
        {list.loading ? <Loading /> : list.error ? <ErrorBox msg={list.error} retry={list.reload} /> : <>
          <Table cols={cols} rows={list.data.items} sort={sort} desc={desc} onSort={k => { k === sort ? setDesc(!desc) : (setSort(k), setDesc(true)); }} />
          <Pager page={page} size={25} total={list.data.total} set={setPage} /></>}
      </Card>
    </Page>
  );
}
