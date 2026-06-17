import { useEffect, useState, useRef } from 'react';
import { authApi, marketApi, signalApi, jobsApi, papertradeApi, settingsApi, kiteApi } from './services/api';
import { AnalysisModal } from './components/AnalysisModal';
import { SectorDeals } from './components/SectorDeals';
import { PortfolioOptimizer } from './components/PortfolioOptimizer';
import { PaperTradingView } from './components/PaperTradingView';
import { PerformanceAuditView } from './components/PerformanceAuditView';
import { ActivePositionsView } from './components/ActivePositionsView';
import { PaperOrderModal } from './components/PaperOrderModal';
import { AdminView } from './components/AdminView';
import { List, Activity, AlertTriangle, ShieldCheck, Search, X, Loader2, Sparkles, LayoutDashboard, BarChart3, Shield } from 'lucide-react';
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
  const [mode, setMode] = useState<'intraday' | 'longterm' | 'swing'>('intraday');
  const [loading, setLoading] = useState(false);
  const [autoRestart, setAutoRestart] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [username, setUsername] = useState('');

  // Kite Status State
  const [kiteStatus, setKiteStatus] = useState<any>(null);
  const [isConnectingKite, setIsConnectingKite] = useState(false);

  // Progress State - Global Tracking
  const [jobStates, setJobStates] = useState<Record<string, any>>({});
  const scanJob = jobStates[mode === 'intraday' ? 'intraday' : mode === 'swing' ? 'swing_scan' : 'full_scan']; // Derived state for UI compatibility

  // Refs for Worker Context
  const isInitialMount = useRef(true);
  const modeRef = useRef<'intraday' | 'longterm' | 'swing'>('intraday');


  // Modal State
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const [isFailedModalOpen, setIsFailedModalOpen] = useState(false);
  const [failedSymbolsList, setFailedSymbolsList] = useState<{ symbol: string, reason: string }[]>([]);

  // Paper Trading State
  const [isBuyModalOpen, setIsBuyModalOpen] = useState(false);
  const [buySignal, setBuySignal] = useState<Signal | null>(null);
  const [virtualBalance, setVirtualBalance] = useState<number>(1000000);

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
  const [sectorSignals, setSectorSignals] = useState<Record<string, SectorData>>(() => {
    try {
      const cached = localStorage.getItem('sector_v2_intraday');
      return cached ? JSON.parse(cached) : {};
    } catch { return {}; }
  });
  const [sectorStats, setSectorStats] = useState<any>(() => {
    try {
      const cached = localStorage.getItem('sector_stats_v2_intraday');
      return cached ? JSON.parse(cached) : null;
    } catch { return null; }
  });
  const [activeTab, setActiveTab] = useState<'deals' | 'portfolio' | 'papertrade' | 'audit' | 'positions' | 'admin'>('deals');
  const lastCompletedJobId = useRef<string | null>(null);
  const currentSignalJobId = useRef<string | null>(null);

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
        const signalsRes = await signalApi.getTodaySignals(mode, jobId);
        resData = signalsRes.data;
      }

      let newData: Signal[] = [];

      // Extract array intelligently depending on nesting levels from different API endpoints
      if (Array.isArray(resData)) {
        newData = resData;
      } else if (resData && typeof resData === 'object') {
        if (Array.isArray(resData.data?.data)) {
           newData = resData.data.data;
        } else if (Array.isArray(resData.data)) {
           newData = resData.data;
        } else if (resData.buys || resData.sells || resData.holds) {
           newData = [...(resData.buys || []), ...(resData.sells || []), ...(resData.holds || [])];
        } else if (Array.isArray(resData.results)) {
           newData = resData.results;
        }
      }

      // [V14.8 JOB-AWARE TRANSITION]
      // Only keep old results if we are fetching the SAME job that produced them.
      // If the Job ID has changed, we must clear the screen for the new run.
      const isNewJob = jobId && jobId !== currentSignalJobId.current;
      
      if (!isNewJob && jobId && newData.length === 0 && signals.length > 0) {
        return;
      }

      setSignals(newData);
      if (jobId) currentSignalJobId.current = jobId;
      localStorage.setItem(`signals_v2_${mode}`, JSON.stringify(newData));
    } catch (error) {
      console.error("Failed to fetch signals:", error);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const fetchSectorSignals = async (jobId?: string) => {
    try {
      const sectorRes = await signalApi.getSectorSignals(mode, jobId);
      const resData = sectorRes.data;
      
      if (resData && resData.data) {
        // [V43 FIX] Guard against empty API responses wiping existing scan results
        // If we already have sector data and the new response is empty, keep existing data
        const newSectorData = resData.data;
        const hasExistingData = Object.keys(sectorSignals).length > 0;
        const newDataIsEmpty = typeof newSectorData === 'object' && Object.keys(newSectorData).length === 0;
        
        if (hasExistingData && newDataIsEmpty && !jobId) {
          // Don't wipe existing results with empty data from a generic (no jobId) fetch
          console.log('[V43] Blocked empty sector wipe — preserving existing scan results');
          return;
        }
        
        setSectorSignals(newSectorData);
        setSectorStats(resData.stats);
        localStorage.setItem(`sector_v2_${mode}`, JSON.stringify(newSectorData));
        if (resData.stats) localStorage.setItem(`sector_stats_v2_${mode}`, JSON.stringify(resData.stats));
      } else if (resData && Object.keys(sectorSignals).length === 0) {
        // Only set raw data if we have nothing yet
        setSectorSignals(resData);
      }
    } catch (e) {
      console.error("Auto-sector refresh failed", e);
    }
  };

  useEffect(() => {
    // Global Error Reporter
    const handleError = (event: ErrorEvent) => {
      setRuntimeError(`Runtime Error: ${event.message} at ${event.filename}:${event.lineno}`);
    };
    window.addEventListener('error', handleError);

    // 1. Initial Market Status, Account Fetch & Settings
    const fetchData = async () => {
      try {
        const [statusRes, accRes, settingsRes, kiteRes, userRes] = await Promise.all([
          marketApi.getStatus(),
          papertradeApi.getAccount(),
          settingsApi.get('auto_restart').catch(() => ({ data: { value: 'true' } })),
          kiteApi.getStatus().catch(() => ({ data: null })),
          authApi.getMe().catch(() => ({ data: { is_admin: false, username: '' } }))
        ]);
        setIsAdmin(userRes.data.is_admin);
        setUsername(userRes.data.username);
        setMarketStatus(statusRes.data);
        setVirtualBalance(accRes.data.balance);
        setAutoRestart(settingsRes.data.value.toLowerCase() === 'true');
        setKiteStatus(kiteRes.data);
      } catch (error) {
        console.error("Failed to fetch initial data:", error);
      }
    };
    fetchData();

    // Setup periodic Kite status polling (every 15s)
    const kiteInterval = setInterval(async () => {
        try {
            const res = await kiteApi.getStatus();
            setKiteStatus(res.data);
        } catch (e) {}
    }, 15000);

    // Mark that initial load is done after slight delay
    setTimeout(() => { isInitialMount.current = false; }, 1000);

    return () => {
        window.removeEventListener('error', handleError);
        clearInterval(kiteInterval);
    };
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
          // const currentMode = modeRef.current;
          // const currentJobType = currentMode === 'intraday' ? 'intraday' : currentMode === 'swing' ? 'swing_scan' : 'full_scan';
          // const activeJob = newStates[currentJobType];

          // [V14.7 REACTIVITY REFACTOR]
          // The background worker ONLY updates the job status/progress.
          // We rely on the dedicated React 'Watcher' useEffect below to detect changes 
          // in activeJob.result.progress and trigger the signal/sector fetches.
          // This eliminates stale closures and ensures 100% UI reactivity.
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

  // 3. Auto-Fetch Signals on Pulse
  // This watcher detects "Pulses" (progress updates) from the background worker.
  // Intraday/Longterm: Use API fetch (their engines write to DB directly).
  // Swing: Stream from scanJob.result.data + API fetch at completion.
  useEffect(() => {
    const isProcessing = scanJob?.status === 'processing';
    const isCompleted = scanJob?.status === 'completed';
    const jobChanged = scanJob?.id !== lastCompletedJobId.current;

    if (isProcessing) {
      if (mode === 'swing') {
        // 🚀 SWING STREAMING: Read matches from the job state payload directly.
        const liveData = scanJob?.result?.data;
        if (liveData && Array.isArray(liveData) && liveData.length > 0) {
           const sortedData = [...liveData].sort((a: any, b: any) => (b.score || 0) - (a.score || 0));
           setSignals(sortedData);
           // Dynamically build sectorSignals for real-time streaming to the Sector UI
           const streamedSectorSignals: Record<string, SectorData> = {};
           sortedData.forEach((sig: any) => {
              const sec = sig.sector || 'General';
              if (!streamedSectorSignals[sec]) {
                  streamedSectorSignals[sec] = { buys: [], holds: [], sells: [] };
              }
              if (sig.signal && sig.signal.includes('BUY')) streamedSectorSignals[sec].buys.push(sig);
              else if (sig.signal && sig.signal.includes('SELL')) streamedSectorSignals[sec].sells.push(sig);
              else streamedSectorSignals[sec].holds.push(sig);
           });
           setSectorSignals(streamedSectorSignals);
        }
      } else {
        // 📡 INTRADAY / LONGTERM: Use standard API fetch (these engines write to DB, not job state)
        fetchSignals(true, scanJob.id);
        fetchSectorSignals(scanJob.id);
      }
    } else if (isCompleted && jobChanged) {
      // 🏁 FINISH LINE: Final API refresh for ALL modes — swing uses API here too (job state is cleared by backend at completion)
      fetchSignals(true, scanJob.id);
      fetchSectorSignals(scanJob.id);
      lastCompletedJobId.current = scanJob.id;
    }
  }, [scanJob?.id, scanJob?.status, scanJob?.result?.progress, mode]);



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

  // 4. Logic: Completion Refresh — HANDLED IN PULSE WATCHER (useEffect #3) above.
  // Removed duplicate handler that was double-firing fetchSignals without jobId,
  // overwriting matched stocks with empty results.

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

  const handleBuyRequest = (signal: Signal, tradeType: 'PAPER' | 'REAL' = 'PAPER') => {
    setBuySignal({ ...signal, _intendedTradeType: tradeType } as any);
    setIsBuyModalOpen(true);
  };

  const executePaperTrade = async (qty: number) => {
    if (!buySignal) return;
    try {
      const res = await papertradeApi.placeOrder({
        symbol: buySignal.symbol,
        qty: qty,
        price: buySignal.price,
        target: buySignal.target,
        stop_loss: buySignal.stop_loss,
        score: buySignal.score,
        trade_type: (buySignal as any)._intendedTradeType || 'PAPER',
        full_scan_data: buySignal
      });
      setVirtualBalance(res.data.remaining_balance);
      setIsBuyModalOpen(false);
      alert(`Success! ${(buySignal as any)._intendedTradeType === 'REAL' ? 'LIVE ORDER PLACED FOR' : 'Bought'} ${qty} shares of ${buySignal.symbol}`);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Trade execution failed");
    }
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

      {buySignal && (
        <PaperOrderModal
          isOpen={isBuyModalOpen}
          onClose={() => setIsBuyModalOpen(false)}
          signal={buySignal}
          balance={virtualBalance}
          onConfirm={executePaperTrade}
        />
      )}

      {/* Header */}
      <header className="border-b border-border bg-card p-4 sticky top-0 z-10 shadow-sm">
        <div className="container mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold tracking-tight">Blind Trade</h1>
            {username && (
                <div className="ml-4 px-3 py-1 bg-primary/10 text-primary text-xs font-bold rounded-full uppercase tracking-widest">
                    {username} {isAdmin && '(ADMIN)'}
                </div>
            )}
          </div>

          {/* Search Bar with Suggestions - Keyed by mode for state isolation */}
          <SearchBox key={mode} onSelect={analyzeSymbol} />

          <div className="flex gap-4 text-sm items-center flex-wrap">
            {isAdmin && (
              <>
            {/* Phase 89: Background Job Toggle */}
            <div className="flex items-center gap-2 bg-muted px-3 py-1.5 rounded-full border border-border">
              <span className="text-[10px] font-black tracking-widest uppercase text-muted-foreground">
                Auto-Restart
              </span>
              <button
                onClick={async () => {
                  const newVal = !autoRestart;
                  setAutoRestart(newVal);
                  try {
                    await settingsApi.update('auto_restart', newVal.toString());
                  } catch (e) {
                    setAutoRestart(!newVal);
                    alert("Failed to update setting");
                  }
                }}
                className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${autoRestart ? 'bg-primary' : 'bg-muted-foreground/30'}`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${autoRestart ? 'translate-x-5.5' : 'translate-x-1'}`}
                />
              </button>
              <span className={`text-[10px] font-bold ${autoRestart ? 'text-primary' : 'text-muted-foreground'}`}>
                {autoRestart ? 'ON' : 'OFF'}
              </span>
            </div>

            {/* Kite Connection Status Toggle */}
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border border-border ${kiteStatus?.is_ready ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-destructive/10 border-destructive/20'}`}>
               <span className="text-[10px] font-black tracking-widest uppercase text-muted-foreground">
                KITE
               </span>
               <button
                disabled={isConnectingKite || kiteStatus?.is_ready}
                onClick={async () => {
                   setIsConnectingKite(true);
                   try {
                       const res = await kiteApi.login();
                       setKiteStatus(res.data);
                       if (res.data.is_ready) {
                           console.log("Kite Connected Successfully!");
                       } else if (res.data.login_url) {
                           alert("Auto-login failed. Please check backend console for manual login URL.");
                       } else {
                           alert("Login failed. Check backend logs.");
                       }
                   } catch (e) {
                       alert("Failed to connect to Kite");
                   } finally {
                       setIsConnectingKite(false);
                   }
                }}
                className={`relative inline-flex items-center rounded-full focus:outline-none ${isConnectingKite ? 'opacity-70' : 'hover:opacity-80'}`}
               >
                  {isConnectingKite ? (
                      <Loader2 className="w-4 h-4 animate-spin text-primary" />
                  ) : (
                      <>
                        <span className={`w-3 h-3 rounded-full mr-1.5 ${kiteStatus?.is_ready ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.5)] animate-pulse'}`}></span>
                        <span className={`text-[10px] font-bold ${kiteStatus?.is_ready ? 'text-emerald-500' : 'text-destructive'}`}>
                          {kiteStatus?.is_ready ? 'CONNECTED' : 'DISCONNECTED (CLICK)'}
                        </span>
                      </>
                  )}
               </button>
            </div>

            {/* Context-aware Start Button (Phase 90: Manual Override) */}
            {(() => {
              const jobType = mode === 'intraday' ? 'intraday' : mode === 'swing' ? 'swing_scan' : 'full_scan';
              const activeJob = jobStates[jobType];
              
              // Only hide button if a MANUAL job is already pending/processing
              const isManualActive = activeJob && 
                activeJob.trigger_source === 'manual' && 
                ['pending', 'processing', 'paused'].includes(activeJob.status);

              return (
                <button
                  onClick={async () => {
                    const scanType = mode === 'intraday' ? "intraday" : mode === 'swing' ? "swing_scan" : "full_scan";

                    if (isManualActive) {
                      alert(`A manual scan is already in progress. Please wait.`);
                      return;
                    }

                    try {
                      setSignals([]);
                      setSectorSignals({});
                      localStorage.removeItem(`signals_v2_${mode}`);
                      localStorage.removeItem(`sector_v2_${mode}`);
                      await jobsApi.triggerScan(scanType);
                    } catch (e) { 
                      alert("Failed to start scan"); 
                    }
                  }}
                  className="bg-primary text-primary-foreground px-4 py-2 rounded-md font-bold hover:bg-primary/90 transition-colors flex items-center gap-2"
                >
                  <Search className="w-4 h-4" />
                  {mode === 'intraday' ? 'RUN INTRA SCAN' : mode === 'swing' ? 'RUN SWING SCAN' : 'RUN FULL SCAN'}
                </button>
              );
            })()}
            </>
            )}

            <div className="flex items-center gap-4 text-xs font-bold tracking-wider">
              <span className="text-muted-foreground flex items-center gap-1">
                NIFTY 50
                <span className={marketStatus?.nifty_change !== undefined && marketStatus.nifty_change > 0 ? 'text-green-500' : 'text-red-500'}>
                  {marketStatus?.nifty_50 !== undefined ? marketStatus.nifty_50 : '---'}
                </span>
              </span>
              <span className="text-muted-foreground flex items-center gap-1">
                INDIA VIX
                <span className={marketStatus?.india_vix !== undefined && marketStatus.india_vix < 20 ? 'text-green-500' : 'text-red-500'}>
                  {marketStatus?.india_vix !== undefined ? marketStatus.india_vix : '---'}
                </span>
              </span>
            </div>
            <button
              onClick={() => {
                localStorage.removeItem('blind_trade_token');
                window.location.reload();
              }}
              className="ml-4 px-3 py-1 rounded-md text-xs font-bold bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
            >
              LOGOUT
            </button>
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
                  onBuy={(e, tradeType) => { e.stopPropagation(); handleBuyRequest(searchResult, tradeType); }}
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
                onClick={() => setActiveTab('papertrade')}
                className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTab === 'papertrade' ? 'bg-card shadow-sm text-primary border border-primary/20' : 'text-muted-foreground hover:text-foreground'}`}
              >
                <LayoutDashboard className="h-3 w-3" /> PAPER TRADING
              </button>
              <button
                onClick={() => setActiveTab('audit')}
                className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTab === 'audit' ? 'bg-card shadow-sm text-primary border border-primary/20' : 'text-muted-foreground hover:text-foreground'}`}
              >
                <BarChart3 className="h-3 w-3" /> SCAN HISTORY
              </button>
              <button
                onClick={() => setActiveTab('positions')}
                className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTab === 'positions' ? 'bg-card shadow-sm text-primary border border-primary/20' : 'text-muted-foreground hover:text-foreground'}`}
              >
                <ShieldCheck className="h-3 w-3" /> POSITIONS
              </button>
              {isAdmin && (
                <button
                  onClick={() => setActiveTab('admin')}
                  className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTab === 'admin' ? 'bg-card shadow-sm text-primary border border-primary/20' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  <Shield className="h-3 w-3" /> ADMIN
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Signals Grid */}
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : activeTab === 'admin' ? (
            <AdminView />
        ) : (
          <>
            {activeTab === 'deals' && (
              <ErrorBoundary>
                <SectorDeals
                  data={sectorSignals}
                  stats={sectorStats}
                  mode={mode}
                  onSignalClick={openAnalysis}
                  onBuy={handleBuyRequest}
                />
              </ErrorBoundary>
            )}
            {activeTab === 'portfolio' && <PortfolioOptimizer />}
            {activeTab === 'papertrade' && <PaperTradingView />}
            {activeTab === 'audit' && <PerformanceAuditView />}
            {activeTab === 'positions' && <ActivePositionsView />}
          </>
        )}
      </main >
    </div >
  );
}

export default App;
