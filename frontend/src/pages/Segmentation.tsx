import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { money, useApi } from "../lib/api";
import { Card, Empty, ErrorBox, Input, Loading, PALETTE, Page, RunPanel, Table } from "../lib/ui";

export default function Segmentation() {
  const [k, setK] = useState(""); const { data, loading, error, reload } = useApi<any>("/api/clusters/latest");
  const res = data?.run?.result;
  const byK = res ? Object.entries(res.silhouette_by_k).map(([k, v]) => ({ k, silhouette: v })) : [];
  const ks = res ? Array.from(new Set(res.points.map((p: any) => p.cluster))) as number[] : [];
  return (
    <Page title="Customer segmentation" sub="K-Means on log-transformed, standardised RFM values. Leave k empty to choose the k (2–8) with the best silhouette score.">
      <Card><RunPanel runType="clustering" label="Run K-Means" params={k ? { k: Number(k) } : {}} onDone={reload}>
        <label className="text-sm">Fixed k (optional)<br /><Input type="number" min={2} max={12} value={k} onChange={e => setK(e.target.value)} className="w-24" /></label></RunPanel></Card>
      {loading ? <Loading /> : error ? <ErrorBox msg={error} retry={reload} /> : !res ? <Empty>No clustering run yet. Import data and run K-Means.</Empty> : <>
        <div className="grid lg:grid-cols-2 gap-4">
          <Card title={`Silhouette by k (chosen k = ${res.k}, score ${res.silhouette})`}><div className="h-64"><ResponsiveContainer><BarChart data={byK}>
            <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" /><XAxis dataKey="k" /><YAxis fontSize={12} domain={[0, "auto"]} /><Tooltip /><Bar dataKey="silhouette" fill="#0E8F7E" /></BarChart></ResponsiveContainer></div></Card>
          <Card title={`Clusters in PCA space (explained variance ${res.pca_explained_variance.map((v: number) => (v * 100).toFixed(0) + "%").join(" + ")})`}>
            <div className="h-64"><ResponsiveContainer><ScatterChart><CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" /><XAxis type="number" dataKey="x" name="PC1" fontSize={12} /><YAxis type="number" dataKey="y" name="PC2" fontSize={12} />
              <Tooltip /><Legend />{ks.sort().map(c => <Scatter key={c} name={`Cluster ${c}`} data={res.points.filter((p: any) => p.cluster === c)} fill={PALETTE[c % PALETTE.length]} />)}</ScatterChart></ResponsiveContainer></div></Card>
        </div>
        <Card title="Cluster profiles (means)"><Table rows={res.profiles} cols={[{ key: "cluster", label: "Cluster" }, { key: "size", label: "Customers", right: true },
          { key: "recency", label: "Recency (d)", right: true }, { key: "frequency", label: "Orders", right: true }, { key: "monetary", label: "Monetary", right: true, render: (r: any) => money(r.monetary, data?.currency) }]} /></Card></>}
    </Page>
  );
}
