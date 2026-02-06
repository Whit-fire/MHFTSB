import { useState, useEffect } from 'react';
import "@/App.css";
import { Sidebar } from './components/Sidebar';
import { useWebSocket } from './lib/websocket';
import { Toaster } from './components/ui/sonner';
import botApi from './lib/api';
import SetupPage from './pages/SetupPage';
import ControlPage from './pages/ControlPage';
import PositionsPage from './pages/PositionsPage';
import LogsPage from './pages/LogsPage';
import MetricsPage from './pages/MetricsPage';

function App() {
  const [page, setPage] = useState('control');
  const [botStatus, setBotStatus] = useState(null);
  const [walletAddress, setWalletAddress] = useState(null);
  const { connected, logs, metrics, positions, clearLogs } = useWebSocket();

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await botApi.getBotStatus();
        setBotStatus(r.data);
      } catch (e) { /* ignore */ }
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    botApi.getWalletStatus().then(r => {
      if (r.data.address) setWalletAddress(r.data.address);
    }).catch(() => {});
  }, [page]);

  const liveStatus = metrics || botStatus;

  return (
    <div className="flex h-screen bg-[#050505] text-white overflow-hidden">
      <Sidebar
        currentPage={page}
        onPageChange={setPage}
        botStatus={liveStatus}
        wsConnected={connected}
        walletAddress={walletAddress}
      />
      <main className="flex-1 overflow-y-auto" data-testid="main-content">
        {page === 'setup' && <SetupPage onWalletChange={setWalletAddress} />}
        {page === 'control' && <ControlPage status={liveStatus} metrics={metrics} walletAddress={walletAddress} />}
        {page === 'positions' && <PositionsPage positions={positions} />}
        {page === 'logs' && <LogsPage logs={logs} onClearLogs={clearLogs} />}
        {page === 'metrics' && <MetricsPage metrics={liveStatus} />}
      </main>
      <Toaster position="bottom-right" theme="dark" />
    </div>
  );
}

export default App;
