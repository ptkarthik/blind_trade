import { useEffect, useState, useRef } from 'react';
import { marketApi, signalApi, jobsApi } from './services/api';
import { AnalysisModal } from './components/AnalysisModal';

import { SectorDeals } from './components/SectorDeals';
import { PortfolioOptimizer } from './components/PortfolioOptimizer';
import { PieChart, List, Activity, AlertTriangle, ShieldCheck, Search, X, Loader2, Sparkles } from 'lucide-react';
import { SearchBox } from './components/SearchBox';
import { StockCardLongTerm } from './components/StockCardLongTerm';
import { StockCardIntraday } from './components/StockCardIntraday';
import { StockCardSwing } from './components/StockCardSwing';
import { FailedSymbolsModal } from './components/FailedSymbolsModal';
import type { Signal } from './components/DealCard';
import { ErrorBoundary } from './components/ErrorBoundary';

function App() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [marketStatus, setMarketStatus] = useState<any>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [mode, setMode] = useState<'intraday' | 'longterm' | 'swing'>('longterm');
  const [loading, setLoading] = useState(false);

  // Progress State - Global Tracking
  const [jobStates, setJobStates] = useState<Record<string, any>>({});
  const scanJob = jobStates[mode === 'intraday' ? 'intraday' : mode === 'swing' ? 'swing_scan' : 'full_scan']; // Derived state for UI compatibility

  // Refs for Worker Context
  const isInitialMount = useRef(true);
  const modeRef = useRef<'intraday' | 'longterm' | 'swing'>(mode);


  // Modal State
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [isFailedModalOpen, setIsFailedModalOpen] = useState(false);
  const [failedSymbolsList, setFailedSymbolsList] = useState<{ symbol: string, reason: string }[]>([]);

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

  const fetchSignals = async (silent = false, jobId?: string) => {
    if (!silent && !signals.length) setLoading(true);
    try {
      let resData;
      if (jobId) {
        const res = await jobsApi.getResults(jobId);
        resData = res.data;
      } else {
        const signalsRes = await signalApi.getTodaySignals(mode);
        resData = signalsRes.data;
      }

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

    // Mark that initial load is done after slight delay
    setTimeout(() => { isInitialMount.current = false; }, 1000);

    return () => window.removeEventListener('error', handleError);
  }, []);

  // 2. Poll Job Status (2s) - Using Web Worker for background reliability
  // We use a REF to track mode inside the closure without restarting the worker
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    const worker = new Worker(new URL('./services/pollingWorker.ts', import.meta.url), { type: 'module' });

    // Worker Handler
    worker.onmessage = async (e) => {
      if (e.data === 'TICK') {
        try {
          // Poll ALL THREE job types in parallel
          const [intraRes, fullRes, swingRes] = await Promise.allSettled([
            jobsApi.getStatus('intraday'),
            jobsApi.getStatus('full_scan'),
            jobsApi.getStatus('swing_scan')
          ]);

          const newStates: Record<string, any> = {};

          if (intraRes.status === 'fulfilled') newStates['intraday'] = intraRes.value.data;
          else newStates['intraday'] = null;

          if (fullRes.status === 'fulfilled') newStates['full_scan'] = fullRes.value.data;
          else newStates['full_scan'] = null;

          if (swingRes.status === 'fulfilled') newStates['swing_scan'] = swingRes.value.data;
          else newStates['swing_scan'] = null;

          setJobStates(prev => {
            // Preserve "stopping" state if backend hasn't caught up yet to avoid UI flicker
            const merged = { ...newStates };
            if (prev['intraday']?.status === 'stopping' && newStates['intraday']?.status !== 'stopped') {
              merged['intraday'] = prev['intraday'];
            }
            if (prev['full_scan']?.status === 'stopping' && newStates['full_scan']?.status !== 'stopped') {
              merged['full_scan'] = prev['full_scan'];
            }
            if (prev['swing_scan']?.status === 'stopping' && newStates['swing_scan']?.status !== 'stopped') {
              merged['swing_scan'] = prev['swing_scan'];
            }
            return merged;
          });

          // Trigger Signal Fetch if the ACTIVE mode's job is processing
          // We use the Ref to know the current active view
          const currentMode = modeRef.current;
          const currentJobType = currentMode === 'intraday' ? 'intraday' : currentMode === 'swing' ? 'swing_scan' : 'full_scan';
          const activeJob = newStates[currentJobType];

          if (activeJob?.status === 'processing') {
            // Refresh signals silently
          }
        } catch (err) {
          // Silent fail
        }
      }
    };

    worker.postMessage({ action: 'START', interval: 2000 });

    return () => {
      worker.postMessage({ action: 'STOP' });
      worker.terminate();
    };
  }, []); // Run ONCE. Worker persists across mode switches.

  // 3. Auto-Fetch Signals on Pulse (Replaces the Interval)
  useEffect(() => {
    if (scanJob?.status === 'processing') {
      // fetchSignals(true); // DISABLED: Don't poll full results every 2s, only progress
      fetchSectorSignals(true);
    }
  }, [scanJob?.progress, scanJob?.updated_at]); // Trigger on job updates


  // 3. Logic: Mode Switch & Dashboard Sync
  useEffect(() => {
    // 1. OPTIMISTIC TRANSITION: Remove cache as requested by user
    setSignals([]);
    setSectorSignals({});

    // Clear the active rendering list locally so it doesn't try to auto-hydrate from old storage
    // if the fetch is slow or fails
    localStorage.removeItem(`signals_v2_${mode}`);
    localStorage.removeItem(`sector_v2_${mode}`);

    // 2. We only set high-level loading flags
    setLoading(true);
    setLoadingSector(true);

    // Clear modals & reset state appropriately on mode switch
    setIsModalOpen(false);
    setSelectedSignal(null);
    setSearchError('');
    setSearchResult(null);
    setSearching(false);

    // 3. Refresh for the new mode
    fetchSignals();
    fetchSectorSignals();

    return () => { };
  }, [mode]);

  // 4. Logic: Completion Refresh
  useEffect(() => {
    if (scanJob?.status === 'completed' || scanJob?.status === 'stopped') {
      // ONLY pass the jobId if the completed job actually belongs to the active tab's mode.
      // Otherwise, an intraday job finishing in the background will overwrite the swing tab's data!
      const currentJobType = mode === 'intraday' ? 'intraday' : mode === 'swing' ? 'swing_scan' : 'full_scan';

      if (scanJob?.id && scanJob?.type === currentJobType) {
        fetchSignals(true, scanJob.id);
      } else {
        fetchSignals(true);
      }
      fetchSectorSignals(true);
    }
  }, [scanJob?.status, mode]);

  const analyzeSymbol = async (symbol: string) => {
    setSearching(true);
    setSearchError('');
    setSearchResult(null);

    try {
      const res = await signalApi.analyze(symbol, mode);
      if (res.data.error) {
        setSearchError(res.data.error);
      } else {
        // Ensure we preserve the original analysis_mode for UI layout logic
        // but mark it as an on-demand result for the header
        setSearchResult({ ...res.data, is_ondemand: true });
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
    setSearching(false);
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* Analysis Modal */}
      <ErrorBoundary key={selectedSignal ? selectedSignal.symbol : 'modal-boundary'}>
        <AnalysisModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          data={selectedSignal}
        />
      </ErrorBoundary>

      <FailedSymbolsModal
        isOpen={isFailedModalOpen}
        onClose={() => setIsFailedModalOpen(false)}
        symbols={failedSymbolsList}
      />

      {/* Header */}
      <header className="border-b border-border bg-card p-4 sticky top-0 z-10 shadow-sm">
        <div className="container mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold tracking-tight">Blind Trade Engine</h1>
          </div>

          {/* Search Bar with Suggestions - Keyed by mode for state isolation */}
          <SearchBox key={mode} onSelect={analyzeSymbol} />

          <div className="flex gap-4 text-sm hidden md:flex items-center">
            {/* Context-aware Start Button */}
            {(!jobStates[mode === 'intraday' ? 'intraday' : mode === 'swing' ? 'swing_scan' : 'full_scan'] ||
              !['pending', 'processing', 'paused'].includes(jobStates[mode === 'intraday' ? 'intraday' : mode === 'swing' ? 'swing_scan' : 'full_scan']?.status)) && (
                <button
                  onClick={async () => {
                    const scanLabel = mode === 'intraday' ? "Intraday Analysis" : mode === 'swing' ? "Swing Scan" : "Full Market Scan";
                    const scanType = mode === 'intraday' ? "intraday" : mode === 'swing' ? "swing_scan" : "full_scan";

                    if (confirm(`Start ${scanLabel}? This runs in background.`)) {
                      try {
                        setSignals([]);
                        setSectorSignals({});
                        localStorage.removeItem(`signals_v2_${mode}`);
                        localStorage.removeItem(`sector_v2_${mode}`);
                        await jobsApi.triggerScan(scanType);
                      } catch (e) { alert("Failed to start scan"); }
                    }
                  }}
                  className="bg-primary text-primary-foreground px-4 py-2 rounded-md font-bold hover:bg-primary/90 transition-colors flex items-center gap-2"
                >
                  <Search className="w-4 h-4" />
                  {mode === 'intraday' ? 'RUN INTRA SCAN' : mode === 'swing' ? 'RUN SWING SCAN' : 'RUN FULL SCAN'}
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

      {/* Progress Bars - Mode Specific Tracking */}
      <div className="sticky top-[73px] z-[9] flex flex-col">
        {[mode === 'intraday' ? 'intraday' : mode === 'swing' ? 'swing_scan' : 'full_scan'].map(type => {
          const job = jobStates[type];
          if (!job || !['pending', 'processing', 'paused', 'stopping'].includes(job.status)) return null;

          const label = type === 'intraday' ? 'INTRADAY' : type === 'swing_scan' ? 'SWING' : 'LONG-TERM';
          const progress = job.result?.progress || 0;
          const total = job.result?.total_steps || 0;
          const percent = total ? Math.round((progress / total) * 100) : 0;

          return (
            <div key={type} className={`bg-card border-b border-border px-4 py-2 animate-in fade-in slide-in-from-top-1 ${job.status === 'paused' ? 'bg-amber-500/5' : 'bg-primary/5'}`}>
              <div className="container mx-auto">
                <div className="flex justify-between items-center gap-4 text-[10px] font-bold">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex items-center gap-1.5 shrink-0">
                      {job.status === 'processing' ? (
                        <Loader2 className="w-3 h-3 animate-spin text-primary" />
                      ) : job.status === 'paused' ? (
                        <Activity className="w-3 h-3 text-amber-500" />
                      ) : (
                        <Loader2 className="w-3 h-3 text-muted-foreground" />
                      )}
                      <span className={`tracking-widest ${job.status === 'paused' ? 'text-amber-600' : 'text-primary'}`}>
                        {label}: {job.result?.status_msg || 'INITIALIZING...'}
                      </span>
                    </div>
                    {job.result?.active_symbols && job.result.active_symbols.length > 0 && (
                      <span className="truncate text-muted-foreground/60 hidden sm:inline">
                        Scanning: {Array.isArray(job.result.active_symbols) ? job.result.active_symbols.slice(0, 3).join(", ") : '...'}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-4 shrink-0">
                    {/* Inline Controls for each Bar */}
                    <div className="flex gap-1 mr-2 border-r border-border pr-3">
                      <button
                        disabled={job.status === 'stopping'}
                        onClick={async () => {
                          if (job.status === 'paused') await jobsApi.resume(type);
                          else await jobsApi.pause(type);
                        }}
                        className={`p-1 rounded hover:bg-muted transition-colors ${job.status === 'paused' ? 'text-amber-600' : 'text-primary'}`}
                        title={job.status === 'paused' ? 'Resume' : 'Pause'}
                      >
                        {job.status === 'paused' ? <Activity size={14} /> : <X size={14} className="rotate-45" />}
                      </button>
                      <button
                        disabled={job.status === 'stopping'}
                        onClick={async () => {
                          if (confirm(`Stop ${label} scan?`)) {
                            setJobStates(prev => ({
                              ...prev,
                              [type]: { ...prev[type], status: 'stopping' }
                            }));
                            await jobsApi.stop(type);
                          }
                        }}
                        className="p-1 rounded hover:bg-destructive/10 text-destructive transition-colors"
                        title="Stop"
                      >
                        <X size={14} />
                      </button>
                    </div>

                    <div className="flex items-center gap-2">
                      {job.result?.failed_symbols && job.result.failed_symbols.length > 0 && (
                        <button
                          onClick={() => {
                            setFailedSymbolsList(job.result.failed_symbols);
                            setIsFailedModalOpen(true);
                          }}
                          className="text-[10px] bg-destructive/10 text-destructive px-2 py-0.5 rounded hover:bg-destructive/20 font-bold tracking-widest transition-colors flex items-center gap-1"
                          title="View Failed Validations"
                        >
                          <AlertTriangle className="w-3 h-3" />
                          {job.result.failed_symbols.length} FAILED
                        </button>
                      )}
                      <span className="text-muted-foreground">{progress} / {total || '...'}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[11px] ${job.status === 'paused' ? 'bg-amber-100 text-amber-700' : 'bg-primary/20 text-primary'}`}>
                        {percent}%
                      </span>
                    </div>
                  </div>
                </div>
                <div className="mt-1.5 h-1 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-700 ease-in-out relative ${job.status === 'paused' ? 'bg-amber-500' : 'bg-primary'}`}
                    style={{ width: `${percent}%` }}
                  >
                    <div className="absolute inset-0 bg-white/20 animate-pulse" />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

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
              ) : mode === 'swing' ? (
                <StockCardSwing
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
              MARKET HUB <span className="text-muted-foreground font-light text-lg">/ {mode === 'intraday' ? 'Intraday Advice' : mode === 'swing' ? 'Swing Breakouts' : 'Long-Term Scans'}</span>
            </h2>
            <div className="flex gap-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
              <span className={mode === 'intraday' ? 'text-primary' : ''}>Intraday</span>
              <span>•</span>
              <span className={mode === 'swing' ? 'text-primary' : ''}>Swing</span>
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
                onClick={() => setMode('swing')}
                className={`px-4 py-1.5 rounded-lg text-[10px] font-black tracking-widest uppercase transition-all ${mode === 'swing' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                SWING
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
