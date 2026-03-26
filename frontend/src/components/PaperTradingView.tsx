import { useEffect, useState } from 'react';
import { papertradeApi } from '../services/api';
import { Wallet, TrendingUp, TrendingDown, Clock, XCircle, RefreshCcw, Landmark, Activity } from 'lucide-react';

interface Trade {
    id: string;
    symbol: string;
    qty: number;
    buy_price: number;
    sell_price: number;
    buy_time: string;
    sell_time: string;
    status: 'OPEN' | 'CLOSED';
}

export function PaperTradingView() {
    const [account, setAccount] = useState<any>(null);
    const [trades, setTrades] = useState<Trade[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [accRes, tradesRes] = await Promise.all([
                papertradeApi.getAccount(),
                papertradeApi.getTrades()
            ]);
            setAccount(accRes.data);
            setTrades(tradesRes.data);
        } catch (error) {
            console.error("Failed to fetch paper trading data", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
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
    const closedTrades = trades.filter(t => t.status === 'CLOSED');

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Account Summary Header */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex items-center gap-4">
                    <div className="p-4 bg-primary/10 rounded-2xl">
                        <Wallet className="text-primary h-8 w-8" />
                    </div>
                    <div>
                        <p className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Virtual Balance</p>
                        <h2 className="text-3xl font-black font-mono">₹{account?.balance?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</h2>
                    </div>
                </div>

                <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex items-center gap-4">
                    <div className={`p-4 rounded-2xl ${(account?.total_pnl || 0) >= 0 ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                        {(account?.total_pnl || 0) >= 0 ? <TrendingUp className="text-emerald-500 h-8 w-8" /> : <TrendingDown className="text-red-500 h-8 w-8" />}
                    </div>
                    <div>
                        <p className="text-sm font-bold text-muted-foreground uppercase tracking-wider">Total P&L</p>
                        <h2 className={`text-3xl font-black font-mono ${(account?.total_pnl || 0) >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                            {account?.total_pnl >= 0 ? '+' : ''}₹{account?.total_pnl?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
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
                    <h2 className="text-xl font-black tracking-tight">ACTIVE POSITIONS ({openTrades.length})</h2>
                </div>

                {openTrades.length === 0 ? (
                    <div className="bg-muted/30 border border-dashed border-border rounded-2xl py-12 text-center">
                        <p className="text-muted-foreground font-medium">No active positions. Execute a trade from the Intraday Scanner.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {openTrades.map(trade => (
                            <div key={trade.id} className="bg-card border border-border border-l-4 border-l-primary rounded-xl p-4 shadow-sm hover:shadow-md transition-all group">
                                <div className="flex justify-between items-start mb-3">
                                    <div>
                                        <h3 className="text-lg font-black text-slate-800">{trade.symbol}</h3>
                                        <p className="text-[10px] font-bold text-muted-foreground flex items-center gap-1">
                                            <Clock size={10} /> {new Date(trade.buy_time).toLocaleTimeString()}
                                        </p>
                                    </div>
                                    <div className="text-right">
                                        <span className="text-[10px] font-black bg-primary/10 text-primary px-2 py-0.5 rounded uppercase tracking-widest">
                                            QTY: {trade.qty}
                                        </span>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-4 bg-muted/20 p-3 rounded-lg border border-slate-100 mb-4 font-mono">
                                    <div>
                                        <p className="text-[9px] font-bold text-muted-foreground uppercase">Buy Price</p>
                                        <p className="text-sm font-bold">₹{trade.buy_price.toLocaleString('en-IN')}</p>
                                    </div>
                                    <div>
                                        <p className="text-[9px] font-bold text-muted-foreground uppercase text-primary">Invested</p>
                                        <p className="text-sm font-bold text-primary">₹{(trade.qty * trade.buy_price).toLocaleString('en-IN')}</p>
                                    </div>
                                </div>

                                <button 
                                    onClick={() => handleCloseTrade(trade.id)}
                                    className="w-full py-2.5 bg-red-500 text-white rounded-lg font-black uppercase text-xs hover:bg-red-600 shadow-sm shadow-red-100 transition-all flex items-center justify-center gap-2"
                                >
                                    <XCircle size={14} /> Square Off (Exit)
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Trade History */}
            {closedTrades.length > 0 && (
                <div className="pt-6 border-t border-border">
                    <div className="flex items-center gap-2 mb-4">
                        <Landmark className="text-muted-foreground h-5 w-5" />
                        <h2 className="text-xl font-black tracking-tight text-muted-foreground">TRADE HISTORY</h2>
                    </div>

                    <div className="overflow-hidden border border-border rounded-2xl shadow-sm">
                        <table className="w-full text-left border-collapse bg-card">
                            <thead className="bg-muted/50 text-muted-foreground text-[10px] font-black uppercase tracking-widest">
                                <tr>
                                    <th className="p-4 border-b border-border">Symbol</th>
                                    <th className="p-4 border-b border-border">Qty</th>
                                    <th className="p-4 border-b border-border">Buy</th>
                                    <th className="p-4 border-b border-border">Sell</th>
                                    <th className="p-4 border-b border-border text-right">Net P&L</th>
                                </tr>
                            </thead>
                            <tbody className="text-sm font-medium">
                                {closedTrades.map(trade => {
                                    const pnl = (trade.sell_price - trade.buy_price) * trade.qty;
                                    return (
                                        <tr key={trade.id} className="hover:bg-muted/20 transition-colors">
                                            <td className="p-4 border-b border-border font-black text-slate-700">{trade.symbol}</td>
                                            <td className="p-4 border-b border-border font-mono">{trade.qty}</td>
                                            <td className="p-4 border-b border-border font-mono text-slate-500 text-xs">₹{trade.buy_price.toLocaleString('en-IN')}</td>
                                            <td className="p-4 border-b border-border font-mono text-slate-500 text-xs">₹{trade.sell_price.toLocaleString('en-IN')}</td>
                                            <td className={`p-4 border-b border-border text-right font-black font-mono ${pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                                {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
