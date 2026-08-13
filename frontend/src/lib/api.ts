// Thin fetch wrapper. Calls are proxied to the FastAPI backend (see next.config.js).
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request("/health"),
  accountInfo: () => request("/account/info"),
  switchAccount: (target: "DEMO" | "LIVE") =>
    request("/account/switch", { method: "POST", body: JSON.stringify({ target }) }),
  runPipeline: (body: unknown) =>
    request("/live/run", { method: "POST", body: JSON.stringify(body) }),
  monitored: () => request("/live/monitored"),
  testTrade: (body: unknown) =>
    request("/live/test-trade", { method: "POST", body: JSON.stringify(body) }),
  scannerSettings: () => request("/scanner/settings"),
  saveScannerSettings: (body: unknown) =>
    request("/scanner/settings", { method: "PUT", body: JSON.stringify(body) }),
  scannerBlockers: (hours = 24) => request(`/scanner/blockers?hours=${hours}`),
  scannerDecisions: (limit = 100) => request(`/scanner/decisions?limit=${limit}`),
  moneyOverview: () => request("/money/overview"),
  saveMoneySettings: (body: unknown) =>
    request("/money/settings", { method: "PUT", body: JSON.stringify(body) }),
  runBacktest: (body: unknown) =>
    request("/backtest/run", { method: "POST", body: JSON.stringify(body) }),
  backtestMatrix: (body: unknown) =>
    request("/backtest/matrix", { method: "POST", body: JSON.stringify(body) }),
  backtestStrategies: () => request("/backtest/strategies"),
  backtestDatasets: () => request("/backtest/datasets"),
  importMarketData: () => request("/backtest/import-data", { method: "POST" }),
  strategyMatrix: () => request("/history/strategy-matrix"),
  strategyReview: () => request("/review/strategies"),
  saveJournal: (body: unknown) =>
    request("/journal/save", { method: "POST", body: JSON.stringify(body) }),
  journalEntries: () => request("/journal/entries"),
  journalAnalysis: (month?: string) =>
    request(`/journal/analysis${month ? `?month=${month}` : ""}`),
  historyTrades: () => request("/history/trades"),
  historySummary: (month?: string) =>
    request(`/history/summary${month ? `?month=${month}` : ""}`),
  monthlyReport: (month?: string) =>
    request(`/history/monthly-report${month ? `?month=${month}` : ""}`),
  exportMonthly: (month?: string) =>
    request(`/history/monthly-export${month ? `?month=${month}` : ""}`, { method: "POST" }),
  events: () => request("/news/events"),
  telegramStatus: () => request("/telegram/status"),
  telegramTestEntry: () => request("/telegram/test-entry", { method: "POST" }),
  telegramTestExit: () => request("/telegram/test-exit", { method: "POST" }),
};
