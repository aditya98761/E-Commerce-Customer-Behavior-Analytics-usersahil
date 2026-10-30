import { useEffect, useState } from "react";
import { api, errMsg, num, useApi } from "../lib/api";
import { Card, Empty, ErrorBox, Input, Loading, Page } from "../lib/ui";

type CustomerOption = { customer_id: string; order_count: number; last_order: string };
type Product = { product_id: string; category: string; order_count?: number; spend?: number; similar_customer_count?: number; score?: number | null; reason?: string };
type RecommendationResult = { customer_id: string; history: Product[]; recommendations: Product[]; method: string };

export default function Recommendations() {
  const [search, setSearch] = useState("");
  const [customerId, setCustomerId] = useState("");
  const customers = useApi<CustomerOption[]>("/api/recommendations/customers", { search: search || undefined, limit: 30 });
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!customerId) { setResult(null); setError(null); return; }
    let active = true;
    setLoading(true);
    setError(null);
    api.get<RecommendationResult>(`/api/recommendations/${encodeURIComponent(customerId)}`, { params: { limit: 12 } })
      .then(response => { if (active) setResult(response.data); })
      .catch(e => { if (active) setError(errMsg(e)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [customerId]);

  const peers = result?.method === "similar_customers";
  return (
    <Page title="Personalized product recommendations"
      sub="Choose a customer to recommend products from delivered purchases made by customers with similar product histories. If there is no useful overlap, the page falls back to popular products the customer has not bought.">
      <Card title="Choose a customer">
        <div className="flex flex-col md:flex-row gap-3 md:items-end">
          <label className="text-sm text-slate-600 flex-1">Search customer ID
            <Input className="mt-1 w-full" placeholder="Enter a customer ID or part of one" value={search}
              onChange={e => setSearch(e.target.value)} aria-label="Search customer ID" />
          </label>
          <label className="text-sm text-slate-600 flex-1">Customer
            <select className="mt-1 w-full border rounded px-3 py-2 text-sm bg-white" value={customerId}
              onChange={e => setCustomerId(e.target.value)} aria-label="Select customer">
              <option value="">Select a customer…</option>
              {(customers.data ?? []).map(c => <option key={c.customer_id} value={c.customer_id}>
                {c.customer_id} · {num(c.order_count)} delivered orders
              </option>)}
            </select>
          </label>
        </div>
        {customers.loading && <Loading label="Loading customers…" />}
        {customers.error && <div className="mt-3"><ErrorBox msg={customers.error} retry={customers.reload} /></div>}
        {!customers.loading && !customers.error && !customers.data?.length && <div className="mt-3"><Empty>No matching customers with delivered orders.</Empty></div>}
      </Card>

      {loading && <Card><Loading label="Finding products for this customer…" /></Card>}
      {error && <ErrorBox msg={error} />}
      {result && !loading && <>
        <Card title={peers ? "Recommended for this customer" : "Popular alternatives"}>
          {!result.recommendations.length ? <Empty>No recommendations found. This customer may not have enough delivered purchase history.</Empty> :
            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {result.recommendations.map((item, i) => <article key={item.product_id} className="rounded-lg border border-slate-200 p-4 bg-white">
                <div className="text-xs text-teal-dark font-semibold">RECOMMENDATION {i + 1}</div>
                <div className="font-semibold mt-2 break-all">{item.product_id}</div>
                <div className="text-sm text-slate-600 mt-1">{item.category}</div>
                <div className="text-xs text-slate-500 mt-3">{item.reason}</div>
              </article>)}
            </div>}
        </Card>
        <Card title="Previously purchased">
          {!result.history.length ? <Empty>No delivered product history is available.</Empty> :
            <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2">
              {result.history.map(item => <div key={item.product_id} className="rounded bg-slate-50 px-3 py-2 text-sm">
                <div className="font-medium break-all">{item.product_id}</div>
                <div className="text-slate-500">{item.category}</div>
                <div className="text-xs text-slate-400 mt-1">{num(item.order_count)} orders</div>
              </div>)}
            </div>}
        </Card>
      </>}
    </Page>
  );
}
