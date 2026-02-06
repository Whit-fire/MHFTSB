import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API, timeout: 15000 });

export const botApi = {
  getHealth: () => api.get('/health'),
  getConfig: () => api.get('/config'),
  updateConfig: (config) => api.put('/config', { config }),
  setParam: (path, value) => api.post('/config/set', { path, value }),
  getSetup: () => api.get('/setup'),
  saveSetup: (data) => api.post('/setup', data),
  resetWallet: () => api.post('/wallet/reset'),
  encryptWallet: (privateKey, passphrase) => api.post('/wallet/encrypt', { private_key: privateKey, passphrase }),
  unlockWallet: (passphrase) => api.post('/wallet/unlock', { passphrase }),
  getWalletStatus: () => api.get('/wallet/status'),
  startBot: () => api.post('/bot/start'),
  stopBot: () => api.post('/bot/stop'),
  getBotStatus: () => api.get('/bot/status'),
  panic: () => api.post('/bot/panic'),
  toggleMode: () => api.post('/bot/toggle-mode'),
  getPositions: () => api.get('/positions'),
  getPositionHistory: () => api.get('/positions/history'),
  closePosition: (id) => api.post(`/positions/${id}/close`),
  forceSell: (id) => api.post(`/positions/${id}/force-sell`),
  setStopLoss: (id, value) => api.put(`/positions/${id}/sl`, { action: 'sl', value }),
  getMetrics: () => api.get('/metrics'),
  getKpi: () => api.get('/metrics/kpi'),
  getLatencies: () => api.get('/metrics/latencies'),
  getRpcHealth: () => api.get('/metrics/rpc'),
  getLogs: (limit = 100) => api.get(`/logs?limit=${limit}`),
  manualBuy: (mint, amount) => api.post('/trade/buy', { mint, amount_sol: amount }),
};

export default botApi;
