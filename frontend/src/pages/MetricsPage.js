import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, PieChart, Pie, Cell } from 'recharts';
import { Activity, Zap, Clock, Server } from 'lucide-react';
import botApi from '../lib/api';

const COLORS = ['#00E676', '#00B0FF', '#FF1744', '#FFD600', '#A1A1AA'];

export default function MetricsPage({ metrics }) {
  const [latencies, setLatencies] = useState([]);
  const [rpcHealth, setRpcHealth] = useState(null);
  const [kpi, setKpi] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [latR, rpcR, kpiR] = await Promise.all([
          botApi.getLatencies(), botApi.getRpcHealth(), botApi.getKpi()
        ]);
        setLatencies(latR.data.latencies || []);
        setRpcHealth(rpcR.data);
        setKpi(kpiR.data);
      } catch (e) { /* ignore */ }
    };
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, []);

  const snapshot = metrics?.metrics || {};
  const histograms = snapshot.histograms || {};
  const counters = snapshot.counters || {};
  const gauges = snapshot.gauges || {};

  const histData = Object.entries(histograms).map(([name, val]) => ({
    name: name.replace(/_/g, ' ').replace(' ms', ''),
    avg: val.avg, p50: val.p50, p99: val.p99, max: val.max, count: val.count
  }));

  const latencyChart = latencies.slice(-100).map((l, i) => ({
    idx: i, name: l.name?.replace(/_/g, ' ').replace(' ms', ''), value: l.value
  }));

  const scoreBuckets = metrics?.strategy?.score_buckets || {};
  const pieData = Object.entries(scoreBuckets).filter(([, v]) => v > 0).map(([name, value]) => ({ name, value }));

  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <h1 className="text-2xl font-bold tracking-tight">METRICS</h1>

      <div className="grid grid-cols-5 gap-2">
        <MCard label="WSS EVENTS" value={counters.wss_events_total || 0} icon={Activity} />
        <MCard label="APPROVED" value={counters.strategy_approved || 0} icon={Zap} color="text-hft-green" />
        <MCard label="REJECTED" value={counters.strategy_rejected || 0} icon={Zap} color="text-hft-red" />
        <MCard label="TRADES OK" value={counters.trades_success || 0} icon={Zap} color="text-hft-green" />
        <MCard label="TRADES FAIL" value={counters.trades_failed || 0} icon={Zap} color="text-hft-red" />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card className="border-hft-border bg-hft-card">
          <CardHeader className="py-2 px-4 border-b border-hft-border">
            <CardTitle className="text-xs font-mono uppercase tracking-wider flex items-center gap-2">
              <Clock size={12} /> Latency Histogram
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            {histData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={histData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="name" tick={{ fill: '#A1A1AA', fontSize: 10, fontFamily: 'JetBrains Mono' }} />
                  <YAxis tick={{ fill: '#A1A1AA', fontSize: 10, fontFamily: 'JetBrains Mono' }} />
                  <Tooltip contentStyle={{ background: '#0A0A0A', border: '1px solid #27272a', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                  <Bar dataKey="avg" fill="#00B0FF" name="AVG" />
                  <Bar dataKey="p99" fill="#FF1744" name="P99" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[220px] flex items-center justify-center font-mono text-xs text-hft-muted">No data yet</div>
            )}
          </CardContent>
        </Card>

        <Card className="border-hft-border bg-hft-card">
          <CardHeader className="py-2 px-4 border-b border-hft-border">
            <CardTitle className="text-xs font-mono uppercase tracking-wider flex items-center gap-2">
              <Activity size={12} /> Recent Latencies
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            {latencyChart.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={latencyChart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="idx" tick={{ fill: '#A1A1AA', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#A1A1AA', fontSize: 10, fontFamily: 'JetBrains Mono' }} unit="ms" />
                  <Tooltip contentStyle={{ background: '#0A0A0A', border: '1px solid #27272a', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                  <Line type="monotone" dataKey="value" stroke="#00E676" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[220px] flex items-center justify-center font-mono text-xs text-hft-muted">No data yet</div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="border-hft-border bg-hft-card">
          <CardHeader className="py-2 px-4 border-b border-hft-border">
            <CardTitle className="text-xs font-mono uppercase tracking-wider">PumpScore Distribution</CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" outerRadius={70} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                    {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#0A0A0A', border: '1px solid #27272a', fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[180px] flex items-center justify-center font-mono text-xs text-hft-muted">No data yet</div>
            )}
          </CardContent>
        </Card>

        <Card className="border-hft-border bg-hft-card">
          <CardHeader className="py-2 px-4 border-b border-hft-border">
            <CardTitle className="text-xs font-mono uppercase tracking-wider flex items-center gap-2">
              <Server size={12} /> RPC Health
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-2">
            {rpcHealth?.endpoints?.map((ep, i) => (
              <div key={i} className="flex items-center gap-2 text-xs font-mono">
                <div className={`w-1.5 h-1.5 ${ep.available ? 'bg-hft-green' : 'bg-hft-red'}`} />
                <Badge className="text-[9px] border border-hft-border text-hft-muted w-16 justify-center">{ep.role?.toUpperCase()}</Badge>
                <span className="text-hft-muted truncate flex-1">{ep.url}</span>
                <span className="text-hft-cyan">{ep.health_score}</span>
                {ep.recent_429s > 0 && <span className="text-hft-red">{ep.recent_429s}x429</span>}
              </div>
            )) || <span className="font-mono text-xs text-hft-muted">Loading...</span>}
          </CardContent>
        </Card>

        <Card className="border-hft-border bg-hft-card">
          <CardHeader className="py-2 px-4 border-b border-hft-border">
            <CardTitle className="text-xs font-mono uppercase tracking-wider">KPI Summary</CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-2">
            <KpiRow label="Win Rate" value={`${kpi?.win_rate || 0}%`} color={(kpi?.win_rate || 0) >= 50 ? 'text-hft-green' : 'text-hft-red'} />
            <KpiRow label="Wins" value={kpi?.wins || 0} color="text-hft-green" />
            <KpiRow label="Losses" value={kpi?.losses || 0} color="text-hft-red" />
            <KpiRow label="Open" value={kpi?.open_positions || 0} />
            <KpiRow label="Closed" value={kpi?.closed_positions || 0} />
            <KpiRow label="Total PnL" value={`${(kpi?.total_pnl_sol || 0).toFixed(4)} SOL`}
                    color={(kpi?.total_pnl_sol || 0) >= 0 ? 'text-hft-green' : 'text-hft-red'} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MCard({ label, value, icon: Icon, color }) {
  return (
    <Card className="border-hft-border bg-hft-card">
      <CardContent className="p-3">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[10px] tracking-widest text-hft-muted uppercase">{label}</span>
          {Icon && <Icon size={12} className="text-hft-muted" />}
        </div>
        <div className={`font-mono text-lg font-bold ${color || 'text-white'}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function KpiRow({ label, value, color }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] tracking-widest text-hft-muted uppercase">{label}</span>
      <span className={`font-mono text-sm font-bold ${color || 'text-white'}`}>{value}</span>
    </div>
  );
}
