import { NavLink, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Customers from "./pages/Customers";
import Segmentation from "./pages/Segmentation";
import Products from "./pages/Products";
import Forecast from "./pages/Forecast";
import ImportPage from "./pages/ImportPage";
import History from "./pages/History";
import Recommendations from "./pages/Recommendations";

const nav = [["/", "Dashboard"], ["/customers", "Customers & RFM"], ["/segmentation", "Segmentation"], ["/products", "Products & Baskets"],
  ["/recommendations", "Recommendations"], ["/forecast", "Forecasting"], ["/import", "Data Import & Quality"], ["/history", "Run History"]];

export default function App() {
  return (
    <div className="min-h-screen md:flex">
      <aside className="bg-ink text-slate-200 md:w-60 md:min-h-screen shrink-0">
        <div className="px-5 py-4 font-semibold text-white">Retail Behavior<div className="text-xs font-normal text-slate-400">Customer purchase analytics</div></div>
        <nav className="flex md:flex-col overflow-x-auto md:overflow-visible px-2 pb-2 gap-1">
          {nav.map(([to, label]) => <NavLink key={to} to={to} end={to === "/"}
            className={({ isActive }) => `px-3 py-2 rounded text-sm whitespace-nowrap ${isActive ? "bg-teal text-white" : "hover:bg-white/10"}`}>{label}</NavLink>)}
        </nav>
      </aside>
      <main className="flex-1 p-4 md:p-8 min-w-0">
        <Routes>
          <Route path="/" element={<Dashboard />} /><Route path="/customers" element={<Customers />} />
          <Route path="/segmentation" element={<Segmentation />} /><Route path="/products" element={<Products />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/forecast" element={<Forecast />} /><Route path="/import" element={<ImportPage />} /><Route path="/history" element={<History />} />
        </Routes>
      </main>
    </div>
  );
}
