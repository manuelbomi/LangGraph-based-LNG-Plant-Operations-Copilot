import { NavLink, Route, Routes } from "react-router-dom";

import { PlantDashboardPage } from "./pages/PlantDashboardPage";
import { SensorDetailPage } from "./pages/SensorDetailPage";
import { WorkOrderDetailPage } from "./pages/WorkOrderDetailPage";
import { WorkOrderQueuePage } from "./pages/WorkOrderQueuePage";

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium ${
          isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div>
            <h1 className="text-base font-semibold text-slate-900">LNG Plant Operations Copilot</h1>
            <p className="text-xs text-slate-400">Built with LangGraph</p>
          </div>
          <nav className="flex gap-1">
            <NavItem to="/">Plant Dashboard</NavItem>
            <NavItem to="/work-orders">Work Order Queue</NavItem>
          </nav>
        </div>
      </header>

      <div className="border-b border-amber-200 bg-amber-50">
        <div className="mx-auto max-w-6xl px-4 py-2 text-xs font-medium text-amber-800">
          Decision-support and documentation-drafting copilot only -- this app does NOT autonomously control any
          equipment and does NOT make a final safety-critical decision. All equipment, sensor data, manuals, and
          incident reports in this demo are entirely synthetic and fictitious. Every draft work order requires
          qualified engineer review and approval before any action is taken.
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<PlantDashboardPage />} />
          <Route path="/tags/:tagId" element={<SensorDetailPage />} />
          <Route path="/work-orders" element={<WorkOrderQueuePage />} />
          <Route path="/work-orders/:id" element={<WorkOrderDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}
