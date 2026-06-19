import React, { useState, useEffect } from 'react';
import { positionsApi } from '../services/api';
import { AlertCircle, CheckCircle2, TrendingUp, Clock, RefreshCw, XCircle, Activity, Sparkles } from 'lucide-react';
import { AnalysisModal } from './AnalysisModal';

export const ActivePositionsView: React.FC = () => {
    const [positions, setPositions] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [evaluating, setEvaluating] = useState(false);
    const [selectedScan, setSelectedScan] = useState<any>(null);
    // Unused: const [hoveredPosId, setHoveredPosId] = useState<string | null>(null);

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
            setLoading(true);
            const res = await positionsApi.getPortfolio();
            setPositions(res.data || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadPositions();
        const interval = setInterval(loadPositions, 60000); // refresh every minute
        return () => clearInterval(interval);
    }, []);

    const handleEvaluateNow = async () => {
        try {
            setEvaluating(true);
            await positionsApi.triggerEvaluation();
            // The backend now fully waits for the deep scan to finish before returning.
            await loadPositions();
            setEvaluating(false);
        } catch (e) {
            console.error(e);
            setEvaluating(false);
        }
    };

    if (loading && positions.length === 0) {
        return <div className="flex justify-center p-12"><div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" /></div>;
    }

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

            {positions.length === 0 ? (
                <div className="bg-card border border-border rounded-xl p-12 text-center">
                    <AlertCircle size={48} className="mx-auto text-muted-foreground/50 mb-4" />
                    <h3 className="text-lg font-bold text-foreground">No Active Positions</h3>
                    <p className="text-muted-foreground">Trades marked as 'OPEN' will automatically appear here for monitoring.</p>
                </div>
            ) : (
                <div className="space-y-8">
                    {Object.entries(
                        positions.reduce((groups, pos) => {
                            const date = new Date(pos.created_at || pos.entry_date || Date.now()).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
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
                                    const maxProfit = pos.scan_data?.max_profit_pct || 0;
                                    const lockPct = pos.stop_loss > pos.entry ? ((pos.stop_loss - pos.entry) / pos.entry) * 100 : 0;
                                    
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
                                                    </div>
                                                </div>
                                                <div className="text-right flex flex-col items-end gap-2">
                                                    <button 
                                                        onClick={async () => {
                                                            if(window.confirm(`Are you sure you want to close tracking for ${pos.symbol}?`)) {
                                                                await positionsApi.closeTrade(pos.id);
                                                                loadPositions();
                                                            }
                                                        }}
                                                        className="text-xs text-muted-foreground hover:text-red-500 flex items-center gap-1 transition-colors bg-background px-2 py-1 rounded-md border border-border/50 hover:border-red-500/30"
                                                    >
                                                        <XCircle size={14} /> Close
                                                    </button>
                                                    <div>
                                                        <div className={`text-2xl font-black tracking-tighter ${pos.profit_pct >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                                            {pos.profit_pct >= 0 ? '+' : ''}{pos.profit_pct}%
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
                                                                {(pos.volume_health || 'N/A').split(':')[0]}
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
