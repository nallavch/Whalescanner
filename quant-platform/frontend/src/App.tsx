import { Link, Route, Routes } from 'react-router-dom';

import { BacktestsPage } from './pages/BacktestsPage';
import { DashboardPage } from './pages/DashboardPage';
import { DataSyncPage } from './pages/DataSyncPage';

export function App() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>Quant Platform</h1>
        <nav>
          <Link to="/">Dashboard</Link>
          <Link to="/backtests">Backtests</Link>
          <Link to="/data-sync">Data Sync</Link>
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/backtests" element={<BacktestsPage />} />
          <Route path="/data-sync" element={<DataSyncPage />} />
        </Routes>
      </main>
    </div>
  );
}
