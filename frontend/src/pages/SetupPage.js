import { useState, useEffect } from 'react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Shield, Server, Zap, Lock } from 'lucide-react';
import botApi from '../lib/api';
import { toast } from 'sonner';

export default function SetupPage() {
  const [walletKey, setWalletKey] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [walletStatus, setWalletStatus] = useState({ is_setup: false, is_unlocked: false });
  const [setup, setSetup] = useState(null);
  const [tipAmount, setTipAmount] = useState('0.001');
  const [tradeAmount, setTradeAmount] = useState('0.5');
  const [slippage, setSlippage] = useState('1.0');
  const [mode, setMode] = useState('simulation');

  useEffect(() => {
    botApi.getWalletStatus().then(r => setWalletStatus(r.data)).catch(() => {});
    botApi.getSetup().then(r => {
      if (r.data.setup) {
        setSetup(r.data.setup);
        if (r.data.setup.tip_amount_sol) setTipAmount(String(r.data.setup.tip_amount_sol));
        if (r.data.setup.default_trade_amount_sol) setTradeAmount(String(r.data.setup.default_trade_amount_sol));
        if (r.data.setup.slippage_percent) setSlippage(String(r.data.setup.slippage_percent));
        if (r.data.setup.mode) setMode(r.data.setup.mode);
      }
    }).catch(() => {});
  }, []);

  const handleEncryptWallet = async () => {
    if (!walletKey || !passphrase) {
      toast.error('Private key and passphrase required');
      return;
    }
    try {
      const r = await botApi.encryptWallet(walletKey, passphrase);
      if (r.data.success) {
        toast.success('Wallet encrypted and stored');
        setWalletStatus({ is_setup: true, is_unlocked: false, address: r.data.address });
        setWalletKey('');
      } else {
        toast.error(r.data.error || 'Encryption failed');
      }
    } catch (e) { toast.error('Failed to encrypt wallet'); }
  };

  const handleUnlock = async () => {
    if (!passphrase) { toast.error('Passphrase required'); return; }
    try {
      const r = await botApi.unlockWallet(passphrase);
      if (r.data.success) {
        toast.success('Wallet unlocked');
        setWalletStatus(prev => ({ ...prev, is_unlocked: true }));
      } else {
        toast.error(r.data.error || 'Unlock failed');
      }
    } catch (e) { toast.error('Unlock failed'); }
  };

  const handleResetWallet = async () => {
    try {
      await botApi.resetWallet();
      toast.success('Wallet reset');
      setWalletStatus({ is_setup: false, is_unlocked: false, address: null });
      setWalletKey('');
      setPassphrase('');
    } catch (e) { toast.error('Reset failed'); }
  };

  const handleSaveSetup = async () => {
    try {
      const rpc_endpoints = (setup?.rpc_endpoints || []).map(ep => ({
        url: ep.url, wss: ep.wss || null, type: ep.type || ep.role || 'helius', role: ep.role || 'fast'
      }));
      await botApi.saveSetup({
        rpc_endpoints, tip_amount_sol: parseFloat(tipAmount),
        default_trade_amount_sol: parseFloat(tradeAmount),
        slippage_percent: parseFloat(slippage), mode
      });
      toast.success('Setup saved');
    } catch (e) { toast.error('Save failed'); }
  };

  const rpcs = setup?.rpc_endpoints || [];

  return (
    <div className="p-4 space-y-4 animate-fade-in max-w-5xl">
      <h1 className="text-2xl font-bold tracking-tight">SETUP</h1>

      <Card className="border-hft-border bg-hft-card">
        <CardHeader className="py-3 px-4 border-b border-hft-border">
          <CardTitle className="text-sm font-mono uppercase tracking-wider flex items-center gap-2">
            <Lock size={14} /> Wallet Security (AES-256-GCM)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-3 mb-2">
            <Badge className={`font-mono text-[10px] tracking-widest border ${walletStatus.is_setup ? 'border-hft-green text-hft-green' : 'border-hft-muted text-hft-muted'}`}>
              {walletStatus.is_setup ? 'CONFIGURED' : 'NOT SET'}
            </Badge>
            <Badge className={`font-mono text-[10px] tracking-widest border ${walletStatus.is_unlocked ? 'border-hft-green text-hft-green' : 'border-hft-red text-hft-red'}`}>
              {walletStatus.is_unlocked ? 'UNLOCKED' : 'LOCKED'}
            </Badge>
            {walletStatus.address && <span className="font-mono text-xs text-hft-muted">{walletStatus.address}</span>}
            {walletStatus.is_setup && (
              <Button data-testid="reset-wallet-btn" size="sm" variant="ghost" onClick={handleResetWallet}
                      className="ml-auto h-7 px-3 text-hft-red border border-hft-red/30 font-mono text-[10px] uppercase tracking-wider hover:bg-hft-red/10">
                Reset Wallet
              </Button>
            )}
          </div>
          {!walletStatus.is_setup && (
            <div className="space-y-2">
              <Input data-testid="wallet-key-input" type="password" placeholder="Paste private key (Base58)"
                     value={walletKey} onChange={e => setWalletKey(e.target.value)}
                     className="bg-black border-hft-border font-mono text-sm focus:ring-1 focus:ring-hft-green" />
              <Input data-testid="wallet-passphrase-input" type="password" placeholder="Encryption passphrase"
                     value={passphrase} onChange={e => setPassphrase(e.target.value)}
                     className="bg-black border-hft-border font-mono text-sm focus:ring-1 focus:ring-hft-green" />
              <Button data-testid="encrypt-wallet-btn" onClick={handleEncryptWallet}
                      className="bg-hft-green text-black font-mono font-bold text-xs uppercase tracking-wider hover:bg-hft-green-dim">
                <Shield size={14} className="mr-2" /> Encrypt & Store
              </Button>
            </div>
          )}
          {walletStatus.is_setup && !walletStatus.is_unlocked && (
            <div className="flex gap-2">
              <Input data-testid="unlock-passphrase-input" type="password" placeholder="Enter passphrase to unlock"
                     value={passphrase} onChange={e => setPassphrase(e.target.value)}
                     className="bg-black border-hft-border font-mono text-sm focus:ring-1 focus:ring-hft-green flex-1" />
              <Button data-testid="unlock-wallet-btn" onClick={handleUnlock}
                      className="bg-hft-cyan text-black font-mono font-bold text-xs uppercase tracking-wider hover:bg-hft-cyan-dim">
                Unlock
              </Button>
            </div>
          )}
          {walletStatus.is_setup && walletStatus.is_unlocked && (
            <div className="space-y-2 border-t border-hft-border pt-3 mt-2">
              <p className="font-mono text-xs text-hft-muted">Wallet is active. To change wallet, click "Reset Wallet" above then enter your new private key.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-hft-border bg-hft-card">
        <CardHeader className="py-3 px-4 border-b border-hft-border">
          <CardTitle className="text-sm font-mono uppercase tracking-wider flex items-center gap-2">
            <Server size={14} /> RPC Endpoints ({rpcs.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          {rpcs.length > 0 ? (
            <div className="space-y-1">
              {rpcs.map((rpc, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 border-b border-hft-border/50 last:border-0">
                  <Badge className="font-mono text-[10px] tracking-widest border border-hft-cyan text-hft-cyan w-20 justify-center">
                    {(rpc.type || rpc.role || 'rpc').toUpperCase()}
                  </Badge>
                  <span className="font-mono text-xs text-hft-muted truncate flex-1">{rpc.url}</span>
                  {rpc.wss && <span className="font-mono text-[10px] text-hft-green">WSS</span>}
                </div>
              ))}
            </div>
          ) : (
            <p className="font-mono text-xs text-hft-muted">Loading endpoints from environment...</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-hft-border bg-hft-card">
        <CardHeader className="py-3 px-4 border-b border-hft-border">
          <CardTitle className="text-sm font-mono uppercase tracking-wider flex items-center gap-2">
            <Zap size={14} /> Trade Defaults
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block mb-1">Tip Amount (SOL)</label>
              <Input data-testid="tip-amount-input" value={tipAmount} onChange={e => setTipAmount(e.target.value)}
                     className="bg-black border-hft-border font-mono text-sm h-8 focus:ring-1 focus:ring-hft-green" />
            </div>
            <div>
              <label className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block mb-1">Trade Amount (SOL)</label>
              <Input data-testid="trade-amount-input" value={tradeAmount} onChange={e => setTradeAmount(e.target.value)}
                     className="bg-black border-hft-border font-mono text-sm h-8 focus:ring-1 focus:ring-hft-green" />
            </div>
            <div>
              <label className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block mb-1">Slippage %</label>
              <Input data-testid="slippage-input" value={slippage} onChange={e => setSlippage(e.target.value)}
                     className="bg-black border-hft-border font-mono text-sm h-8 focus:ring-1 focus:ring-hft-green" />
            </div>
            <div className="flex items-center gap-3">
              <label className="font-mono text-[10px] tracking-widest text-hft-muted uppercase">Mode</label>
              <span className="font-mono text-[10px] text-hft-muted">SIM</span>
              <Switch data-testid="setup-mode-toggle" checked={mode === 'live'} onCheckedChange={v => setMode(v ? 'live' : 'simulation')} />
              <span className="font-mono text-[10px] text-hft-muted">LIVE</span>
            </div>
          </div>
          <Button data-testid="save-setup-btn" onClick={handleSaveSetup}
                  className="mt-4 bg-hft-green text-black font-mono font-bold text-xs uppercase tracking-wider hover:bg-hft-green-dim">
            Save Setup
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
