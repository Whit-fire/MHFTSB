import { Activity, Settings, BarChart3, Terminal, Briefcase, Wallet } from 'lucide-react';

const NAV_ITEMS = [
  { id: 'control', label: 'CONTROL', icon: Activity },
  { id: 'positions', label: 'POSITIONS', icon: Briefcase },
  { id: 'logs', label: 'LOGS', icon: Terminal },
  { id: 'metrics', label: 'METRICS', icon: BarChart3 },
  { id: 'setup', label: 'SETUP', icon: Settings },
];

export const Sidebar = ({ currentPage, onPageChange, botStatus, wsConnected, walletAddress }) => {
  const status = botStatus?.status || 'stopped';
  const mode = botStatus?.mode || 'simulation';
  const gate = botStatus?.hft_gate || {};

  return (
    <div data-testid="sidebar" className="w-[220px] min-h-screen bg-[#0A0A0A] border-r border-hft-border flex flex-col">
      <div className="p-4 border-b border-hft-border">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 ${status === 'running' ? 'bg-hft-green animate-pulse-green' : 'bg-hft-red'}`} />
          <span className="font-mono font-bold text-sm tracking-wider text-white">HFT BOT</span>
        </div>
        <div className="mt-2 font-mono text-[10px] tracking-widest text-hft-muted uppercase">
          {mode} | {status}
        </div>
      </div>

      <nav className="flex-1 py-2">
        {NAV_ITEMS.map(item => {
          const Icon = item.icon;
          const active = currentPage === item.id;
          return (
            <button
              key={item.id}
              data-testid={`nav-${item.id}`}
              onClick={() => onPageChange(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 text-xs font-mono uppercase tracking-wider transition-colors duration-100 ${
                active
                  ? 'bg-hft-green/10 text-hft-green border-l-2 border-hft-green'
                  : 'text-hft-muted hover:text-white hover:bg-white/5 border-l-2 border-transparent'
              }`}
            >
              <Icon size={14} />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="p-4 border-t border-hft-border space-y-2">
        {walletAddress && (
          <div className="flex items-center gap-2 mb-2 pb-2 border-b border-hft-border/50">
            <Wallet size={10} className="text-hft-green" />
            <span className="font-mono text-[10px] text-hft-green truncate">{walletAddress.slice(0, 4)}...{walletAddress.slice(-4)}</span>
          </div>
        )}
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] tracking-widest text-hft-muted">GATE</span>
          <span className="font-mono text-xs text-white">{gate.in_flight || 0}/{gate.max_in_flight || 3}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] tracking-widest text-hft-muted">DROPS</span>
          <span className="font-mono text-xs text-hft-red">{gate.dropped_count || 0}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] tracking-widest text-hft-muted">WS</span>
          <div className={`w-2 h-2 ${wsConnected ? 'bg-hft-green' : 'bg-hft-red'}`} />
        </div>
      </div>
    </div>
  );
};
