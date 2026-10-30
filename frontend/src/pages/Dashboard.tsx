import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, num, pct, useApi } from "../lib/api";
import { Card, Empty, ErrorBox, Kpi, Loading, Page } from "../lib/ui";

export default function Dashboard() {
  const [gran, setGran] = useState("month");
  const s = useApi<any>("/api/dashboard/summary");
  const source = useApi<any>("/api/data-source");
  const t = useApi<any[]>("/api/dashboard/trends", { granularity: gran });
  const p = useApi<any[]>("/api/dashboard/top-products", { limit: 10 });
  const c = useApi<any[]>("/api/dashboard/countries", { limit: 10 });
  if (source.loading || s.loading) return <Loading />;
  if (source.data && !source.data.analytics_ready) return <Page title="Dashboard"><Empty>
    Analytics views are not set up for this database yet. After importing all Olist CSVs, run <code>Databas_Olist/03_enable_project_analytics.sql</code> in pgAdmin.
  </Empty></Page>;
  if (source.error) return <ErrorBox msg={source.error} retry={source.reload} />;
  if (s.error) return <ErrorBox msg={s.error} retry={s.reload} />;
  if (!s.data?.has_data) return <Page title="Dashboard"><Empty>No data found for {source.data?.label ?? "the selected source"}.</Empty></Page>;
  const d = s.data;
  const currency = d.currency ?? source.data?.currency ?? "GBP";
  const stateLabel = source.data?.source === "olist" ? "state" : "country";
  return (
    <Page title="Sales overview" sub={`Source: ${source.data?.label}. Amounts in ${currency}. ${String(d.date_min).slice(0, 10)} to ${String(d.date_max).slice(0, 10)}. Revenue excludes cancelled orders.`}>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi label={`Revenue (${currency})`} value={money(d.revenue, currency)} hint={`${money(d.cancelled_value, currency)} cancelled`} />
        <Kpi label="Orders" value={num(d.orders)} />
        <Kpi label="Avg order value" value={money(d.avg_order_value, currency)} />
        <Kpi label="Customers" value={num(d.customers)} hint="identified only" />
        <Kpi label="Repeat purchase rate" value={pct(d.repeat_purchase_rate)} hint="buyers with 2+ orders" />
      </div>
      <Card title="Revenue trend" right={<select aria-label="Granularity" className="border rounded px-2 py-1 text-sm" value={gran} onChange={e => setGran(e.target.value)}>
        <option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option></select>}>
        {t.loading ? <Loading /> : t.error ? <ErrorBox msg={t.error} retry={t.reload} /> :
          <div className="h-72"><ResponsiveContainer><LineChart data={t.data ?? []}><CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" />
            <XAxis dataKey="date" fontSize={12} /><YAxis fontSize={12} tickFormatter={v => money(v, currency)} />
            <Tooltip formatter={(v: number) => money(v, currency)} /><Line type="monotone" dataKey="revenue" stroke="#0E8F7E" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>}
      </Card>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Top products by revenue">{p.loading ? <Loading /> : p.error ? <ErrorBox msg={p.error} /> :
          <div className="h-80"><ResponsiveContainer><BarChart data={p.data ?? []} layout="vertical" margin={{ left: 20 }}><CartesianGrid stroke="#e5e7eb" horizontal={false} />
            <XAxis type="number" fontSize={12} tickFormatter={v => money(v, currency)} /><YAxis type="category" dataKey="description" width={170} fontSize={11} />
            <Tooltip formatter={(v: number) => money(v, currency)} /><Bar dataKey="revenue" fill="#7B4B94" /></BarChart></ResponsiveContainer></div>}</Card>
        <Card title={`Revenue by ${stateLabel} (top 10)`}>{c.loading ? <Loading /> : c.error ? <ErrorBox msg={c.error} /> :
          <div className="h-80"><ResponsiveContainer><BarChart data={c.data ?? []} layout="vertical" margin={{ left: 20 }}><CartesianGrid stroke="#e5e7eb" horizontal={false} />
            <XAxis type="number" fontSize={12} tickFormatter={v => money(v, currency)} /><YAxis type="category" dataKey="country" width={120} fontSize={11} />
            <Tooltip formatter={(v: number) => money(v, currency)} /><Bar dataKey="revenue" fill="#E7A33E" /></BarChart></ResponsiveContainer></div>}</Card>
      </div>
    </Page>
  );
}
