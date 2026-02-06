import { useRef, useEffect, useState, useCallback } from 'react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Trash2, Search, ArrowDown } from 'lucide-react';
import { ScrollArea } from '../components/ui/scroll-area';

const LEVEL_COLORS = {
  INFO: 'text-hft-cyan',
  WARN: 'text-yellow-400',
  ERROR: 'text-hft-red',
  TRADE: 'text-hft-green',
};

const LEVEL_FILTERS = ['ALL', 'INFO', 'WARN', 'ERROR', 'TRADE'];

export default function LogsPage({ logs, onClearLogs }) {
  const [filter, setFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef(null);
  const bottomRef = useRef(null);

  const filtered = (logs || []).filter(log => {
    if (filter !== 'ALL' && log.level !== filter) return false;
    if (search && !log.message?.toLowerCase().includes(search.toLowerCase()) &&
        !log.service?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'auto' });
    }
  }, [filtered.length, autoScroll]);

  return (
    <div className="p-4 space-y-4 animate-fade-in h-[calc(100vh-2rem)] flex flex-col">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">LOGS</h1>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] tracking-widest text-hft-muted">{filtered.length} entries</span>
          <Button data-testid="clear-logs-btn" size="sm" variant="ghost" onClick={onClearLogs}
                  className="h-7 px-2 text-hft-muted hover:text-hft-red">
            <Trash2 size={12} />
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {LEVEL_FILTERS.map(lvl => (
          <button key={lvl} data-testid={`log-filter-${lvl.toLowerCase()}`}
                  onClick={() => setFilter(lvl)}
                  className={`font-mono text-[10px] uppercase tracking-widest px-3 py-1 border transition-colors duration-100 ${
                    filter === lvl
                      ? 'border-hft-green text-hft-green bg-hft-green/10'
                      : 'border-hft-border text-hft-muted hover:text-white hover:border-white/20'
                  }`}>
            {lvl}
          </button>
        ))}
        <div className="flex-1 relative ml-2">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-hft-muted" />
          <Input data-testid="log-search-input" value={search} onChange={e => setSearch(e.target.value)}
                 placeholder="Filter logs..."
                 className="bg-black border-hft-border font-mono text-xs h-7 pl-7 focus:ring-1 focus:ring-hft-green" />
        </div>
        <button onClick={() => setAutoScroll(!autoScroll)}
                className={`font-mono text-[10px] px-2 py-1 border transition-colors duration-100 ${
                  autoScroll ? 'border-hft-green text-hft-green' : 'border-hft-border text-hft-muted'
                }`}>
          <ArrowDown size={12} />
        </button>
      </div>

      <Card className="border-hft-border bg-black flex-1 overflow-hidden">
        <CardContent className="p-0 h-full">
          <div ref={scrollRef} className="h-full overflow-y-auto p-2 space-y-0" data-testid="logs-container">
            {filtered.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <span className="font-mono text-sm text-hft-muted">Waiting for logs...</span>
              </div>
            ) : (
              filtered.map((log, i) => {
                const ts = log.timestamp ? new Date(log.timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
                return (
                  <div key={i} className="flex items-start gap-2 py-0.5 hover:bg-white/[0.02] px-1 font-mono text-xs leading-relaxed">
                    <span className="text-hft-muted shrink-0 w-16">{ts}</span>
                    <span className={`shrink-0 w-12 font-bold ${LEVEL_COLORS[log.level] || 'text-white'}`}>{log.level}</span>
                    <span className="text-hft-cyan shrink-0 w-28 truncate">{log.service}</span>
                    <span className="text-white/90 break-all">{log.message}</span>
                  </div>
                );
              })
            )}
            <div ref={bottomRef} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
