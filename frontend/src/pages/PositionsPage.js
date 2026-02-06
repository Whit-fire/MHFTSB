import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { X, TrendingDown, DollarSign } from 'lucide-react';
import botApi from '../lib/api';
import { toast } from 'sonner';

export default function PositionsPage({ positions }) {
  const openPositions = positions || [];
  const totalPnl = openPositions.reduce((sum, p) => sum + (p.pnl_sol || 0), 0);
  const totalAmount = openPositions.reduce((sum, p) => sum + (p.amount_sol || 0), 0);

  const handleClose = async (id, name) => {
    try {
      await botApi.closePosition(id);
      toast.success(`Closed ${name}`);
    } catch (e) { toast.error('Close failed'); }
  };

  const handleForceSell = async (id, name) => {
    try {
      await botApi.forceSell(id);
      toast.success(`Force sold ${name}`);
    } catch (e) { toast.error('Force sell failed'); }
  };

  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">POSITIONS</h1>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <span className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block">TOTAL PNL</span>
            <span className={`font-mono text-lg font-bold ${totalPnl >= 0 ? 'text-hft-green' : 'text-hft-red'}`}>
              {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(4)} SOL
            </span>
          </div>
          <div className="text-right">
            <span className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block">OPEN</span>
            <span className="font-mono text-lg font-bold text-white">{openPositions.length}</span>
          </div>
          <div className="text-right">
            <span className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block">INVESTED</span>
            <span className="font-mono text-lg font-bold text-hft-cyan">{totalAmount.toFixed(4)} SOL</span>
          </div>
        </div>
      </div>

      <Card className="border-hft-border bg-hft-card">
        <CardContent className="p-0">
          <table data-testid="positions-table" className="w-full">
            <thead>
              <tr className="border-b border-hft-border">
                {['TOKEN', 'SCORE', 'ENTRY', 'CURRENT', 'PNL (SOL)', 'PNL (%)', 'AMOUNT', 'TIME', 'TRAIL', 'ACTIONS'].map(h => (
                  <th key={h} className="h-8 px-3 text-left font-mono text-[10px] uppercase tracking-widest text-hft-muted font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {openPositions.length === 0 ? (
                <tr><td colSpan={10} className="text-center py-8 font-mono text-sm text-hft-muted">No open positions</td></tr>
              ) : (
                openPositions.map(pos => {
                  const pnlColor = (pos.pnl_percent || 0) >= 0 ? 'text-hft-green' : 'text-hft-red';
                  const entryTime = pos.entry_time ? new Date(pos.entry_time) : null;
                  const elapsed = entryTime ? Math.floor((Date.now() - entryTime.getTime()) / 1000) : 0;
                  const timeStr = elapsed > 60 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` : `${elapsed}s`;
                  return (
                    <tr key={pos.id} data-testid={`position-row-${pos.id}`}
                        className="border-b border-hft-border/50 hover:bg-white/[0.02] transition-colors duration-100">
                      <td className="px-3 py-2">
                        <span className="font-mono text-xs font-bold text-white">{pos.token_name}</span>
                      </td>
                      <td className="px-3 py-2">
                        <Badge className={`font-mono text-[10px] border ${
                          pos.pump_score >= 85 ? 'border-hft-green text-hft-green' :
                          pos.pump_score >= 70 ? 'border-hft-cyan text-hft-cyan' : 'border-hft-muted text-hft-muted'
                        }`}>{pos.pump_score}</Badge>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-hft-muted">{pos.entry_price_sol?.toFixed(6)}</td>
                      <td className="px-3 py-2 font-mono text-xs text-white">{pos.current_price_sol?.toFixed(6)}</td>
                      <td className={`px-3 py-2 font-mono text-xs font-bold ${pnlColor}`}>
                        {(pos.pnl_sol || 0) >= 0 ? '+' : ''}{(pos.pnl_sol || 0).toFixed(4)}
                      </td>
                      <td className={`px-3 py-2 font-mono text-xs font-bold ${pnlColor}`}>
                        {(pos.pnl_percent || 0) >= 0 ? '+' : ''}{(pos.pnl_percent || 0).toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-hft-muted">{pos.amount_sol?.toFixed(4)}</td>
                      <td className="px-3 py-2 font-mono text-xs text-hft-muted">{timeStr}</td>
                      <td className="px-3 py-2">
                        {pos.trailing_active && <Badge className="font-mono text-[10px] border border-hft-green text-hft-green">TRAIL</Badge>}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex gap-1">
                          <Button data-testid={`close-pos-${pos.id}`} size="sm" variant="ghost" onClick={() => handleClose(pos.id, pos.token_name)}
                                  className="h-6 px-2 text-hft-muted hover:text-hft-red hover:bg-hft-red/10">
                            <X size={12} />
                          </Button>
                          <Button data-testid={`force-sell-${pos.id}`} size="sm" variant="ghost" onClick={() => handleForceSell(pos.id, pos.token_name)}
                                  className="h-6 px-2 text-hft-muted hover:text-hft-red hover:bg-hft-red/10">
                            <TrendingDown size={12} />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
