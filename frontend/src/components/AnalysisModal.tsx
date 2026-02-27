import { useState, useEffect } from 'react';
import { X, Activity, Loader2 } from 'lucide-react';
import { InvestmentAnalysis } from './InvestmentAnalysis';

interface AnalysisModalProps {
    isOpen: boolean;
    onClose: () => void;
    data: any; // Signal Data
}

export function AnalysisModal({ isOpen, onClose, data }: AnalysisModalProps) {
    const [detailedData, setDetailedData] = useState<any>(null);
    const [isLoading] = useState(false);

    useEffect(() => {
        if (isOpen && data) {
            setDetailedData(data);
        }
    }, [data, isOpen]);

    if (!isOpen || !detailedData) return null;

    // Use detailedData for rendering
    const displayData = detailedData;

    // Check for Long Term Mode
    const isLongTerm = displayData.analysis_mode === 'LONGTERM_INVEST';

    // Split reasons into categories for better UI
    const safeReasons = Array.isArray(data.reasons) ? data.reasons : [];
    const bullishReasons = safeReasons.filter((r: any) => r.type === "positive");
    const bearishReasons = safeReasons.filter((r: any) => r.type === "negative");

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <div className={`bg-card w-full ${isLongTerm ? 'max-w-4xl' : 'max-w-2xl'} rounded-2xl shadow-2xl border border-border max-h-[90vh] overflow-y-auto transition-all`}>

                {/* Header */}
                <div className="flex justify-between items-center p-6 border-b border-border sticky top-0 bg-card z-10">
                    <div>
                        <h2 className="text-2xl font-black flex items-center gap-2 tracking-tight">
                            <Activity className="text-primary h-6 w-6" />
                            {displayData.symbol} <span className="text-muted-foreground font-light">Analysis</span>
                        </h2>
                        <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
                            <span className="font-medium">AI-Generated Strategy Report</span>
                            {(displayData.analysis_mode || displayData.is_ondemand) && (
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-black tracking-widest uppercase border ${isLongTerm ? 'bg-purple-500/10 text-purple-600 border-purple-500/20' : 'bg-primary/10 text-primary border-primary/20'}`}>
                                    {displayData.is_ondemand ? 'ON-DEMAND' : displayData.analysis_mode}
                                </span>
                            )}
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-muted rounded-full transition-colors">
                        <X className="h-6 w-6" />
                    </button>
                </div>

                {isLoading ? (
                    <div className="p-12 flex flex-col items-center justify-center text-muted-foreground animate-pulse">
                        <Loader2 className="h-10 w-10 animate-spin mb-4 text-purple-500" />
                        <p className="font-bold">Generating Deep Investment Report...</p>
                        <p className="text-xs opacity-70 mt-2">Fetching Fundamentals & Sentiment Analysis</p>
                    </div>
                ) : isLongTerm ? (
                    <div className="p-6">
                        <InvestmentAnalysis data={displayData} />
                    </div>
                ) : (
                    <>
                        {/* Score Hero Section */}
                        <div className="px-6 py-8 bg-gradient-to-b from-muted/30 to-transparent border-b border-border/50">
                            <div className="flex flex-col items-center gap-6">
                                <div className="text-center">
                                    <div className={`text-7xl font-black leading-tight tracking-tighter ${data.score >= 60 ? 'text-emerald-500' :
                                        data.score >= 40 ? 'text-amber-500' :
                                            'text-red-500'
                                        } drop-shadow-sm`}>
                                        {data.score}<span className="text-xl text-muted-foreground font-normal opacity-50">/100</span>
                                    </div>
                                    <div className="uppercase tracking-[0.3em] text-[10px] font-black text-muted-foreground opacity-60">AI Conviction Score</div>
                                </div>

                                {/* Strategic Verdict Summary */}
                                <div className={`max-w-xl w-full p-4 rounded-2xl border border-dashed flex items-center gap-4 transition-all duration-500 ${data.score >= 60 ? 'bg-emerald-500/[0.03] border-emerald-200' :
                                    data.score >= 40 ? 'bg-amber-500/[0.03] border-amber-200' :
                                        'bg-red-500/[0.03] border-red-200'
                                    }`}>
                                    <div className={`h-3 w-3 rounded-full shrink-0 ${data.score >= 60 ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]' :
                                        data.score >= 40 ? 'bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]' :
                                            'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]'
                                        } animate-pulse`} />
                                    <div className="flex flex-col">
                                        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground opacity-60">Strategic Verdict</span>
                                        <p className="text-sm font-bold text-slate-700 italic leading-tight">
                                            "{data.strategic_summary || "Multi-engine analysis confirms signal integrity based on current market pulse."}"
                                        </p>
                                    </div>
                                </div>

                                {/* Engine Impact Bars (Visual Transparency) */}
                                {data.weights && (
                                    <div className="w-full max-w-md space-y-2">
                                        <div className="flex justify-between text-[10px] font-black uppercase tracking-widest text-muted-foreground opacity-60">
                                            <span>Engine Contribution</span>
                                            <div className="flex gap-4">
                                                {data.weights && Object.entries(data.weights).map(([k, v]: [string, any]) => (
                                                    <span key={k}>{k.slice(0, 4)}: {v}%</span>
                                                ))}
                                            </div>
                                        </div>
                                        <div className="flex w-full h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200/50 shadow-inner">
                                            {data.weights && Object.entries(data.weights).map(([key, val]: [string, any]) => {
                                                const engineScore = data.groups?.[key]?.score || 50;
                                                const impactColor = engineScore >= 70 ? 'bg-emerald-500' : engineScore >= 40 ? 'bg-orange-400' : 'bg-red-500';
                                                return (
                                                    <div
                                                        key={key}
                                                        style={{ width: `${val}%` }}
                                                        className={`${impactColor} transition-all duration-1000 border-r border-white/20 last:border-none`}
                                                        title={`${key}: ${val}% Weight`}
                                                    />
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}

                                {/* --- INVESTMENT ADVISOR BLUEPRINT (Phase 40) --- */}
                                {data.investment_advisory && (
                                    <div className="w-full max-w-2xl mt-8 bg-white/50 backdrop-blur-sm border border-slate-200 shadow-xl shadow-slate-200/40 rounded-3xl overflow-hidden">

                                        {/* Advisory Header */}
                                        <div className="bg-slate-900 text-white p-5 flex justify-between items-center">
                                            <div>
                                                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-blue-400">Strategic Blueprint</div>
                                                <h3 className="text-lg font-bold italic">Investment Advisor</h3>
                                            </div>
                                            <div className="text-right">
                                                <div className="text-[9px] font-black uppercase text-slate-400 tracking-widest">Review Cycle</div>
                                                <div className="font-bold text-sm text-yellow-400">{data.investment_advisory.review_cycle}</div>
                                            </div>
                                        </div>

                                        {/* Core Metrics Grid */}
                                        {/* Core Metrics Grid */}
                                        <div className="grid grid-cols-3 divide-x divide-slate-100 border-b border-slate-100">
                                            <div className="p-4 text-center">
                                                <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Suggested Hold</div>
                                                <div className="text-lg font-black text-slate-800 tracking-tight">{data.investment_advisory.holding_period?.period_display || 'N/A'}</div>
                                                <div className="text-[10px] font-bold text-slate-500">{data.investment_advisory.holding_period?.label || 'Standard'}</div>
                                            </div>
                                            <div className="p-4 text-center bg-emerald-50/50">
                                                <div className="text-[9px] font-black text-emerald-600/60 uppercase tracking-widest mb-1">Target</div>
                                                <div className="text-lg font-black text-emerald-600 tracking-tight">₹{typeof data.investment_advisory.targets?.['3_year_target'] === 'number' ? data.investment_advisory.targets['3_year_target'].toLocaleString() : 'N/A'}</div>
                                                <div className="text-[10px] font-bold text-emerald-600/70">ROI: {data.investment_advisory.targets?.absolute_return || 0}%</div>
                                            </div>
                                            <div className="p-4 text-center bg-red-50/50">
                                                <div className="text-[9px] font-black text-red-600/60 uppercase tracking-widest mb-1">Smart Stop</div>
                                                <div className="text-lg font-black text-red-600 tracking-tight">₹{typeof data.investment_advisory.stop_loss?.stop_price === 'number' ? data.investment_advisory.stop_loss.stop_price.toLocaleString() : 'N/A'}</div>
                                                <div className="text-[10px] font-bold text-red-600/70">{data.investment_advisory.stop_loss?.type || 'Standard'}</div>
                                            </div>
                                        </div>

                                        {/* Scenarios Table */}
                                        <div className="p-5">
                                            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Scenario Projections</div>
                                            <div className="space-y-2">
                                                {data.investment_advisory.scenarios?.map((s: any, idx: number) => (
                                                    <div key={idx} className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 transition-colors">
                                                        <div className="flex items-center gap-3">
                                                            <div className={`h-2 w-2 rounded-full ${s.label === 'Aggressive' ? 'bg-purple-500' : s.label === 'Realistic' ? 'bg-blue-500' : 'bg-slate-400'}`} />
                                                            <span className="text-xs font-bold text-slate-700">{s.label}</span>
                                                        </div>
                                                        <div className="flex items-center gap-6">
                                                            <span className="text-xs font-medium text-slate-500">{s.cagr || 0}% ROI</span>
                                                            <div className="text-right w-24">
                                                                <div className="text-xs font-black text-slate-800">₹{typeof s.target === 'number' ? s.target.toLocaleString() : 'N/A'}</div>
                                                                <div className="text-[10px] font-bold text-emerald-500">
                                                                    {typeof s.target === 'number' && typeof displayData.price === 'number' && displayData.price !== 0
                                                                        ? `+${Math.round(((s.target - displayData.price) / displayData.price) * 100)}%`
                                                                        : ''}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* Absolute Valuation (Intrinsic Value / DCF) */}
                                {data.intrinsic_value > 0 && (
                                    <div className="w-full max-w-md mt-6 p-5 rounded-3xl bg-slate-900 text-white shadow-xl shadow-slate-200/50">
                                        <div className="flex justify-between items-start mb-4">
                                            <div>
                                                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">Absolute Valuation</span>
                                                <h4 className="text-sm font-bold mt-1 italic">DCF Model Estimates</h4>
                                            </div>
                                            <div className={`px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-tighter ${data.valuation_gap > 20 ? 'bg-emerald-500 text-white' : data.valuation_gap < -20 ? 'bg-red-500 text-white' : 'bg-slate-700 text-slate-300'}`}>
                                                {data.valuation_gap > 0 ? `${data.valuation_gap}% Undervalued` : `${Math.abs(data.valuation_gap)}% Overvalued`}
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-6 relative">
                                            <div className="flex flex-col">
                                                <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Intrinsic Worth</span>
                                                <span className="text-2xl font-black tracking-tighter text-emerald-400">₹{typeof data.intrinsic_value === 'number' ? data.intrinsic_value.toLocaleString() : 'N/A'}</span>
                                            </div>
                                            <div className="flex flex-col border-l border-slate-700 pl-6">
                                                <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Market Price</span>
                                                <span className="text-2xl font-black tracking-tighter text-slate-200 opacity-60">₹{typeof data.entry === 'number' ? data.entry.toLocaleString() : 'N/A'}</span>
                                            </div>

                                            {/* Scale Visualization */}
                                            <div className="col-span-2 mt-4 space-y-2">
                                                <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden relative">
                                                    <div
                                                        className={`absolute inset-y-0 left-0 transition-all duration-1000 ${data.valuation_gap > 0 ? 'bg-emerald-500' : 'bg-red-500'}`}
                                                        style={{ width: `${Math.min(100, Math.abs(data.valuation_gap) + 50)}%`, opacity: 0.6 }}
                                                    />
                                                    <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-white z-10" title="Fair Value Center" />
                                                </div>
                                                <div className="flex justify-between text-[8px] font-black text-slate-500 uppercase tracking-widest">
                                                    <span>Expensive</span>
                                                    <span>Fair Value</span>
                                                    <span>Bargain</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* Breakout Timing (Volatility Squeeze) */}
                                {data.squeeze && (data.squeeze.squeeze_on || data.squeeze.firing) && (
                                    <div className="w-full max-w-md mt-4 p-5 rounded-3xl bg-orange-500 text-white shadow-xl shadow-orange-200/50">
                                        <div className="flex justify-between items-start mb-4">
                                            <div>
                                                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-orange-100">Breakout Timing</span>
                                                <h4 className="text-sm font-bold mt-1 italic">Volatility Analysis</h4>
                                            </div>
                                            <div className="bg-white/20 px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-tighter">
                                                {data.squeeze.firing ? "🚀 Firing" : "⏳ Coiling"}
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-6">
                                            <div className="flex flex-col">
                                                <span className="text-[9px] font-black text-orange-100 uppercase tracking-widest">Compression</span>
                                                <span className="text-2xl font-black tracking-tighter">{data.squeeze.compression}%</span>
                                            </div>
                                            <div className="flex-1 space-y-2">
                                                <div className="h-1.5 w-full bg-white/20 rounded-full overflow-hidden">
                                                    <div
                                                        className="h-full bg-white transition-all duration-1000"
                                                        style={{ width: `${Math.max(20, 100 - data.squeeze.compression)}%` }}
                                                    />
                                                </div>
                                                <p className="text-[10px] font-medium leading-tight opacity-90">
                                                    {data.squeeze.squeeze_on
                                                        ? "Energy is building. A major directional move typically follows this compression."
                                                        : "Squeeze released. High-velocity move in progress."}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* Technical Ladder (Support & Resistance) */}
                                {data.levels && (data.levels.resistance?.length > 0 || data.levels.support?.length > 0) && (
                                    <div className="w-full max-w-xl bg-slate-50/50 p-6 rounded-3xl border border-slate-200/50 mt-4">
                                        <div className="flex items-center gap-2 mb-6">
                                            <div className="h-4 w-1 bg-primary rounded-full" />
                                            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground">Technical Ladder</span>
                                        </div>

                                        <div className="relative flex flex-col gap-3">
                                            {/* Resistance Levels */}
                                            <div className="space-y-2">
                                                {Array.isArray(data.levels?.resistance) && [...data.levels.resistance].reverse().map((lvl: any, idx: number) => (
                                                    <div key={`res-${idx}`} className="flex items-center justify-between group">
                                                        <div className="flex items-center gap-3">
                                                            <div className="w-12 text-[9px] font-black text-red-500/50 text-right uppercase tracking-tighter">Res {data.levels.resistance.length - idx}</div>
                                                            <div className="h-[1px] w-8 bg-gradient-to-r from-red-200/50 to-transparent" />
                                                            <span className="text-[10px] font-bold text-slate-500">{lvl.label}</span>
                                                        </div>
                                                        <div className="px-3 py-1 bg-red-50 border border-red-100/50 rounded-lg text-[11px] font-black text-red-600 tabular-nums shadow-sm group-hover:scale-105 transition-transform">
                                                            ₹{typeof lvl.price === 'number' ? lvl.price.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : 'N/A'}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>

                                            {/* Current Price Marker */}
                                            <div className="relative py-4 my-2">
                                                <div className="absolute inset-x-0 top-1/2 h-[2px] bg-gradient-to-r from-transparent via-primary/20 to-transparent -translate-y-1/2" />
                                                <div className="relative z-10 flex justify-center">
                                                    <div className="bg-primary text-white text-[10px] font-black px-6 py-1.5 rounded-full shadow-lg shadow-primary/20 flex items-center gap-2 border-2 border-white">
                                                        <div className="h-1.5 w-1.5 bg-white rounded-full animate-ping" />
                                                        CURRENT PRICE: ₹{typeof data.entry === 'number' ? data.entry.toLocaleString() : 'N/A'}
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Support Levels */}
                                            <div className="space-y-2">
                                                {Array.isArray(data.levels?.support) && data.levels.support.map((lvl: any, idx: number) => (
                                                    <div key={`sup-${idx}`} className="flex items-center justify-between group">
                                                        <div className="flex items-center gap-3">
                                                            <div className="w-12 text-[9px] font-black text-emerald-500/50 text-right uppercase tracking-tighter">Sup {idx + 1}</div>
                                                            <div className="h-[1px] w-8 bg-gradient-to-r from-emerald-200/50 to-transparent" />
                                                            <span className="text-[10px] font-bold text-slate-500">{lvl.label}</span>
                                                        </div>
                                                        <div className="px-3 py-1 bg-emerald-50 border border-emerald-100/50 rounded-lg text-[11px] font-black text-emerald-600 tabular-nums shadow-sm group-hover:scale-105 transition-transform">
                                                            ₹{typeof lvl.price === 'number' ? lvl.price.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : 'N/A'}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Split Breakdown: Bullish Drivers vs Risk Factors (Phase 14) */}
                        <div className="p-6 grid gap-8 md:grid-cols-2">
                            {/* Column 1: Bullish Drivers (Pros) */}
                            <div className="space-y-5">
                                <div className="flex items-center gap-2 border-b border-emerald-100 pb-2">
                                    <div className="h-4 w-1 bg-emerald-500 rounded-full" />
                                    <h3 className="font-black text-xs uppercase tracking-[0.2em] text-emerald-600">Bullish Drivers</h3>
                                </div>

                                <div className="space-y-3">
                                    {bullishReasons.length > 0 ? (
                                        bullishReasons.map((indicator: any, idx: number) => (
                                            <div key={idx} className="flex items-start justify-between p-4 rounded-2xl border border-emerald-100 bg-emerald-500/[0.02] hover:bg-emerald-500/[0.05] transition-all group">
                                                <div className="flex items-start gap-4">
                                                    <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] group-hover:scale-125 transition-transform mt-1.5" />
                                                    <div className="flex flex-col">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-sm font-bold text-slate-700">{indicator.text}</span>
                                                            {indicator.label && (
                                                                <span className="text-[8px] font-black px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200 uppercase tracking-tighter">
                                                                    {indicator.label}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <p className="text-[10px] text-muted-foreground font-medium opacity-60">Insight contribution identified by AI</p>
                                                    </div>
                                                </div>
                                                <div className="text-[11px] font-black px-2.5 py-1 rounded-lg bg-white shadow-sm border border-emerald-100 text-emerald-600 tabular-nums">
                                                    {indicator.value}
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="p-8 border border-dashed border-slate-200 rounded-3xl text-center">
                                            <p className="text-xs text-muted-foreground italic">No strong bullish drivers detected</p>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Column 2: Risk Factors (Cons) */}
                            <div className="space-y-5">
                                <div className="flex items-center gap-2 border-b border-red-100 pb-2">
                                    <div className="h-4 w-1 bg-red-500 rounded-full" />
                                    <h3 className="font-black text-xs uppercase tracking-[0.2em] text-red-600">Risk Factors</h3>
                                </div>

                                <div className="space-y-3">
                                    {bearishReasons.length > 0 ? (
                                        bearishReasons.map((indicator: any, idx: number) => (
                                            <div key={idx} className="flex items-start justify-between p-4 rounded-2xl border border-red-100 bg-red-500/[0.02] hover:bg-red-500/[0.05] transition-all group">
                                                <div className="flex items-start gap-4">
                                                    <div className="h-2 w-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)] group-hover:scale-125 transition-transform mt-1.5" />
                                                    <div className="flex flex-col">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-sm font-bold text-slate-700">{indicator.text}</span>
                                                            {indicator.label && (
                                                                <span className="text-[8px] font-black px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200 uppercase tracking-tighter">
                                                                    {indicator.label}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <p className="text-[10px] text-muted-foreground font-medium opacity-60">Potential volatility threat</p>
                                                    </div>
                                                </div>
                                                <div className="text-[11px] font-black px-2.5 py-1 rounded-lg bg-white shadow-sm border border-red-100 text-red-600 tabular-nums">
                                                    {indicator.value}
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="p-8 border border-dashed border-slate-200 rounded-3xl text-center">
                                            <p className="text-xs text-muted-foreground italic">No major risks identified in current cycle</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="p-6 border-t border-border bg-muted/20">
                            <p className="text-xs text-center text-muted-foreground">
                                Disclaimer: This report is generated by algorithms based on historical price data.
                                It does not constitute financial advice. Market risks apply.
                            </p>
                        </div>
                    </>
                )}

            </div>
        </div>
    );
}
