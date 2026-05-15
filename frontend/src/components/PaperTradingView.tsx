import { useEffect, useState } from 'react';
import { papertradeApi } from '../services/api';
import { Wallet, TrendingUp, TrendingDown, Clock, XCircle, RefreshCcw, Landmark, Activity, Calendar } from 'lucide-react';

interface Trade {
    id: string;
    symbol: string;
    qty: number;
    buy_price: number;
    sell_price: number;
    current_price?: number; // Live Price from API enrichment
    buy_time: string;
    sell_time: string;
    status: 'OPEN' | 'CLOSED';
    close_reason?: string;
}

interface DailyHistory {
    date: string;
    total_pnl: number;
    count: number;
    details: {
        symbol: string;
        buy_price: number;
        sell_price: number;
        pnl: number;
        pnl_percent: number;
        score: number;
        reason: string;
        time: string;
    }[];
}

export function PaperTradingView() {
    const [account, setAccount] = useState<any>(null);
    const [trades, setTrades] = useState<Trade[]>([]);
    const [dailyHistory, setDailyHistory] = useState<DailyHistory[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        // Only set loading on first fetch
        if (!account) setLoading(true);
        try {
            const [accRes, tradesRes, historyRes] = await Promise.all([
                papertradeApi.getAccount(),
                papertradeApi.getTrades(),
                papertradeApi.getDailyHistory()
            ]);
            setAccount(accRes.data);
            setTrades(tradesRes.data);
            setDailyHistory(historyRes.data);
        } catch (error) {
            console.error("Failed to fetch paper trading data", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        
        // Auto-Refresh Live P&L every 10 seconds for near-real-time prices
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, []);

    const handleCloseTrade = async (tradeId: string) => {
        if (!confirm("Close this trade at current market price?")) return;
        try {
            await papertradeApi.closeTrade(tradeId);
            fetchData();
        } catch (error) {
            alert("Failed to close trade");
        }
    };

    const handleReset = async () => {
        if (!confirm("Reset virtual balance to 10 Lakhs and clear P&L?")) return;
        try {
            await papertradeApi.resetAccount();
            fetchData();
        } catch (error) {
            alert("Reset failed");
        }
    };

    if (loading && !account) {
        return <div className="flex justify-center py-20"><RefreshCcw className="animate-spin text-primary" /></div>;
    }

    const openTrades = trades.filter(t => t.status === 'OPEN');
    
    // Calculate REAL TOTAL P&L (Realized + Unrealized)
    const unrealizedPnl = openTrades.reduce((sum, t) => {
        const currentPrice = t.current_price || t.buy_price;
        return sum + (currentPrice - t.buy_price) * t.qty;
    }, 0);
    
    const totalPnl = (account?.total_pnl || 0) + unrealizedPnl;

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Account Summary Header */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex items-center gap-4 hover:border-primary/20 transition-colors">
                    <div className="p-4 bg-primary/10 rounded-2xl">
                        <Wallet className="text-primary h-8 w-8" />
                    </div>
                    <div>
                        <p className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Virtual Balance</p>
                        <h2 className="text-3xl font-black font-mono">₹{account?.balance?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</h2>
                    </div>
                </div>

                <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex items-center gap-4 hover:border-primary/20 transition-colors">
                    <div className={`p-4 rounded-2xl ${totalPnl >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                        {totalPnl >= 0 ? <TrendingUp className="text-emerald-500 h-8 w-8" /> : <TrendingDown className="text-red-500 h-8 w-8" />}
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                             <p className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Total P&L</p>
                             <span className="text-[9px] font-black bg-muted-foreground/10 text-muted-foreground px-1.5 py-0.5 rounded animate-pulse">LIVE</span>
                        </div>
                        <h2 className={`text-3xl font-black font-mono ${totalPnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {totalPnl >= 0 ? '+' : ''}₹{totalPnl?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                        </h2>
                    </div>
                </div>

                <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col justify-center gap-2">
                    <button 
                        onClick={handleReset}
                        className="flex items-center justify-center gap-2 w-full py-3 rounded-xl border border-destructive/30 text-destructive font-black uppercase text-xs hover:bg-destructive/5 transition-colors"
                    >
                        <RefreshCcw size={14} /> Reset Virtual Money
                    </button>
                    <p className="text-[10px] text-center text-muted-foreground font-bold tracking-tight px-4">Starting Capital: ₹10,00,000</p>
                </div>
            </div>

            {/* Active Trades */}
            <div className="space-y-4">
                <div className="flex items-center gap-2">
                    <Activity className="text-primary h-5 w-5" />
                    <h2 className="text-xl font-black tracking-tight uppercase">Active Positions ({openTrades.length})</h2>
                    {openTrades.length > 0 && <span className="text-[10px] font-bold text-emerald-500 flex items-center gap-1 ml-2"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Live · 10s</span>}
                </div>

                {openTrades.length === 0 ? (
                    <div className="bg-muted/30 border border-dashed border-border rounded-2xl py-12 text-center">
                        <p className="text-muted-foreground font-medium text-xs">No active positions. Execute a trade from the Intraday Scanner.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {openTrades.map(trade => {
                            const currentPrice = trade.current_price || trade.buy_price;
                            const tradePnl = (currentPrice - trade.buy_price) * trade.qty;
                            const pnlPercent = ((currentPrice - trade.buy_price) / trade.buy_price) * 100;
                            
                            return (
                                <div key={trade.id} className="bg-card border border-border border-l-4 border-l-primary rounded-xl p-4 shadow-sm hover:shadow-md transition-all group overflow-hidden relative">
                                    <div className="flex justify-between items-start mb-3 relative z-10">
                                        <div>
                                            <h3 className="text-lg font-black text-slate-800 leading-tight">{trade.symbol}</h3>
                                            <p className="text-[10px] font-bold text-muted-foreground flex items-center gap-1 opacity-70">
                                                <Clock size={10} /> {new Date(trade.buy_time.endsWith('Z') ? trade.buy_time : trade.buy_time + 'Z').toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })}
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <span className={`text-sm font-black font-mono ${tradePnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                                {tradePnl >= 0 ? '+' : ''}₹{tradePnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                                            </span>
                                            <p className={`text-[10px] font-black ${tradePnl >= 0 ? 'text-emerald-500' : 'text-red-500'} opacity-80`}>
                                                {tradePnl >= 0 ? '▲' : '▼'} {Math.abs(pnlPercent).toFixed(2)}%
                                            </p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-2 bg-muted/20 p-2 rounded-lg border border-slate-100/50 mb-4 font-mono relative z-10 text-[11px]">
                                        <div>
                                            <p className="text-[8px] font-bold text-muted-foreground uppercase">Buy Price</p>
                                            <p className="font-bold">₹{trade.buy_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-[8px] font-bold text-emerald-500 uppercase tracking-tighter animate-pulse">Live Price</p>
                                            <p className="font-black text-emerald-600">₹{currentPrice.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</p>
                                        </div>
                                    </div>

                                    <button 
                                        onClick={() => handleCloseTrade(trade.id)}
                                        className="w-full py-2 bg-red-500 text-white rounded-lg font-black uppercase text-[10px] hover:bg-red-600 shadow-sm shadow-red-100 transition-all flex items-center justify-center gap-2 relative z-10"
                                    >
                                        <XCircle size={14} /> Square Off
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Date-Wise Trade History */}
            {dailyHistory.length > 0 && (
                <div className="pt-6 border-t border-border space-y-8">
                    <div className="flex items-center gap-2 mb-4">
                        <Landmark className="text-muted-foreground h-5 w-5" />
                        <h2 className="text-xl font-black tracking-tight text-muted-foreground uppercase">Date-Wise Performance History</h2>
                    </div>

                    {dailyHistory.map(day => (
                        <div key={day.date} className="space-y-3">
                            <div className="flex items-center justify-between bg-muted/30 px-4 py-2 rounded-xl border border-border/50">
                                <div className="flex items-center gap-2">
                                    <Calendar className="h-4 w-4 text-primary/60" />
                                    <span className="text-sm font-black text-slate-700">{new Date(day.date).toLocaleDateString('en-IN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</span>
                                    <span className="text-[10px] font-bold bg-muted-foreground/10 text-muted-foreground px-2 py-0.5 rounded-full">{day.count} Trades</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Day P&L:</span>
                                    <span className={`text-sm font-black font-mono ${day.total_pnl >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                        {day.total_pnl >= 0 ? '+' : ''}₹{day.total_pnl.toLocaleString('en-IN')}
                                    </span>
                                </div>
                            </div>

                            <div className="overflow-hidden border border-border rounded-2xl shadow-sm overflow-x-auto">
                                <table className="w-full text-left border-collapse bg-card min-w-[800px]">
                                    <thead className="bg-muted/50 text-muted-foreground text-[10px] font-black uppercase tracking-widest">
                                        <tr>
                                            <th className="p-4 border-b border-border">Symbol / Time</th>
                                            <th className="p-4 border-b border-border">Reason</th>
                                            <th className="p-4 border-b border-border text-center">Score</th>
                                            <th className="p-4 border-b border-border text-right">Buy Price</th>
                                            <th className="p-4 border-b border-border text-right">Sell Price</th>
                                            <th className="p-4 border-b border-border text-right">P&L (%)</th>
                                            <th className="p-4 border-b border-border text-right">Net P&L</th>
                                        </tr>
                                    </thead>
                                    <tbody className="text-sm font-medium">
                                        {day.details.map((detail, idx) => (
                                            <tr key={`${day.date}-${detail.symbol}-${idx}`} className="hover:bg-muted/10 transition-colors">
                                                <td className="p-4 border-b border-border">
                                                    <p className="font-black text-slate-700">{detail.symbol}</p>
                                                    <p className="text-[9px] font-bold text-muted-foreground uppercase">{detail.time}</p>
                                                </td>
                                                <td className="p-4 border-b border-border">
                                                    <span className={`text-[10px] font-black px-2 py-0.5 rounded uppercase tracking-tighter
                                                        ${detail.reason === 'STOP_LOSS' ? 'bg-red-100 text-red-600' : 
                                                          detail.reason === 'TARGET' ? 'bg-emerald-100 text-emerald-600' : 
                                                          detail.reason === 'EOD' ? 'bg-amber-100 text-amber-600' : 
                                                          'bg-slate-100 text-slate-600'}`}>
                                                        {detail.reason || 'MANUAL'}
                                                    </span>
                                                </td>
                                                <td className="p-4 border-b border-border text-center">
                                                    <span className={`text-[10px] font-black px-2 py-0.5 rounded-full
                                                        ${detail.score >= 85 ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' : 
                                                          detail.score >= 75 ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20' : 
                                                          'bg-red-500/10 text-red-500 border border-red-500/20'}`}>
                                                        {detail.score}
                                                    </span>
                                                </td>
                                                <td className="p-4 border-b border-border text-right font-mono text-muted-foreground font-bold">
                                                    ₹{detail.buy_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                                </td>
                                                <td className="p-4 border-b border-border text-right font-mono text-slate-700 font-black">
                                                    ₹{detail.sell_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                                                </td>
                                                <td className={`p-4 border-b border-border text-right font-mono font-black ${detail.pnl_percent >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                                    {detail.pnl_percent >= 0 ? '+' : ''}{detail.pnl_percent.toFixed(2)}%
                                                </td>
                                                <td className={`p-4 border-b border-border text-right font-black font-mono ${detail.pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                                    {detail.pnl >= 0 ? '+' : ''}₹{detail.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
