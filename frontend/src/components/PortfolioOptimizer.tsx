
import { useState, useEffect } from 'react';
import { signalApi } from '../services/api';
import { ShieldCheck, Info, PieChart, Activity, Layers, AlertCircle } from 'lucide-react';

export function PortfolioOptimizer() {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const fetchPortfolio = async () => {
            setLoading(true);
            try {
                const res = await signalApi.getPortfolioAnalysis();
                setData(res.data);
            } catch (e) {
                console.error("Failed to fetch portfolio analysis", e);
            } finally {
                setLoading(false);
            }
        };
        fetchPortfolio();
    }, []);

    if (loading) return (
        <div className="flex flex-col items-center justify-center p-20 text-muted-foreground animate-pulse">
            <Activity className="h-10 w-10 animate-spin text-primary mb-4" />
            <p className="font-bold">Analyzing Correlation Matrix...</p>
        </div>
    );

    if (!data || data.message) return (
        <div className="p-12 border border-dashed rounded-3xl text-center text-muted-foreground">
            <AlertCircle className="h-10 w-10 mx-auto mb-4 opacity-20" />
            <p className="font-medium">{data?.message || "No high-conviction signals found to optimize."}</p>
        </div>
    );

    return (
        <div className="space-y-8 animate-in fade-in duration-700">
            {/* Header / Stats Overlay */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-primary/5 border border-primary/10 rounded-2xl p-6 relative overflow-hidden">
                    <div className="text-[10px] font-black uppercase tracking-widest text-primary opacity-60 mb-1">Diversification Score</div>
                    <div className="text-4xl font-black text-primary">{data.diversification_score}<span className="text-sm opacity-50">/100</span></div>
                    <ShieldCheck className="absolute -bottom-2 -right-2 h-16 w-16 text-primary/10 -rotate-12" />
                </div>

                <div className="col-span-1 md:col-span-3 bg-card border border-border rounded-2xl p-6 flex items-center gap-6">
                    <div className="h-12 w-12 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-600">
                        <PieChart className="h-6 w-6" />
                    </div>
                    <div>
                        <div className="text-[10px] font-black uppercase tracking-widest text-muted-foreground opacity-60">Portfolio Concentration</div>
                        <div className="flex gap-2 mt-1">
                            {Object.entries(data.sector_spread || {}).map(([sector, count]: [string, any]) => (
                                <div key={sector} className="px-3 py-1 bg-muted rounded-lg text-[10px] font-bold border border-border">
                                    {sector}: {count}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Correlation Matrix */}
                <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
                    <h3 className="text-sm font-black uppercase tracking-widest flex items-center gap-2 mb-6">
                        <Layers className="h-4 w-4 text-primary" />
                        Correlation Heatmap
                    </h3>
                    <div className="overflow-x-auto">
                        <table className="w-full text-[10px] border-collapse">
                            <thead>
                                <tr>
                                    <th className="p-2 border border-border bg-muted/50"></th>
                                    {Object.keys(data.correlation_matrix || {}).map(sym => (
                                        <th key={sym} className="p-2 border border-border font-black text-slate-700 bg-muted/50">{sym}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {Object.entries(data.correlation_matrix || {}).map(([rowSym, cols]: [string, any]) => (
                                    <tr key={rowSym}>
                                        <td className="p-2 border border-border font-black text-slate-700 bg-muted/20 text-center">{rowSym}</td>
                                        {Object.entries(cols).map(([colSym, val]: [string, any]) => {
                                            const v = parseFloat(val);
                                            const color = v > 0.8 ? 'bg-red-500/80 text-white' :
                                                v > 0.5 ? 'bg-amber-500/40' :
                                                    v < 0 ? 'bg-emerald-500/40' : '';
                                            return (
                                                <td key={colSym} className={`p-2 border border-border text-center font-mono ${color}`}>
                                                    {v === 1 ? '1.0' : v}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div className="mt-4 flex items-center gap-2 text-[10px] text-muted-foreground italic bg-muted/30 p-2 rounded-lg">
                        <Info className="h-3 w-3" />
                        <span>Values {'>'} 0.7 indicate high correlation. Avoid buying strongly correlated stocks to reduce group risk.</span>
                    </div>
                </div>

                {/* Risk Allocation Guider */}
                <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
                    <h3 className="text-sm font-black uppercase tracking-widest flex items-center gap-2 mb-6">
                        <ShieldCheck className="h-4 w-4 text-emerald-600" />
                        Risk Allocation Guide
                    </h3>
                    <div className="space-y-4">
                        {Object.entries(data.risk_allocations || {}).map(([sym, weight]: [string, any]) => (
                            <div key={sym} className="flex items-center justify-between p-4 bg-muted/10 rounded-xl border border-border group hover:border-primary/30 transition-all">
                                <div className="flex items-center gap-4">
                                    <div className="text-sm font-black tracking-tight">{sym}</div>
                                    <div className="text-[10px] bg-slate-100 px-2 py-0.5 rounded font-bold text-slate-500 border border-slate-200 uppercase">Weight Limit</div>
                                </div>
                                <div className="flex items-center gap-3">
                                    <div className="h-2 w-32 bg-slate-100 rounded-full overflow-hidden">
                                        <div className="h-full bg-emerald-500" style={{ width: weight }} />
                                    </div>
                                    <div className="text-sm font-black text-emerald-600 tabular-nums">{weight}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="mt-8 p-4 bg-emerald-500/[0.03] border border-dashed border-emerald-200 rounded-xl">
                        <p className="text-xs text-emerald-800 leading-relaxed font-medium">
                            <span className="font-black underline mr-1">STRATEGY:</span>
                            Allocations are adjusted for individual stock "Alpha Hubs" and historical volatility.
                            Never allocate more than <span className="font-black">20%</span> to a single cluster of correlated symbols.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
