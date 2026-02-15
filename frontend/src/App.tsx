import { useEffect, useState } from 'react';
import { marketApi, signalApi, jobsApi } from './services/api';
import { AnalysisModal } from './components/AnalysisModal';

import { SectorDeals } from './components/SectorDeals';
import { PortfolioOptimizer } from './components/PortfolioOptimizer';
import { PieChart, List, Activity, AlertTriangle, ShieldCheck, Search, X, Loader2, Sparkles } from 'lucide-react';
import { SearchBox } from './components/SearchBox';
import { StockCardLongTerm } from './components/StockCardLongTerm';
import { StockCardIntraday } from './components/StockCardIntraday';
import type { Signal } from './components/DealCard';
import { ErrorBoundary } from './components/ErrorBoundary';

function App() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [marketStatus, setMarketStatus] = useState<any>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [mode, setMode] = useState<'intraday' | 'longterm'>('longterm');
  const [loading, setLoading] = useState(false);

  // Progress State
  const [scanJob, setScanJob] = useState<any>(null);

  // Modal State
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Search State
  const [searchResult, setSearchResult] = useState<Signal | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  // Sector Signals State
  interface SectorData {
    buys: Signal[];
    holds: Signal[];
    sells: Signal[];
  }
  const [sectorSignals, setSectorSignals] = useState<Record<string, SectorData>>({});
  const [loadingSector, setLoadingSector] = useState(false);
  const [activeTab, setActiveTab] = useState<'deals' | 'portfolio'>('deals');

  const openAnalysis = (signal: Signal) => {
    setSelectedSignal(signal);
    setIsModalOpen(true);
  };

  const fetchSignals = async (silent = false) => {
    if (!silent && !signals.length) setLoading(true);
    try {
      const signalsRes = await signalApi.getTodaySignals(mode);
      const resData = signalsRes.data;
      let newData: Signal[] = [];

      if (resData && typeof resData === 'object' && !Array.isArray(resData)) {
        // Flatten buys, sells, holds into a single array for state/cache
        newData = [...(resData.buys || []), ...(resData.sells || []), ...(resData.holds || [])];
      } else if (Array.isArray(resData)) {
        newData = resData;
      }

      setSignals(newData);
      localStorage.setItem(`signals_v2_${mode}`, JSON.stringify(newData));
    } catch (error) {
      console.error("Failed to fetch signals:", error);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const fetchSectorSignals = async (silent = false) => {
    if (!silent && !Object.keys(sectorSignals).length) setLoadingSector(true);
    try {
      const sectorRes = await signalApi.getSectorSignals(mode);
      setSectorSignals(sectorRes.data);
      localStorage.setItem(`sector_v2_${mode}`, JSON.stringify(sectorRes.data));
    } catch (e) {
      console.error("Auto-sector refresh failed", e);
    } finally {
      if (!silent) setLoadingSector(false);
    }
  };

  useEffect(() => {
    // Global Error Reporter
    const handleError = (event: ErrorEvent) => {
      setRuntimeError(`Runtime Error: ${event.message} at ${event.filename}:${event.lineno}`);
    };
    window.addEventListener('error', handleError);

    // 1. Initial Market Status Fetch
    const fetchData = async () => {
      try {
        const statusRes = await marketApi.getStatus();
        setMarketStatus(statusRes.data);
      } catch (error) {
        console.error("Failed to fetch market status:", error);
      }
    };
    fetchData();

    // 2. Poll Job Status (2s)
    const pollJobStatus = async () => {
      try {
        const jobType = mode === 'intraday' ? 'intraday' : 'full_scan';
        const res = await jobsApi.getStatus(jobType);
        setScanJob(res.data);
      } catch (e: any) {
        if (!e.response || e.response.status !== 404) {
          // console.error("Job status poll error:", e);
        } else {
          setScanJob(null); // Clear if no job of this type found
        }
      }
    };
    pollJobStatus();
    const jobInterval = setInterval(pollJobStatus, 2000);
    return () => {
      clearInterval(jobInterval);
      window.removeEventListener('error', handleError);
    };
  }, [mode]);

  // 3. Logic: Mode Switch & Dashboard Sync
  useEffect(() => {
    const cachedSignals = localStorage.getItem(`signals_v2_${mode}`);
    const cachedSectors = localStorage.getItem(`sector_v2_${mode}`);

    // 1. CLEAR STALE STATE IMMEDIATELY to prevent "ghost" data collision
    setSignals([]);
    setSectorSignals({});
    // setScanJob(null); // Shield Wall: OFF - Persist job state across tabs
    setLoading(true);
    setLoadingSector(true);

    // 2. Load mode-specific cache if it exists (allows partial data while fetching)
    if (cachedSignals) setSignals(JSON.parse(cachedSignals));
    if (cachedSectors) setSectorSignals(JSON.parse(cachedSectors));

    // Clear modals & reset state appropriately on mode switch
    setIsModalOpen(false);
    setSelectedSignal(null);

    // 3. Refresh for the new mode anyway
    fetchSignals();
    fetchSectorSignals();

    return () => { };
  }, [mode]);

  // 4. Logic: Incremental/Completion Refresh during Jobs
  useEffect(() => {
    let interval: any;

    if (scanJob?.status === 'completed') {
      fetchSignals(true);
      fetchSectorSignals(true);
    } else if (scanJob?.status === 'processing') {
      interval = setInterval(() => {
        fetchSignals(true);
        fetchSectorSignals(true);
      }, 10000);
    }

    return () => clearInterval(interval);
  }, [scanJob?.status, scanJob?.id, mode]);

  const analyzeSymbol = async (symbol: string) => {
    setSearching(true);
    setSearchError('');
    setSearchResult(null);

    try {
      const res = await signalApi.analyze(symbol, mode);
      if (res.data.error) {
        setSearchError(res.data.error);
      } else {
        // Ensure analysis_mode is tagged for unique UI attributes
        setSearchResult({ ...res.data, analysis_mode: 'on-demand' });
      }
    } catch (err) {
      setSearchError('Failed to analyze symbol. Check validity.');
    } finally {
      setSearching(false);
    }
  };

  const clearSearch = () => {
    setSearchResult(null);
    setSearchError('');
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* Analysis Modal */}
      <ErrorBoundary>
        <AnalysisModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          data={selectedSignal}
        />
      </ErrorBoundary>

      {/* Header */}
      <header className="border-b border-border bg-card p-4 sticky top-0 z-10 shadow-sm">
        <div className="container mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold tracking-tight">Blind Trade Engine</h1>
          </div>

          {/* Search Bar with Suggestions */}
          <SearchBox onSelect={analyzeSymbol} />

          <div className="flex gap-4 text-sm hidden md:flex items-center">
            {/* Scan Control Functions */}
            {scanJob?.status === 'processing' || scanJob?.status === 'paused' ? (
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    const jobType = mode === 'intraday' ? 'intraday' : 'full_scan';
                    if (scanJob.status === 'paused') {
                      await jobsApi.resume(jobType);
                    } else {
                      await jobsApi.pause(jobType);
                    }
                  }}
                  className="bg-amber-500 text-white px-3 py-1.5 rounded-md font-bold hover:bg-amber-600 transition-colors flex items-center gap-1.5"
                >
                  {scanJob.status === 'paused' ? (
                    <><Activity className="w-4 h-4" /> RESUME</>
                  ) : (
                    <><X className="w-4 h-4" /> PAUSE</>
                  )}
                </button>
                <button
                  onClick={async () => {
                    const jobType = mode === 'intraday' ? 'intraday' : 'full_scan';
                    if (confirm(`Stop ${mode.toUpperCase()} scan and save partial results?`)) {
                      await jobsApi.stop(jobType);
                      setScanJob(null); // Immediate UI clear
                    }
                  }}
                  className="bg-destructive text-white px-3 py-1.5 rounded-md font-bold hover:bg-destructive/90 transition-colors flex items-center gap-1.5"
                >
                  <X className="w-4 h-4" /> STOP
                </button>
              </div>
            ) : (
              <button
                onClick={async () => {
                  const scanLabel = mode === 'intraday' ? "Intraday Analysis" : "Full Market Scan";
                  const scanType = mode === 'intraday' ? "intraday" : "full_scan";

                  if (confirm(`Start ${scanLabel}? This runs in background.`)) {
                    try {
                      await jobsApi.triggerScan(scanType);
                    } catch (e) { alert("Failed to start scan"); }
                  }
                }}
                className="bg-primary text-primary-foreground px-4 py-2 rounded-md font-bold hover:bg-primary/90 transition-colors flex items-center gap-2"
              >
                <Search className="w-4 h-4" />
                {mode === 'intraday' ? 'RUN INTRA SCAN' : 'RUN FULL SCAN'}
              </button>
            )}

            <div className="flex flex-col items-end">
              <span className="text-muted-foreground">NIFTY 50</span>
              <span className="font-mono font-bold text-up">{marketStatus?.nifty_50 || '---'}</span>
            </div>
            <div className="flex flex-col items-end">
              <span className="text-muted-foreground">INDIA VIX</span>
              <span className="font-mono font-bold text-destructive">{marketStatus?.india_vix || '---'}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Progress Bar */}
      {(scanJob?.status === 'pending' || scanJob?.status === 'processing' || scanJob?.status === 'paused' || scanJob?.status === 'stopped') && (
        <div className={`bg-primary/10 border-b border-primary/20 px-4 py-3 animate-in fade-in slide-in-from-top-1 ${scanJob.status === 'paused' ? 'bg-amber-500/10 border-amber-500/20' : scanJob.status === 'stopped' ? 'bg-destructive/10 border-destructive/20' : ''}`}>
          <div className="container mx-auto">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-2 text-xs font-bold text-primary mb-3">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  {scanJob.status === 'processing' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : scanJob.status === 'paused' ? (
                    <Activity className="w-4 h-4 text-amber-600" />
                  ) : (
                    <X className="w-4 h-4 text-destructive" />
                  )}
                  <span className={`uppercase tracking-wider ${scanJob.status === 'paused' ? 'text-amber-700' : scanJob.status === 'stopped' ? 'text-destructive' : ''}`}>
                    [{mode === 'intraday' ? 'INTRA' : 'LONG-TERM'}] {scanJob.result?.status_msg || 'INITIALIZING SCAN...'}
                  </span>
                </div>
                {scanJob.result?.active_symbols && scanJob.result.active_symbols.length > 0 && (
                  <div className="flex items-center gap-2 text-[10px] text-primary/60 font-medium">
                    <span className="bg-primary/20 px-1.5 py-0.5 rounded">CONCURRENT BATCH:</span>
                    <span>{Array.isArray(scanJob.result.active_symbols) ? scanJob.result.active_symbols.join(", ") : 'Scanning...'}</span>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm">
                  {scanJob.result?.progress || 0} / {scanJob.result?.total_steps || '...'} STOCKS
                </span>
                <span className="bg-primary text-primary-foreground px-2 py-1 rounded text-lg">
                  {scanJob.result?.total_steps ? Math.round(((scanJob.result?.progress || 0) / scanJob.result.total_steps) * 100) : 0}%
                </span>
              </div>
            </div>
            <div className="h-2 bg-primary/20 rounded-full overflow-hidden shadow-inner">
              <div
                className="h-full bg-primary transition-all duration-700 ease-in-out relative"
                style={{ width: `${scanJob.result?.total_steps ? ((scanJob.result?.progress || 0) / scanJob.result.total_steps) * 100 : 0}%` }}
              >
                <div className="absolute inset-0 bg-white/20 animate-pulse" />
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="container mx-auto p-6">
        {runtimeError && (
          <div className="mb-8 p-6 rounded-2xl bg-destructive border-4 border-white shadow-2xl text-white animate-bounce">
            <h2 className="text-xl font-black uppercase mb-2">🚨 CRITICAL UI CRASH DETECTED</h2>
            <p className="font-mono text-sm break-all">{runtimeError}</p>
            <button onClick={() => window.location.reload()} className="mt-4 bg-white text-destructive px-4 py-2 rounded-lg font-bold">RELOAD APP</button>
          </div>
        )}



        {/* Risk Level Banner */}
        <div className="mb-8 rounded-lg border border-yellow-500/20 bg-yellow-500/10 p-4 text-yellow-500 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5" />
          <p className="font-medium">Market Volatility is Moderate. Stick to strict Stop Losses.</p>
        </div>

        {/* Search Result Section */}
        {searching && (
          <div className="mb-8 flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        )}

        {searchError && (
          <div className="mb-8 p-4 rounded-lg bg-destructive/10 text-destructive text-center font-medium border border-destructive/20">
            {searchError}
          </div>
        )}

        {searchResult && (
          <div className="mb-10 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold flex items-center gap-2 text-primary">
                <Sparkles className="h-5 w-5 text-amber-500" />
                On-Demand Analysis Result
              </h2>
              <button onClick={clearSearch} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 bg-muted px-2 py-1 rounded-md">
                <X size={12} /> CLEAR SEARCH
              </button>
            </div>

            <ErrorBoundary>
              {mode === 'intraday' ? (
                <StockCardIntraday
                  signal={searchResult}
                  onClick={() => openAnalysis(searchResult)}
                />
              ) : (
                <StockCardLongTerm
                  signal={searchResult}
                  onClick={() => openAnalysis(searchResult)}
                />
              )}
            </ErrorBoundary>
          </div>
        )}

        <div className="mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-2xl font-black flex items-center gap-2 tracking-tight">
              <ShieldCheck className="h-6 w-6 text-emerald-500" />
              MARKET HUB <span className="text-muted-foreground font-light text-lg">/ {mode === 'intraday' ? 'Intraday Advice' : 'Long-Term Scans'}</span>
            </h2>
            <div className="flex gap-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
              <span className={mode === 'intraday' ? 'text-primary' : ''}>Intraday</span>
              <span>•</span>
              <span className={mode === 'longterm' ? 'text-primary' : ''}>Long-Term</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex bg-muted p-1 rounded-xl border border-border">
              <button
                onClick={() => setMode('intraday')}
                className={`px-4 py-1.5 rounded-lg text-[10px] font-black tracking-widest uppercase transition-all ${mode === 'intraday' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                INTRA
              </button>
              <button
                onClick={() => setMode('longterm')}
                className={`px-4 py-1.5 rounded-lg text-[10px] font-black tracking-widest uppercase transition-all ${mode === 'longterm' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                LONGTERM
              </button>
            </div>

            <div className="flex bg-muted p-1 rounded-xl border border-border">
              <button
                onClick={() => setActiveTab('deals')}
                className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTab === 'deals' ? 'bg-card shadow-sm text-primary' : 'text-muted-foreground hover:text-foreground'}`}
              >
                <List className="h-3 w-3" /> ACTIVE DEALS
              </button>
              <button
                onClick={() => setActiveTab('portfolio')}
                className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTab === 'portfolio' ? 'bg-card shadow-sm text-primary' : 'text-muted-foreground hover:text-foreground'}`}
              >
                <PieChart className="h-3 w-3" /> PORTFOLIO HEALTH
              </button>
            </div>
          </div>
        </div>

        {/* Signals Grid */}
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : activeTab === 'deals' ? (
          <>
            {/* Sector-wise Dashboard (Unified View) */}
            <ErrorBoundary>
              <SectorDeals
                data={sectorSignals}
                loading={loadingSector}
                mode={mode}
                onRefresh={() => fetchSectorSignals(false)}
                onSignalClick={openAnalysis}
              />
            </ErrorBoundary>
          </>
        ) : (
          <PortfolioOptimizer />
        )}
      </main >
    </div >
  );
}

export default App;
