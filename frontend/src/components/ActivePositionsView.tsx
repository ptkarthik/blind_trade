import React, { useState, useEffect } from 'react';
import { positionsApi } from '../services/api';
import { AlertCircle, CheckCircle2, TrendingUp, Clock, RefreshCw, XCircle, Activity } from 'lucide-react';
import { AnalysisModal } from './AnalysisModal';

export const ActivePositionsView: React.FC = () => {
    const [positions, setPositions] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [evaluating, setEvaluating] = useState(false);
    const [selectedScan, setSelectedScan] = useState<any>(null);

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
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {positions.map((pos) => (
                        <div key={pos.id} className="bg-card border border-border rounded-xl p-5 hover:border-primary/30 transition-colors group relative overflow-hidden">
                            {pos.action === 'SELL' && (
                                <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/10 rounded-bl-full -z-10 group-hover:scale-110 transition-transform" />
                            )}
                            
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <h3 className="text-xl font-black text-foreground">{pos.symbol.replace('.NS', '')}</h3>
                                    <div className="flex gap-2 mt-1">
                                        <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground">
                                            {pos.strategy}
                                        </span>
                                        <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                                            AI SCORE: {pos.initial_score} ➡️ {pos.current_score}
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
                                        <div className="text-xs text-muted-foreground">PnL</div>
                                    </div>
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
                                    <div className="font-mono text-sm text-red-400">₹{pos.stop_loss.toFixed(2)}</div>
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
                                <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase font-bold tracking-wider">
                                    <Clock size={12} /> Held for {pos.holding_days} days
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
                    ))}
                </div>
            )}

            {/* Live Scan Modal */}
            {selectedScan && (
                <AnalysisModal 
                    isOpen={!!selectedScan} 
                    onClose={() => setSelectedScan(null)} 
                    signal={selectedScan} 
                />
            )}
        </div>
    );
};
