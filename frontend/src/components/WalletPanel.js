import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Wallet, RefreshCw, ExternalLink, Unplug } from 'lucide-react';
import botApi from '../lib/api';
import { toast } from 'sonner';

export default function WalletPanel({ walletAddress }) {
  const [balance, setBalance] = useState(null);
  const [phantomAddress, setPhantomAddress] = useState(null);
  const [phantomBalance, setPhantomBalance] = useState(null);
  const [loading, setLoading] = useState(false);
  const [phantomAvailable, setPhantomAvailable] = useState(false);

  useEffect(() => {
    const phantom = window?.phantom?.solana || window?.solana;
    setPhantomAvailable(!!phantom?.isPhantom);
    if (phantom?.isConnected && phantom?.publicKey) {
      setPhantomAddress(phantom.publicKey.toString());
    }
  }, []);

  const fetchBalance = useCallback(async (addr) => {
    if (!addr) return;
    setLoading(true);
    try {
      const r = await botApi.getWalletBalance(addr);
      if (r.data.error) {
        toast.error(r.data.error);
      } else {
        return r.data;
      }
    } catch (e) {
      toast.error('Failed to fetch balance');
    } finally {
      setLoading(false);
    }
    return null;
  }, []);

  useEffect(() => {
    if (walletAddress) {
      fetchBalance(walletAddress).then(d => d && setBalance(d));
    }
  }, [walletAddress, fetchBalance]);

  useEffect(() => {
    if (!walletAddress) return;
    const iv = setInterval(() => {
      fetchBalance(walletAddress).then(d => d && setBalance(d));
      if (phantomAddress && phantomAddress !== walletAddress) {
        fetchBalance(phantomAddress).then(d => d && setPhantomBalance(d));
      }
    }, 15000);
    return () => clearInterval(iv);
  }, [walletAddress, phantomAddress, fetchBalance]);

  const handleRefresh = async () => {
    if (walletAddress) {
      const d = await fetchBalance(walletAddress);
      if (d) setBalance(d);
    }
    if (phantomAddress) {
      const d = await fetchBalance(phantomAddress);
      if (d) setPhantomBalance(d);
    }
    toast.success('Balances refreshed');
  };

  const connectPhantom = async () => {
    const phantom = window?.phantom?.solana || window?.solana;
    if (!phantom?.isPhantom) {
      toast.error('Phantom wallet not detected. Install it from phantom.app');
      return;
    }
    try {
      const resp = await phantom.connect();
      const addr = resp.publicKey.toString();
      setPhantomAddress(addr);
      const d = await fetchBalance(addr);
      if (d) setPhantomBalance(d);
      toast.success(`Phantom connected: ${addr.slice(0, 4)}...${addr.slice(-4)}`);
    } catch (e) {
      toast.error('Phantom connection cancelled');
    }
  };

  const disconnectPhantom = async () => {
    try {
      const phantom = window?.phantom?.solana || window?.solana;
      if (phantom) await phantom.disconnect();
    } catch (e) { /* ignore */ }
    setPhantomAddress(null);
    setPhantomBalance(null);
    toast.success('Phantom disconnected');
  };

  const shortAddr = (a) => a ? `${a.slice(0, 4)}...${a.slice(-4)}` : '';

  return (
    <div className="space-y-3">
      <Card className="border-hft-border bg-hft-card">
        <CardHeader className="py-2 px-4 border-b border-hft-border">
          <div className="flex items-center justify-between">
            <CardTitle className="text-xs font-mono uppercase tracking-wider flex items-center gap-2">
              <Wallet size={12} /> Backend Wallet (HFT)
            </CardTitle>
            <Button data-testid="refresh-balance-btn" size="sm" variant="ghost" onClick={handleRefresh}
                    disabled={loading}
                    className="h-6 px-2 text-hft-muted hover:text-white">
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-4">
          {walletAddress ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-hft-muted">Address:</span>
                <span className="font-mono text-xs text-white">{shortAddr(walletAddress)}</span>
                <a href={`https://solscan.io/account/${walletAddress}`} target="_blank" rel="noreferrer"
                   className="text-hft-cyan hover:text-white transition-colors">
                  <ExternalLink size={10} />
                </a>
                <button onClick={() => { navigator.clipboard.writeText(walletAddress); toast.success('Address copied'); }}
                        className="font-mono text-[10px] text-hft-muted hover:text-white px-1">
                  COPY
                </button>
              </div>

              {balance ? (
                <>
                  <div className="flex items-baseline gap-2">
                    <span className="font-mono text-2xl font-bold text-hft-green">{balance.sol_balance.toFixed(4)}</span>
                    <span className="font-mono text-sm text-hft-muted">SOL</span>
                  </div>
                  {balance.tokens && balance.tokens.length > 0 && (
                    <div className="border-t border-hft-border pt-2">
                      <span className="font-mono text-[10px] tracking-widest text-hft-muted uppercase block mb-1">
                        Tokens ({balance.token_count})
                      </span>
                      <ScrollArea className="max-h-[150px]">
                        <div className="space-y-1">
                          {balance.tokens.map((t, i) => (
                            <div key={i} className="flex items-center justify-between py-0.5">
                              <span className="font-mono text-[11px] text-hft-muted truncate max-w-[200px]">
                                {t.mint.slice(0, 6)}...{t.mint.slice(-4)}
                              </span>
                              <span className="font-mono text-xs text-white">{t.ui_amount}</span>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                    </div>
                  )}
                </>
              ) : (
                <div className="font-mono text-xs text-hft-muted">
                  {loading ? 'Loading balance...' : 'Click refresh to load balance'}
                </div>
              )}
            </div>
          ) : (
            <span className="font-mono text-xs text-hft-muted">No wallet configured. Go to Setup to encrypt your key.</span>
          )}
        </CardContent>
      </Card>

      <Card className="border-hft-border bg-hft-card">
        <CardHeader className="py-2 px-4 border-b border-hft-border">
          <CardTitle className="text-xs font-mono uppercase tracking-wider flex items-center gap-2">
            <Wallet size={12} /> Phantom Wallet (Display)
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          {!phantomAddress ? (
            <div className="space-y-2">
              <Button data-testid="connect-phantom-btn" onClick={connectPhantom}
                      disabled={!phantomAvailable}
                      className="bg-[#AB9FF2] text-black font-mono font-bold text-xs uppercase tracking-wider hover:bg-[#9B8FE2] w-full">
                {phantomAvailable ? 'Connect Phantom' : 'Phantom Not Detected'}
              </Button>
              {!phantomAvailable && (
                <p className="font-mono text-[10px] text-hft-muted text-center">
                  Install Phantom from <a href="https://phantom.app" target="_blank" rel="noreferrer" className="text-hft-cyan underline">phantom.app</a>
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 bg-[#AB9FF2]" />
                  <span className="font-mono text-xs text-white">{shortAddr(phantomAddress)}</span>
                  <a href={`https://solscan.io/account/${phantomAddress}`} target="_blank" rel="noreferrer"
                     className="text-hft-cyan hover:text-white transition-colors"><ExternalLink size={10} /></a>
                </div>
                <Button data-testid="disconnect-phantom-btn" size="sm" variant="ghost" onClick={disconnectPhantom}
                        className="h-6 px-2 text-hft-muted hover:text-hft-red">
                  <Unplug size={12} />
                </Button>
              </div>
              {phantomBalance ? (
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-lg font-bold text-[#AB9FF2]">{phantomBalance.sol_balance.toFixed(4)}</span>
                  <span className="font-mono text-sm text-hft-muted">SOL</span>
                  {phantomBalance.token_count > 0 && (
                    <span className="font-mono text-[10px] text-hft-muted">+ {phantomBalance.token_count} tokens</span>
                  )}
                </div>
              ) : (
                <span className="font-mono text-xs text-hft-muted">Loading...</span>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
