import { useState, useEffect } from 'react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Switch } from '../components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import { Play, Square, AlertTriangle, Zap, TrendingUp, Shield, Target, Clock } from 'lucide-react';
import botApi from '../lib/api';
import { toast } from 'sonner';
import WalletPanel from '../components/WalletPanel';

export default function ControlPage({ status, metrics, walletAddress }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const botRunning = status?.status === 'running';
  const mode = status?.mode || 'simulation';
  const gate = status?.hft_gate || {};
  const pos = status?.positions || {};
  const exec = status?.execution || {};
  const strat = status?.strategy || {};

  useEffect(() => {
    botApi.getConfig().then(r => setConfig(r.data.config)).catch(() => {});
  }, []);

  const handleStart = async () => {
    setLoading(true);
    try {
      await botApi.startBot();
      toast.success('Bot started');
    } catch (e) { toast.error('Failed to start bot'); }
    setLoading(false);
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await botApi.stopBot();
      toast.success('Bot stopped');
    } catch (e) { toast.error('Failed to stop bot'); }
    setLoading(false);
  };

  const handlePanic = async () => {
    try {
      await botApi.panic();
      toast.success('PANIC executed - all positions closed');
    } catch (e) { toast.error('Panic failed'); }
  };

  const handleToggleMode = async () => {
    try {
      const r = await botApi.toggleMode();
      toast.success(`Mode: ${r.data.mode}`);
      // Force re-fetch status
      const s = await botApi.getBotStatus();
      if (window.__refreshBotStatus) window.__refreshBotStatus(s.data);
    } catch (e) { toast.error('Toggle failed'); }
  };

  const handleConfigSave = async () => {
    if (!config) return;
    try {
      await botApi.updateConfig(config);
      toast.success('Config updated');
    } catch (e) { toast.error('Config save failed'); }
  };

  const updateNestedConfig = (path, value) => {
    setConfig(prev => {
      const next = JSON.parse(JSON.stringify(prev));
      const keys = path.split('.');
      let obj = next;
      for (let i = 0; i < keys.length - 1; i++) obj = obj[keys[i]];
      const existing = obj[keys[keys.length - 1]];
      if (typeof existing === 'boolean') obj[keys[keys.length - 1]] = value === true || value === 'true';
      else if (typeof existing === 'number') obj[keys[keys.length - 1]] = Number(value);
      else obj[keys[keys.length - 1]] = value;
      return next;
    });
  };

  const uptime = status?.uptime_seconds || 0;
  const h = Math.floor(uptime / 3600);
  const m = Math.floor((uptime % 3600) / 60);
  const s = Math.floor(uptime % 60);

  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">CONTROL CENTER</h1>
        <div className="flex items-center gap-3">
          <Badge data-testid="mode-badge" className={`font-mono text-[10px] tracking-widest border ${mode === 'simulation' ? 'border-hft-cyan text-hft-cyan' : 'border-hft-red text-hft-red'}`}>
            {mode.toUpperCase()}
          </Badge>
          <Badge className={`font-mono text-[10px] tracking-widest border ${botRunning ? 'border-hft-green text-hft-green' : 'border-hft-muted text-hft-muted'}`}>
            {status?.status?.toUpperCase() || 'STOPPED'}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <StatCard label="UPTIME" value={`${h}h ${m}m ${s}s`} icon={Clock} />
        <StatCard label="IN-FLIGHT" value={`${gate.in_flight || 0}/${gate.max_in_flight || 3}`} icon={Zap}
                  accent={gate.in_flight >= 3 ? 'text-hft-red' : 'text-hft-green'} />
        <StatCard label="POSITIONS" value={`${pos.open_positions || 0}/${pos.max_positions || 30}`} icon={TrendingUp} />
        <StatCard label="WIN RATE" value={`${pos.win_rate || 0}%`} icon={Target}
                  accent={(pos.win_rate || 0) >= 50 ? 'text-hft-green' : 'text-hft-red'} />
      </div>

      <div className="grid grid-cols-4 gap-2">
        <StatCard label="TOTAL PNL" value={`${(pos.total_pnl_sol || 0).toFixed(4)} SOL`}
                  accent={(pos.total_pnl_sol || 0) >= 0 ? 'text-hft-green' : 'text-hft-red'} icon={TrendingUp} />
        <StatCard label="EXEC SUCCESS" value={`${exec.success_rate || 0}%`} icon={Shield} />
        <StatCard label="AVG LATENCY" value={`${exec.avg_latency_ms || 0}ms`} icon={Zap} />
        <StatCard label="EVALUATED" value={strat.evaluated || 0} icon={Target} />
      </div>

      <div className="flex items-center gap-3">
        {!botRunning ? (
          <Button data-testid="start-bot-btn" onClick={handleStart} disabled={loading}
                  className="bg-hft-green text-black font-mono font-bold uppercase tracking-wider hover:bg-hft-green-dim active:scale-95 transition-transform duration-100 px-8 py-5">
            <Play size={16} className="mr-2" /> START BOT
          </Button>
        ) : (
          <Button data-testid="stop-bot-btn" onClick={handleStop} disabled={loading}
                  className="bg-hft-red text-white font-mono font-bold uppercase tracking-wider hover:bg-hft-red-dim active:scale-95 transition-transform duration-100 px-8 py-5">
            <Square size={16} className="mr-2" /> STOP BOT
          </Button>
        )}
        <Button data-testid="panic-btn" onClick={handlePanic} variant="outline"
                className="border-hft-red text-hft-red font-mono font-bold uppercase tracking-wider hover:bg-hft-red/10 active:scale-95 transition-transform duration-100 px-6 py-5">
          <AlertTriangle size={16} className="mr-2" /> PANIC
        </Button>
        <div className="flex items-center gap-2 ml-4">
          <span className="font-mono text-[10px] tracking-widest text-hft-muted">SIM</span>
          <Switch data-testid="mode-toggle" checked={mode === 'live'} onCheckedChange={handleToggleMode} />
          <span className="font-mono text-[10px] tracking-widest text-hft-muted">LIVE</span>
        </div>
      </div>

      {config && (
        <div className="grid grid-cols-[1fr_300px] gap-4">
          <Card className="border-hft-border bg-hft-card">
            <CardHeader className="py-3 px-4 border-b border-hft-border">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-mono uppercase tracking-wider">Strategy Configuration</CardTitle>
                <Button data-testid="save-config-btn" onClick={handleConfigSave} size="sm"
                        className="bg-hft-cyan text-black font-mono text-xs uppercase tracking-wider hover:bg-hft-cyan-dim">
                  Save Config
                </Button>
              </div>
            </CardHeader>
          <CardContent className="p-0">
            <Tabs defaultValue="filters" className="w-full">
              <TabsList className="w-full justify-start bg-transparent border-b border-hft-border px-2 h-9">
                {['filters', 'risk', 'take_profit', 'scoring', 'execution', 'hft'].map(tab => (
                  <TabsTrigger key={tab} value={tab}
                    className="font-mono text-[10px] uppercase tracking-widest data-[state=active]:text-hft-green data-[state=active]:border-b-2 data-[state=active]:border-hft-green rounded-none">
                    {tab.replace('_', ' ')}
                  </TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value="filters" className="p-4">
                <ConfigGrid>
                  <ConfigField label="Min Liquidity SOL" path="FILTERS.MIN_LIQUIDITY_SOL" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Min Liq Fast Buy" path="FILTERS.MIN_LIQUIDITY_FAST_BUY" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Max Buy Amount" path="FILTERS.MAX_INITIAL_BUY_AMOUNT" config={config} onChange={updateNestedConfig} />
                  <ConfigToggle label="Fast Buy Enabled" path="FILTERS.FAST_BUY_ENABLED" config={config} onChange={updateNestedConfig} />
                </ConfigGrid>
              </TabsContent>
              <TabsContent value="risk" className="p-4">
                <ConfigGrid>
                  <ConfigToggle label="Kill Switch" path="RISK.KILL_SWITCH.ENABLED" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="KS Max Time (s)" path="RISK.KILL_SWITCH.MAX_TIME_SECONDS" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="KS Drop %" path="RISK.KILL_SWITCH.DROP_THRESHOLD_PERCENT" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Max Rug Score" path="RISK.MAX_RUGCHECK_SCORE" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="SL Low" path="RISK.STOP_LOSS.LOW" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="SL Medium" path="RISK.STOP_LOSS.MEDIUM" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="SL High" path="RISK.STOP_LOSS.HIGH" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="SL Ultra" path="RISK.STOP_LOSS.ULTRA" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Trail Start %" path="RISK.TRAILING.START_PERCENT" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Trail Distance %" path="RISK.TRAILING.DISTANCE_PERCENT" config={config} onChange={updateNestedConfig} />
                </ConfigGrid>
              </TabsContent>
              <TabsContent value="take_profit" className="p-4">
                <ConfigGrid>
                  <ConfigField label="TP1 %" path="TAKE_PROFIT.TP1.percent" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="TP1 Gain" path="TAKE_PROFIT.TP1.gain" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="TP2 %" path="TAKE_PROFIT.TP2.percent" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="TP2 Gain" path="TAKE_PROFIT.TP2.gain" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="TP3 %" path="TAKE_PROFIT.TP3.percent" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="TP3 Gain" path="TAKE_PROFIT.TP3.gain" config={config} onChange={updateNestedConfig} />
                </ConfigGrid>
              </TabsContent>
              <TabsContent value="scoring" className="p-4">
                <ConfigGrid>
                  <ConfigField label="W: Rug Check" path="SCORING.WEIGHTS.RUG_CHECK" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="W: Liquidity" path="SCORING.WEIGHTS.LIQUIDITY" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="W: Momentum" path="SCORING.WEIGHTS.MOMENTUM" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="W: Creator" path="SCORING.WEIGHTS.CREATOR" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Fast Buy Thr" path="SCORING.THRESHOLDS.FAST_BUY" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Min Score" path="SCORING.THRESHOLDS.MIN_SCORE" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Ultra Score" path="SCORING.THRESHOLDS.ULTRA_SCORE" config={config} onChange={updateNestedConfig} />
                </ConfigGrid>
              </TabsContent>
              <TabsContent value="execution" className="p-4">
                <ConfigGrid>
                  <ConfigField label="Max Open Pos" path="EXECUTION.MAX_OPEN_POSITIONS" config={config} onChange={updateNestedConfig} />
                  <ConfigToggle label="One Per Token" path="EXECUTION.ENFORCE_ONE_PER_TOKEN" config={config} onChange={updateNestedConfig} />
                  <ConfigToggle label="Stop When Full" path="EXECUTION.STOP_LISTENING_WHEN_FULL" config={config} onChange={updateNestedConfig} />
                </ConfigGrid>
              </TabsContent>
              <TabsContent value="hft" className="p-4">
                <ConfigGrid>
                  <ConfigField label="Eval Interval (ms)" path="HFT.EVAL_INTERVAL_MS" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Price Update (ms)" path="HFT.PRICE_UPDATE_INTERVAL_MS" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Max Pos Age (ms)" path="HFT.MAX_POSITION_AGE_MS" config={config} onChange={updateNestedConfig} />
                  <ConfigField label="Candidate Max Age" path="HFT.CANDIDATE_MAX_AGE_MS" config={config} onChange={updateNestedConfig} />
                </ConfigGrid>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StatCard({ label, value, icon: Icon, accent }) {
  return (
    <Card className="border-hft-border bg-hft-card">
      <CardContent className="p-3">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[10px] tracking-widest text-hft-muted uppercase">{label}</span>
          {Icon && <Icon size={12} className="text-hft-muted" />}
        </div>
        <div className={`font-mono text-lg font-bold ${accent || 'text-white'}`}>{value}</div>
      </CardContent>
    </Card>
  );
}

function ConfigGrid({ children }) {
  return <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{children}</div>;
}

function ConfigField({ label, path, config, onChange }) {
  const keys = path.split('.');
  let val = config;
  for (const k of keys) val = val?.[k];
  return (
    <div>
      <label className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block mb-1">{label}</label>
      <Input data-testid={`config-${path}`} value={val ?? ''} onChange={e => onChange(path, e.target.value)}
             className="bg-black border-hft-border font-mono text-sm h-8 focus:ring-1 focus:ring-hft-green focus:border-hft-green" />
    </div>
  );
}

function ConfigToggle({ label, path, config, onChange }) {
  const keys = path.split('.');
  let val = config;
  for (const k of keys) val = val?.[k];
  return (
    <div className="flex items-center justify-between">
      <label className="font-mono text-[10px] tracking-widest text-hft-muted uppercase">{label}</label>
      <Switch data-testid={`config-${path}`} checked={!!val} onCheckedChange={v => onChange(path, v)} />
    </div>
  );
}
