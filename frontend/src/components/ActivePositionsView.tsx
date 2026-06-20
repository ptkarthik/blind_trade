import React, { useState, useEffect } from 'react';
import { positionsApi, brokerApi, papertradeApi } from '../services/api';
import { AlertCircle, CheckCircle2, TrendingUp, Clock, RefreshCw, XCircle, Activity, Sparkles, Wallet } from 'lucide-react';
import { AnalysisModal } from './AnalysisModal';

interface ActivePositionsViewProps {
    mode: string;
}

export const ActivePositionsView: React.FC<ActivePositionsViewProps> = ({ mode }) => {
    const [realPositions, setRealPositions] = useState<any[]>([]);
    const [paperPositions, setPaperPositions] = useState<any[]>([]);
    const [account, setAccount] = useState<any>(null);
    const [margins, setMargins] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [evaluating, setEvaluating] = useState(false);
    const [activeTradeTab, setActiveTradeTab] = useState<'REAL' | 'PAPER'>('REAL');
    const [selectedScan, setSelectedScan] = useState<any>(null);

    const formatTimeAgo = (isoString?: string) => {
        if (!isoString) return 'never';
        const seconds = Math.floor((new Date().getTime() - new Date(isoString).getTime()) / 1000);
        if (seconds < 60) return `${seconds}s ago`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        return `${hours}h ago`;
    };

    const loadPositions = async () => {
        try {
            if (!account) setLoading(true);
            const [resReal, resPaper, accRes, marginRes] = await Promise.all([
                positionsApi.getPortfolio(),
                papertradeApi.getTrades(),
                papertradeApi.getAccount(),
                brokerApi.getMargins().catch(() => ({ data: { error: true } }))
            ]);
            setRealPositions(resReal.data || []);
            setPaperPositions(resPaper.data || []);
            setAccount(accRes.data);
            if (marginRes.data && !marginRes.data.error) {
                setMargins(marginRes.data);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadPositions();
        const interval = setInterval(loadPositions, 10000); // 10 second refresh like PaperTradingView
        return () => clearInterval(interval);
    }, []);

    const handleEvaluateNow = async () => {
        try {
            setEvaluating(true);
            await positionsApi.triggerEvaluation();
            await loadPositions();
            setEvaluating(false);
        } catch (e) {
            console.error(e);
            setEvaluating(false);
        }
    };

    if (loading && realPositions.length === 0 && paperPositions.length === 0) {
        return <div className="flex justify-center p-12"><div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" /></div>;
    }

    const filteredReal = realPositions.filter(p => (p.mode || 'swing') === mode && p.status === 'OPEN');
    const filteredPaper = paperPositions.filter(p => (p.mode || 'swing') === mode && p.status === 'OPEN');

    const activeList = activeTradeTab === 'REAL' ? filteredReal : filteredPaper;

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700 pb-12">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-black tracking-tight text-foreground flex items-center gap-3">
                        <span className="bg-primary/10 text-primary p-2 rounded-lg"><TrendingUp size={24} /></span>
                        Active Positions
                    </h2>
                    <p className="text-muted-foreground text-sm mt-1">Live 15-minute Guardian Loop Monitoring</p>
                </div>
                <button 
                    onClick={handleEvaluateNow}
                    disabled={evaluating}
                    className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 font-medium text-sm transition-colors"
                >
                    <RefreshCw size={16} className={evaluating ? "animate-spin" : ""} />
                    Evaluate Now
                </button>
            </div>

            {activeTradeTab === 'REAL' && margins && !margins.error && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Wallet className="w-8 h-8 text-red-500" />
                        <div>
                            <h3 className="text-sm font-bold text-red-500 tracking-wider uppercase">Live Kite Funding</h3>
                            <p className="text-2xl font-black text-foreground">₹{margins.available?.toLocaleString('en-IN')}</p>
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-xs text-muted-foreground uppercase tracking-widest font-bold">Used Margin</div>
                        <div className="text-sm font-bold text-foreground">₹{margins.used?.toLocaleString('en-IN')}</div>
                    </div>
                </div>
            )}

            {activeTradeTab === 'PAPER' && account && (
                <div className="bg-primary/10 border border-primary/20 rounded-xl p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Wallet className="w-8 h-8 text-primary" />
                        <div>
                            <h3 className="text-sm font-bold text-primary tracking-wider uppercase">Virtual Paper Balance</h3>
                            <p className="text-2xl font-black text-foreground">₹{account.balance?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</p>
                        </div>
                    </div>
                    <div className="text-right flex items-center gap-4">
                        <div>
                            <div className="text-xs text-muted-foreground uppercase tracking-widest font-bold">Total P&L</div>
                            <div className={`text-sm font-bold ${account.total_pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                {account.total_pnl >= 0 ? '+' : ''}₹{account.total_pnl?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                            </div>
                        </div>
                        <button 
                            onClick={async () => {
                                if(window.confirm('Reset Virtual Balance?')) {
                                    await papertradeApi.resetAccount();
                                    loadPositions();
                                }
                            }}
                            className="bg-card text-xs uppercase tracking-widest font-bold border border-border px-3 py-1.5 rounded-lg hover:bg-muted"
                        >
                            RESET
                        </button>
                    </div>
                </div>
            )}

            {/* Tabs for Real vs Paper */}
            <div className="flex bg-muted p-1 rounded-xl border border-border w-fit">
                <button
                    onClick={() => setActiveTradeTab('PAPER')}
                    className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTradeTab === 'PAPER' ? 'bg-card shadow-sm text-primary border border-primary/20' : 'text-muted-foreground hover:text-foreground'}`}
                >
                    PAPER TRADES
                </button>
                <button
                    onClick={() => setActiveTradeTab('REAL')}
                    className={`px-6 py-2 rounded-lg text-xs font-black tracking-widest uppercase flex items-center gap-2 transition-all ${activeTradeTab === 'REAL' ? 'bg-card shadow-sm text-red-500 border border-red-500/20' : 'text-muted-foreground hover:text-foreground'}`}
                >
                    LIVE REAL MONEY
                </button>
            </div>

            {activeList.length === 0 ? (
                <div className="bg-card border border-border rounded-xl p-12 text-center">
                    <AlertCircle size={48} className="mx-auto text-muted-foreground/50 mb-4" />
                    <h3 className="text-lg font-bold text-foreground">No Active {activeTradeTab} Positions</h3>
                    <p className="text-muted-foreground">Trades marked as 'OPEN' will automatically appear here for monitoring.</p>
                </div>
            ) : (
                <div className="space-y-8">
                    {Object.entries(
                        activeList.reduce((groups, pos) => {
                            const date = new Date(pos.created_at || pos.entry_date || pos.buy_time || Date.now()).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
                            if (!groups[date]) groups[date] = [];
                            groups[date].push(pos);
                            return groups;
                        }, {} as Record<string, any[]>)
                    )
                    .sort((a, b) => new Date(b[0]).getTime() - new Date(a[0]).getTime())
                    .map(([date, datePositions]: [string, any]) => (
                        <div key={date} className="space-y-4">
                            <h3 className="text-lg font-bold border-b border-border pb-2 text-primary flex items-center gap-2">
                                <Clock className="w-5 h-5" />
                                Entries on {date}
                                <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded-full ml-2">
                                    {datePositions.length} positions
                                </span>
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {datePositions.map((pos: any) => {
                                    // Abstract fields to handle both SwingTrade and PaperTrade
                                    const entryPrice = pos.entry || pos.buy_price || 0;
                                    const qty = pos.quantity || pos.qty || 0;
                                    const currentPrice = pos.current_price || entryPrice; // For PaperTrade we might not have live price here unless enriched, but Guardian updates highest_price_reached
                                    // Actually, positions API returns live PnL for Real trades. For Paper trades we might need to fetch LTP if not returned.
                                    const profitPct = pos.profit_pct || (entryPrice > 0 ? ((currentPrice - entryPrice) / entryPrice) * 100 : 0);
                                    
                                    const maxProfit = pos.scan_data?.max_profit_pct || 0;
                                    const lockPct = pos.stop_loss > entryPrice ? ((pos.stop_loss - entryPrice) / entryPrice) * 100 : 0;
                                    
                                    return (
                                        <div key={pos.id} className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 transition-colors group relative overflow-hidden">
                                            {pos.action === 'SELL' && (
                                                <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/10 rounded-bl-full -z-10 group-hover:scale-110 transition-transform" />
                                            )}
                                            
                                            <div className="flex justify-between items-start mb-4">
                                                <div>
                                                    <h3 className="text-xl font-black text-foreground">{pos.symbol.replace('.NS', '')}</h3>
                                                    <div className="flex flex-col gap-2 mt-1">
                                                        <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground w-fit">
                                                            {pos.strategy}
                                                        </span>
                                                        <span className={`text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full border w-fit ${pos.current_score >= 65 ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : pos.current_score < 45 ? 'bg-red-500/10 text-red-500 border-red-500/20' : 'bg-primary/10 text-primary border-primary/20'}`}>
                                                            RADAR SCORE: {pos.current_score}
                                                        </span>
                                                        {pos.scan_data?.spike_tracker_active && (
                                                            <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full border w-fit bg-orange-500/10 text-orange-500 border-orange-500/20 animate-pulse">
                                                                🔥 SPIKE TRAIL: {pos.scan_data.today_spike_pct}%
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                <div className="text-right flex flex-col items-end gap-2">
                                                    <button 
                                                        onClick={async () => {
                                                            if(window.confirm(`LIVE EXECUTION WARNING: Are you sure you want to place a LIVE MARKET SELL ORDER for ${qty} shares of ${pos.symbol} on Kite?`)) {
                                                                try {
                                                                    const orderRes = await brokerApi.placeOrder({
                                                                        symbol: pos.symbol,
                                                                        quantity: qty,
                                                                        transaction_type: "SELL",
                                                                        order_type: "MARKET"
                                                                    });
                                                                    if (orderRes.data.success) {
                                                                        alert(`Success! Order ID: ${orderRes.data.order_id}`);
                                                                        if (pos.trade_type === 'PAPER') {
                                                                            await papertradeApi.closeTrade(pos.id);
                                                                        } else {
                                                                            await positionsApi.closeTrade(pos.id);
                                                                        }
                                                                        loadPositions();
                                                                    } else {
                                                                        alert(`Order failed: ${orderRes.data.error}`);
                                                                    }
                                                                } catch(e: any) {
                                                                    alert(`API Error: ${e.response?.data?.detail || e.message}`);
                                                                }
                                                            }
                                                        }}
                                                        className="text-xs font-bold uppercase tracking-widest text-red-500 hover:text-white flex items-center gap-1 transition-colors bg-red-500/10 px-3 py-1.5 rounded-md border border-red-500/20 hover:bg-red-500"
                                                    >
                                                        <Activity size={14} /> Square Off
                                                    </button>
                                                    <div>
                                                        <div className={`text-2xl font-black tracking-tighter ${profitPct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                                            {profitPct >= 0 ? '+' : ''}{profitPct.toFixed(2)}%
                                                        </div>
                                                        <div className="text-xs text-muted-foreground">Live PnL</div>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Deviation Hover Tracker */}
                                            <div 
                                                className="absolute inset-0 bg-card/95 backdrop-blur-sm z-20 p-5 flex flex-col opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-300 border border-primary/20 rounded-xl"
                                            >
                                                <div className="flex items-center gap-2 mb-4 border-b border-border pb-2">
                                                    <Sparkles className="w-4 h-4 text-primary" />
                                                    <h4 className="text-sm font-black uppercase tracking-widest text-primary">Radar Analysis</h4>
                                                </div>
                                                
                                                <div className="space-y-4 flex-1">
                                                    <div className="grid grid-cols-2 gap-4">
                                                        <div className="bg-muted/50 p-3 rounded-lg border border-border">
                                                            <div className="text-[9px] uppercase tracking-widest text-muted-foreground font-bold mb-1">Max Reached</div>
                                                            <div className="text-xl font-black text-emerald-500">+{(pos.max_profit_pct || maxProfit).toFixed(1)}%</div>
                                                        </div>
                                                        <div className="bg-primary/5 p-3 rounded-lg border border-primary/20">
                                                            <div className="text-[9px] uppercase tracking-widest text-primary font-bold mb-1">Locked Profit</div>
                                                            <div className="text-xl font-black text-primary">+{Math.max(0, lockPct).toFixed(1)}%</div>
                                                        </div>
                                                    </div>
                                                    
                                                    <div className="grid grid-cols-3 gap-2">
                                                        <div className="bg-muted/30 p-2 rounded-lg border border-border/50 text-center">
                                                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground font-bold mb-1">Volume</div>
                                                            <div className={`text-[10px] font-bold ${(pos.volume_health || '').includes('Accumulation') ? 'text-emerald-500' : (pos.volume_health || '').includes('Distribution') || (pos.volume_health || '').includes('Panic') ? 'text-red-500' : 'text-muted-foreground'}`}>
                                                                {(pos.volume_health && pos.volume_health !== 'Volume data unavailable' ? pos.volume_health.split(':')[0] : 'UNAVAILABLE')}
                                                            </div>
                                                        </div>
                                                        <div className="bg-muted/30 p-2 rounded-lg border border-border/50 text-center">
                                                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground font-bold mb-1">Daily</div>
                                                            <div className={`text-[10px] font-bold ${pos.daily_trend === 'BULLISH' ? 'text-emerald-500' : pos.daily_trend === 'BEARISH' ? 'text-red-500' : 'text-amber-500'}`}>
                                                                {pos.daily_trend || 'N/A'}
                                                            </div>
                                                        </div>
                                                        <div className="bg-muted/30 p-2 rounded-lg border border-border/50 text-center">
                                                            <div className="text-[8px] uppercase tracking-widest text-muted-foreground font-bold mb-1">Nifty</div>
                                                            <div className={`text-[10px] font-bold ${pos.nifty_regime === 'BULLISH' ? 'text-emerald-500' : pos.nifty_regime === 'BEARISH' ? 'text-red-500' : 'text-muted-foreground'}`}>
                                                                {pos.nifty_regime || 'N/A'}
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div className="bg-background rounded-lg p-3 border border-border/50">
                                                        <div className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">Technical Shift</div>
                                                        <p className="text-xs font-medium text-foreground leading-relaxed">
                                                            {pos.initial_score > pos.current_score 
                                                                ? "⚠️ Technical structure has weakened since entry." 
                                                                : pos.initial_score < pos.current_score 
                                                                    ? "🔥 Setup has gained strength." 
                                                                    : "⚖️ Structure remains stable."}
                                                        </p>
                                                        {pos.scan_data?.strategic_summary && (
                                                            <div className="mt-2 text-[10px] text-muted-foreground">
                                                                {pos.scan_data.strategic_summary}
                                                            </div>
                                                        )}
                                                    </div>

                                                    {pos.dead_money && (
                                                        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-2 text-center">
                                                            <div className="text-[10px] font-bold text-amber-500">💤 DEAD MONEY - Consider Redeploying Capital</div>
                                                        </div>
                                                    )}

                                                    {pos.drawdown_from_peak > 2 && (
                                                        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-2 text-center">
                                                            <div className="text-[10px] font-bold text-red-500">📉 Drawdown from peak: -{pos.drawdown_from_peak.toFixed(1)}%</div>
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="text-[9px] text-right text-muted-foreground mt-2">
                                                    Last Evaluated: {formatTimeAgo(pos.last_evaluated_at)}
                                                </div>
                                            </div>

                                            <div className="grid grid-cols-3 gap-2 mb-4 bg-background/50 rounded-lg p-3 border border-border/50">
                                                <div>
                                                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Entry</div>
                                                    <div className="font-mono text-sm">₹{pos.entry.toFixed(2)}</div>
                                                </div>
                                                <div>
                                                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">LTP</div>
                                                    <div className="font-mono text-sm">₹{pos.current_price.toFixed(2)}</div>
                                                </div>
                                                <div>
                                                    <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Stop Loss</div>
                                                    <div className={`font-mono text-sm ${pos.stop_loss > pos.entry ? 'text-emerald-500 font-bold' : 'text-red-400'}`}>₹{pos.stop_loss.toFixed(2)}</div>
                                                </div>
                                            </div>

                                            <div className={`mt-4 p-4 rounded-lg border flex items-start gap-3 ${
                                                pos.action === 'SELL' ? 'bg-red-500/10 border-red-500/20' : 'bg-emerald-500/10 border-emerald-500/20'
                                            }`}>
                                                {pos.action === 'SELL' ? <XCircle className="text-red-500 shrink-0 mt-0.5" size={20} /> : <CheckCircle2 className="text-emerald-500 shrink-0 mt-0.5" size={20} />}
                                                <div>
                                                    <div className={`text-sm font-black tracking-widest uppercase mb-1 ${pos.action === 'SELL' ? 'text-red-500' : 'text-emerald-500'}`}>
                                                        {pos.action}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground leading-relaxed">
                                                        {pos.reason}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="mt-4 flex items-center justify-between">
                                                <div className="flex items-center gap-3">
                                                    <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase font-bold tracking-wider">
                                                        <Clock size={12} /> Held for {pos.holding_days} days
                                                        {pos.scan_data?.hold_duration && (
                                                            <span className="text-[9px] bg-primary/10 text-primary px-1.5 py-0.5 rounded ml-1 border border-primary/20 tracking-tighter">
                                                                EST: {pos.scan_data.hold_duration}
                                                            </span>
                                                        )}
                                                    </div>
                                                    {pos.last_evaluated_at && (
                                                        <div className="flex items-center gap-1.5 text-[9px] text-muted-foreground/60 uppercase font-bold tracking-wider">
                                                            <RefreshCw size={10} /> {formatTimeAgo(pos.last_evaluated_at)}
                                                        </div>
                                                    )}
                                                </div>
                                                {pos.scan_data && (
                                                    <button 
                                                        onClick={() => setSelectedScan(pos.scan_data)}
                                                        className="text-[10px] uppercase tracking-widest font-bold text-primary flex items-center gap-1 bg-primary/5 hover:bg-primary/10 px-3 py-1.5 rounded-lg transition-colors border border-primary/20"
                                                    >
                                                        <Activity size={14} /> View Live Scan
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Live Scan Modal */}
            {selectedScan && (
                <AnalysisModal 
                    isOpen={!!selectedScan} 
                    onClose={() => setSelectedScan(null)} 
                    data={selectedScan} 
                />
            )}
        </div>
    );
};
