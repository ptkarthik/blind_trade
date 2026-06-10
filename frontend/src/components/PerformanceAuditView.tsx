import { useState, useEffect } from 'react';
import { auditApi } from '../services/api';
import { Activity, TrendingUp, TrendingDown, AlertTriangle, RefreshCw, ChevronDown, ChevronUp, Target, Shield, BarChart3, Loader2, Brain, Zap } from 'lucide-react';

interface AuditStock {
  rank: number;
  symbol: string;
  name: string;
  sector: string;
  score: number;
  signal: string;
  strategy: string;
  setup_type: string;
  confidence: string;
  ai_approved: boolean | null;
  entry_price: number;
  stop_loss: number | null;
  target: number | null;
  vol_ratio: number | null;
  delivery_pct: number | null;
  eod_price: number | null;
  eod_change_pct: number | null;
  performance_tag: string | null;
  is_tracked: boolean;
  reasons: any[];
}

interface AuditReport {
  status: string;
  date: string;
  total_tracked: number;
  total_snapshots: number;
  winners: number;
  losers: number;
  traps: number;
  avg_return_pct: number;
  accuracy_pct: number;
  stocks: AuditStock[];
}

interface HistoryEntry {
  date: string;
  total_tracked: number;
  winners: number;
  losers: number;
  traps: number;
  avg_return_pct: number;
  accuracy_pct: number;
}

interface TrapPatternEntry {
  id: string;
  source_symbol: string;
  source_date: string;
  loss_pct: number;
  trap_type: string;
  confidence: number;
  match_count: number;
  indicators: Record<string, number>;
}

export function PerformanceAuditView() {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [trapPatterns, setTrapPatterns] = useState<TrapPatternEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [expandedStock, setExpandedStock] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [activeView, setActiveView] = useState<'today' | 'history' | 'brain'>('today');

  const fetchReport = async (date?: string) => {
    setLoading(true);
    try {
      const res = await auditApi.getReport(date);
      setReport(res.data);
    } catch (e) {
      console.error('Failed to fetch audit report:', e);
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await auditApi.getHistory(14);
      setHistory(res.data?.data || []);
    } catch (e) {
      console.error('Failed to fetch history:', e);
    }
  };

  const fetchTraps = async () => {
    try {
      const res = await auditApi.getTraps();
      setTrapPatterns(res.data?.data || []);
    } catch (e) {
      console.error('Failed to fetch trap patterns:', e);
    }
  };

  const triggerEvaluation = async () => {
    setEvaluating(true);
    try {
      await auditApi.triggerEvaluation(selectedDate || undefined);
      // Refetch report after evaluation
      await fetchReport(selectedDate || undefined);
    } catch (e) {
      console.error('Failed to trigger evaluation:', e);
    } finally {
      setEvaluating(false);
    }
  };

  useEffect(() => {
    fetchReport();
    fetchHistory();
    fetchTraps();
  }, []);

  const getPerformanceColor = (tag: string | null) => {
    switch (tag) {
      case 'WINNER': return 'text-emerald-500';
      case 'NEUTRAL': return 'text-amber-500';
      case 'LOSER': return 'text-orange-500';
      case 'TRAP': return 'text-red-500';
      default: return 'text-muted-foreground';
    }
  };

  const getPerformanceBg = (tag: string | null) => {
    switch (tag) {
      case 'WINNER': return 'bg-emerald-500/10 border-emerald-500/20';
      case 'NEUTRAL': return 'bg-amber-500/10 border-amber-500/20';
      case 'LOSER': return 'bg-orange-500/10 border-orange-500/20';
      case 'TRAP': return 'bg-red-500/10 border-red-500/20';
      default: return 'bg-muted/50 border-border';
    }
  };

  const getChangeIcon = (pct: number | null) => {
    if (pct === null) return null;
    if (pct >= 0) return <TrendingUp className="w-4 h-4 text-emerald-500" />;
    return <TrendingDown className="w-4 h-4 text-red-500" />;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-xl font-black tracking-tight flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-primary" />
            SCAN PERFORMANCE AUDIT
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            Track how your recommendations performed after the scan
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-muted p-1 rounded-lg border border-border">
            <button
              onClick={() => setActiveView('today')}
              className={`px-3 py-1.5 rounded-md text-[10px] font-black tracking-widest uppercase transition-all ${activeView === 'today' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >
              TODAY
            </button>
            <button
              onClick={() => { setActiveView('history'); fetchHistory(); }}
              className={`px-3 py-1.5 rounded-md text-[10px] font-black tracking-widest uppercase transition-all ${activeView === 'history' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >
              HISTORY
            </button>
            <button
              onClick={() => { setActiveView('brain'); fetchTraps(); }}
              className={`px-3 py-1.5 rounded-md text-[10px] font-black tracking-widest uppercase transition-all ${activeView === 'brain' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >
              🧠 BRAIN
            </button>
          </div>
          <button
            onClick={triggerEvaluation}
            disabled={evaluating}
            className="flex items-center gap-1.5 bg-primary text-primary-foreground px-3 py-1.5 rounded-md text-[10px] font-black tracking-widest uppercase hover:bg-primary/90 disabled:opacity-50 transition-all"
          >
            {evaluating ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
            {evaluating ? 'EVALUATING...' : 'UPDATE PRICES'}
          </button>
        </div>
      </div>

      {activeView === 'today' ? (
        <>
          {/* Summary Cards */}
          {report && report.status === 'OK' && report.total_tracked > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div className="rounded-lg border border-border bg-card p-4">
                <div className="text-[10px] font-bold tracking-widest uppercase text-muted-foreground">TRACKED</div>
                <div className="text-2xl font-black mt-1">{report.total_tracked}</div>
                <div className="text-[10px] text-muted-foreground">of {report.total_snapshots} snapshots</div>
              </div>
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4">
                <div className="text-[10px] font-bold tracking-widest uppercase text-emerald-600">WINNERS</div>
                <div className="text-2xl font-black text-emerald-500 mt-1">{report.winners}</div>
                <div className="text-[10px] text-emerald-600/60">&gt;3% gains</div>
              </div>
              <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4">
                <div className="text-[10px] font-bold tracking-widest uppercase text-red-600">TRAPS</div>
                <div className="text-2xl font-black text-red-500 mt-1">{report.traps}</div>
                <div className="text-[10px] text-red-600/60">&gt;2% losses</div>
              </div>
              <div className="rounded-lg border border-border bg-card p-4">
                <div className="text-[10px] font-bold tracking-widest uppercase text-muted-foreground">AVG RETURN</div>
                <div className={`text-2xl font-black mt-1 ${report.avg_return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                  {report.avg_return_pct >= 0 ? '+' : ''}{report.avg_return_pct}%
                </div>
              </div>
              <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
                <div className="text-[10px] font-bold tracking-widest uppercase text-primary">ACCURACY</div>
                <div className="text-2xl font-black text-primary mt-1">{report.accuracy_pct}%</div>
                <div className="text-[10px] text-primary/60">win rate</div>
              </div>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="flex justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          )}

          {/* No Data State */}
          {!loading && report && (report.status === 'NO_DATA' || !report.stocks?.length) && (
            <div className="text-center py-12 text-muted-foreground">
              <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No scan snapshots found for today</p>
              <p className="text-xs mt-1">Run a swing scan first — snapshots are captured automatically</p>
            </div>
          )}

          {/* Stock Cards */}
          {!loading && report?.stocks && report.stocks.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-bold tracking-widest uppercase text-muted-foreground px-1">
                {report.date} — {report.stocks.length} STOCKS TRACKED
              </div>
              {report.stocks.map((stock) => (
                <div
                  key={stock.symbol}
                  className={`rounded-lg border ${getPerformanceBg(stock.performance_tag)} transition-all duration-200`}
                >
                  {/* Main Row */}
                  <div
                    className="flex items-center justify-between p-4 cursor-pointer hover:opacity-80"
                    onClick={() => setExpandedStock(expandedStock === stock.symbol ? null : stock.symbol)}
                  >
                    <div className="flex items-center gap-4">
                      {/* Rank Badge */}
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-black ${
                        stock.rank <= 3 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
                      }`}>
                        {stock.rank}
                      </div>
                      
                      {/* Symbol & Strategy */}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-black text-sm">{stock.symbol.replace('.NS', '')}</span>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold tracking-wider ${
                            stock.strategy === 'BREAKOUT' ? 'bg-blue-500/10 text-blue-500' : 'bg-purple-500/10 text-purple-500'
                          }`}>
                            {stock.strategy}
                          </span>
                          <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold tracking-wider ${
                            stock.signal === 'BUY_STRONG' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-amber-500/10 text-amber-500'
                          }`}>
                            {stock.signal}
                          </span>
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">
                          {stock.name} • {stock.sector}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-6">
                      {/* Score */}
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">SCORE</div>
                        <div className="font-black text-sm">{stock.score}</div>
                      </div>

                      {/* Entry Price */}
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">ENTRY</div>
                        <div className="font-mono text-sm">₹{stock.entry_price?.toFixed(2)}</div>
                      </div>

                      {/* EOD Price & Change */}
                      <div className="text-center min-w-[80px]">
                        <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">EOD</div>
                        {stock.is_tracked ? (
                          <div className="flex items-center justify-center gap-1">
                            {getChangeIcon(stock.eod_change_pct)}
                            <span className={`font-black text-sm ${
                              (stock.eod_change_pct ?? 0) >= 0 ? 'text-emerald-500' : 'text-red-500'
                            }`}>
                              {(stock.eod_change_pct ?? 0) >= 0 ? '+' : ''}{stock.eod_change_pct?.toFixed(2)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground/50">Pending</span>
                        )}
                      </div>

                      {/* Performance Tag */}
                      <div className="text-center min-w-[70px]">
                        {stock.performance_tag ? (
                          <span className={`text-[10px] font-black tracking-widest px-2 py-1 rounded ${getPerformanceColor(stock.performance_tag)}`}>
                            {stock.performance_tag === 'TRAP' && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                            {stock.performance_tag}
                          </span>
                        ) : (
                          <span className="text-[10px] text-muted-foreground/40">—</span>
                        )}
                      </div>

                      {/* Expand Arrow */}
                      {expandedStock === stock.symbol ? (
                        <ChevronUp className="w-4 h-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-muted-foreground" />
                      )}
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {expandedStock === stock.symbol && (
                    <div className="px-4 pb-4 pt-0 border-t border-border/50 animate-in fade-in slide-in-from-top-1 duration-200">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
                        <div className="bg-muted/50 rounded-md p-2.5">
                          <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">STOP LOSS</div>
                          <div className="font-mono text-xs font-bold mt-0.5">₹{stock.stop_loss?.toFixed(2) || 'N/A'}</div>
                        </div>
                        <div className="bg-muted/50 rounded-md p-2.5">
                          <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">TARGET</div>
                          <div className="font-mono text-xs font-bold mt-0.5">₹{stock.target?.toFixed(2) || 'N/A'}</div>
                        </div>
                        <div className="bg-muted/50 rounded-md p-2.5">
                          <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">VOL RATIO</div>
                          <div className="font-mono text-xs font-bold mt-0.5">{stock.vol_ratio?.toFixed(1) || 'N/A'}x</div>
                        </div>
                        <div className="bg-muted/50 rounded-md p-2.5">
                          <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">DELIVERY %</div>
                          <div className="font-mono text-xs font-bold mt-0.5">{stock.delivery_pct?.toFixed(1) || 'N/A'}%</div>
                        </div>
                      </div>

                      {/* Reasons Breakdown */}
                      {stock.reasons && stock.reasons.length > 0 && (
                        <div className="mt-3">
                          <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground mb-2">SCORING REASONS</div>
                          <div className="flex flex-wrap gap-1.5">
                            {stock.reasons.map((reason: any, idx: number) => (
                              <span
                                key={idx}
                                className={`text-[10px] px-2 py-1 rounded-md font-medium border ${
                                  reason.type === 'positive'
                                    ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-600'
                                    : 'bg-red-500/5 border-red-500/20 text-red-500'
                                }`}
                              >
                                {reason.type === 'positive' ? '+' : ''}{reason.impact} {reason.text}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      ) : activeView === 'history' ? (
        /* History View */
        <div className="space-y-3">
          {history.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No historical data yet</p>
              <p className="text-xs mt-1">Performance data will appear here after scans are tracked</p>
            </div>
          ) : (
            <>
              <div className="text-[10px] font-bold tracking-widest uppercase text-muted-foreground px-1">
                LAST {history.length} SCAN DAYS
              </div>
              <div className="grid gap-2">
                {history.map((entry) => (
                  <div
                    key={entry.date}
                    className="rounded-lg border border-border bg-card p-4 flex items-center justify-between cursor-pointer hover:border-primary/30 transition-colors"
                    onClick={() => { setSelectedDate(entry.date); setActiveView('today'); fetchReport(entry.date); }}
                  >
                    <div>
                      <div className="font-bold text-sm">{entry.date}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {entry.total_tracked} stocks tracked
                      </div>
                    </div>
                    <div className="flex items-center gap-6">
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest text-emerald-600">WIN</div>
                        <div className="font-black text-emerald-500">{entry.winners}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest text-red-600">TRAP</div>
                        <div className="font-black text-red-500">{entry.traps}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest text-muted-foreground">AVG</div>
                        <div className={`font-black ${entry.avg_return_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                          {entry.avg_return_pct >= 0 ? '+' : ''}{entry.avg_return_pct}%
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest text-primary">ACC</div>
                        <div className="font-black text-primary">{entry.accuracy_pct}%</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        /* Brain View — Learned Trap Patterns */
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-lg">🧠</span>
              <div>
                <div className="text-sm font-black tracking-tight">TRAP MEMORY — AI BRAIN</div>
                <div className="text-[10px] text-muted-foreground">Patterns learned from past TRAP stocks. Auto-applied to future scans.</div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-black text-primary">{trapPatterns.length}</div>
              <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">PATTERNS STORED</div>
            </div>
          </div>

          {trapPatterns.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <span className="text-4xl block mb-3 opacity-30">🧠</span>
              <p className="font-medium">Brain is empty — no trap patterns learned yet</p>
              <p className="text-xs mt-1">Click UPDATE PRICES after market close to identify TRAPs. The brain auto-learns from them.</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {trapPatterns.map((pattern) => (
                <div
                  key={pattern.id}
                  className="rounded-lg border border-red-500/20 bg-red-500/5 p-4"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
                        <AlertTriangle className="w-5 h-5 text-red-500" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-black text-sm">{pattern.source_symbol.replace('.NS', '')}</span>
                          <span className="text-[9px] px-1.5 py-0.5 rounded font-bold tracking-wider bg-red-500/10 text-red-500">
                            {pattern.trap_type.replace('_', ' ')}
                          </span>
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">
                          Learned on {pattern.source_date} • Lost {pattern.loss_pct?.toFixed(1)}%
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">CONFIDENCE</div>
                        <div className="font-black text-sm text-amber-500">{pattern.confidence?.toFixed(1)}x</div>
                      </div>
                      <div className="text-center">
                        <div className="text-[9px] font-bold tracking-widest uppercase text-muted-foreground">BLOCKED</div>
                        <div className="font-black text-sm text-emerald-500">{pattern.match_count}</div>
                      </div>
                    </div>
                  </div>

                  {/* Indicator Fingerprint */}
                  {pattern.indicators && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      {Object.entries(pattern.indicators).map(([key, val]) => (
                        <span
                          key={key}
                          className="text-[10px] px-2 py-1 rounded-md font-mono bg-muted/50 border border-border text-muted-foreground"
                        >
                          {key}: {typeof val === 'number' ? val.toFixed(1) : val}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
