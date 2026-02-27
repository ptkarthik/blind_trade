
import { AlertTriangle } from 'lucide-react';

export interface Indicator {
    text: string;
    type: "positive" | "negative";
    label: string;
    value: string;
}

export interface Signal {
    symbol: string;
    score: number;
    signal: "BUY" | "SELL" | "NEUTRAL";
    price: number;
    entry: number;
    target: number;
    stop_loss: number;
    name?: string;
    hold_duration?: string;
    target_reason?: string;
    strategic_summary?: string;
    category_rationale?: string;
    weights?: Record<string, number>;
    reasons: Indicator[];
    groups?: any;
    confidence?: number;
    reason?: string;
    support?: number;
    resistance?: number;
    market_cap_category?: "Large" | "Mid" | "Small";
    accumulation_status?: string;
    intrinsic_value?: number;
    valuation_gap?: number;
    squeeze?: { squeeze_on: boolean; label: string; firing: boolean };
    analysis_mode?: 'on-demand' | 'batch' | 'intraday';
    rationale?: string;
    confidence_label?: string;
    verdict?: string;
    // Paid App Features
    alpha_intel?: any;
    sector?: string;
    intraday_signal?: string;
    investment_advisory?: {
        holding_period: {
            play_type: string;
            label: string;
            period_display: string;
        };
        targets: {
            projected_cagr: number;
            business_cagr: number;
            blend_logic: string;
            "3_year_target"?: number;
        };
        entry_analysis?: {
            rationale: string;
            entry_price: number;
        };
        stop_loss?: {
            stop_price: number;
        };
    };
}

interface DealCardProps {
    signal: Signal;
    rank?: number;
    onClick: () => void;
}

export function DealCard({ signal, rank, onClick }: DealCardProps) {
    const isBuy = signal.signal === "BUY";
    const isNeutral = signal.signal === "NEUTRAL";
    const isHold = isNeutral;
    const isHighConviction = signal.score >= 75;
    const isIntraday = signal.analysis_mode === 'intraday';

    const baseColor = isBuy
        ? (isHighConviction ? "bg-emerald-900/[0.04] border-emerald-500/30 shadow-emerald-500/5" : "bg-emerald-50/20 border-emerald-200")
        : isNeutral
            ? "bg-amber-50/20 border-amber-200"
            : (isHighConviction ? "bg-red-900/[0.04] border-red-500/30 shadow-red-500/5" : "bg-red-50/20 border-red-200");

    const textColor = isBuy
        ? (isHighConviction ? "text-emerald-800" : "text-emerald-600")
        : isNeutral
            ? "text-amber-600"
            : (isHighConviction ? "text-red-800" : "text-red-600");

    const strengths = Array.isArray(signal.reasons) ? signal.reasons.filter(r => r.type === "positive") : [];
    const weaknesses = Array.isArray(signal.reasons) ? signal.reasons.filter(r => r.type === "negative") : [];

    // Default weights for Intraday vs Long-Term
    const weights = signal.weights || (isIntraday
        ? { "Trend": 30, "Momentum": 20, "Volume": 20, "Safety": 15, "Macro": 15 }
        : { "Fundamental": 50, "Technical": 30, "Risk": 20 });

    return (
        <div
            onClick={onClick}
            className={`relative border rounded-3xl p-5 shadow-sm transition-all cursor-pointer group hover:shadow-lg hover:-translate-y-0.5 ${baseColor} overflow-hidden`}
        >
            <div className="flex flex-col gap-5">
                {/* Decision Rationale Line */}
                {(signal.category_rationale || signal.rationale) && (
                    <div className={`mt-1 -mb-2 px-3 py-2 rounded-xl text-xs font-semibold flex items-start gap-2 border shadow-sm ${isNeutral ? 'bg-amber-100/50 text-amber-800 border-amber-200' :
                        isBuy ? 'bg-emerald-100/50 text-emerald-800 border-emerald-200' :
                            'bg-red-100/50 text-red-800 border-red-200'
                        }`}>
                        <div className="mt-0.5">
                            <AlertTriangle size={14} className={isNeutral ? 'text-amber-600' : isBuy ? 'text-emerald-600' : 'text-red-600'} />
                        </div>
                        <p>{signal.category_rationale || signal.rationale}</p>
                        {isIntraday && signal.confidence_label && (
                            <span className="ml-auto bg-white/40 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-tighter shadow-sm">{signal.confidence_label}</span>
                        )}
                    </div>
                )}

                {/* Identity, Score and Weights */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                    <div className="flex items-center gap-3">
                        {rank !== undefined && (
                            <div className={`flex items-center justify-center h-10 w-10 rounded-xl font-black text-lg ${isBuy ? 'bg-emerald-600 text-white' :
                                isNeutral ? 'bg-amber-500 text-white' :
                                    'bg-red-600 text-white'
                                }`}>
                                #{rank}
                            </div>
                        )}
                        <div>
                            <div className="flex items-center gap-2">
                                <h4 className="font-black text-xl tracking-tight uppercase">{signal.symbol}</h4>
                                {isIntraday && (
                                    <span className="text-[10px] bg-primary/10 text-primary px-2 py-0.5 rounded-full font-black tracking-widest uppercase">INTRA</span>
                                )}
                            </div>
                            <div className="flex gap-2 mt-0.5 flex-wrap">
                                <span className={`text-[9px] font-black px-1.5 py-0.5 rounded-md bg-white border border-slate-200 text-slate-500 uppercase tracking-tighter`}>
                                    SCORE: {signal.score}
                                </span>
                                {signal.market_cap_category && (
                                    <span className="text-[9px] font-black px-1.5 py-0.5 rounded-md bg-white border border-slate-200 text-slate-500 uppercase tracking-tighter">
                                        {signal.market_cap_category}
                                    </span>
                                )}
                                {signal.accumulation_status && (
                                    <span className={`text-[9px] font-black px-1.5 py-0.5 rounded-md bg-white border border-slate-200 uppercase tracking-tighter ${signal.accumulation_status.includes('High') ? 'text-emerald-500' : 'text-slate-500'}`}>
                                        {signal.accumulation_status}
                                    </span>
                                )}
                                {signal.squeeze?.firing && (
                                    <span className="text-[9px] font-black px-1.5 py-0.5 rounded-md bg-primary text-white border border-primary capitalize animate-bounce">
                                        🚀 BREAKOUT
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Impact Bars */}
                    <div className="flex flex-col items-end gap-1.5 w-full sm:w-auto">
                        <div className="flex gap-1 w-full sm:w-40 h-1.5 bg-slate-200/50 rounded-full overflow-hidden">
                            {Object.entries(weights).map(([key, val]) => {
                                const engineScore = isIntraday ? signal.score : (signal.groups?.[key]?.score || 50);
                                const impactColor = engineScore >= 70 ? 'bg-emerald-500' : engineScore >= 40 ? 'bg-orange-400' : 'bg-red-500';
                                return (
                                    <div
                                        key={key}
                                        style={{ width: `${(val as number)}%` }}
                                        className={`${impactColor} transition-all duration-700`}
                                        title={`${key}: ${val}% Weight`}
                                    />
                                );
                            })}
                        </div>
                        <div className="flex gap-3 text-[8px] font-black uppercase tracking-widest text-muted-foreground/50 italic mr-1">
                            {Object.entries(weights).slice(0, 3).map(([k, v]) => (
                                <span key={k}>{k.slice(0, 3)} {v}%</span>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Middle Section: Price Info */}
                <div className="flex flex-col md:flex-row gap-6 border-t border-b border-slate-200/40 py-5 mt-2">
                    <div className="flex-1 flex items-center justify-between px-2 sm:border-r border-slate-200/30">
                        <div className="flex flex-col text-left">
                            <span className="text-[10px] font-black text-slate-400 tracking-wider uppercase mb-1">{isIntraday ? 'ENTRY PRICE' : 'CURRENT (LTP)'}</span>
                            <span className="text-xl font-black tabular-nums tracking-tighter text-slate-400">₹{typeof signal.price === 'number' ? signal.price.toLocaleString() : 'N/A'}</span>
                        </div>
                        <div className="h-10 w-px bg-slate-200/40 mx-4 hidden sm:block" />
                        <div className="flex flex-col text-right pr-4">
                            <span className="text-[10px] font-black text-primary tracking-wider uppercase mb-1 flex items-center justify-end gap-1">
                                <div className="h-1.5 w-1.5 rounded-full bg-primary" /> {isIntraday ? 'VIRTUAL SL' : 'SMART ENTRY'}
                            </span>
                            <span className={`text-3xl font-black tabular-nums tracking-tighter ${textColor} drop-shadow-sm`}>
                                ₹{(isIntraday ? signal.stop_loss : signal.entry)?.toLocaleString() ?? 'N/A'}
                            </span>
                        </div>
                    </div>

                    <div className="flex flex-col justify-center px-4 border-l border-slate-200/30 hidden xl:flex">
                        <div className="flex flex-col">
                            <span className="text-[9px] font-black text-emerald-600/70 uppercase mb-0.5">{isIntraday ? 'INTRADAY TARGET' : '3Y TARGET & ROI:'}</span>
                            <div className="flex items-baseline gap-1.5">
                                <span className="text-emerald-700 font-bold text-sm">₹{typeof signal.target === 'number' ? signal.target.toLocaleString() : 'N/A'}</span>
                                {(!isIntraday && signal.investment_advisory?.targets?.projected_cagr) && (
                                    <span className="text-[10px] font-black text-emerald-500">
                                        (+{signal.investment_advisory.targets.projected_cagr}%)
                                    </span>
                                )}
                            </div>
                        </div>
                        <div className="h-px w-10 bg-slate-200 my-1" />
                        <div className="flex items-center gap-2">
                            <span className={`text-[9px] font-black ${isIntraday ? 'text-primary' : 'text-red-600/70'} uppercase`}>{isIntraday ? 'RR RATIO:' : 'STOP:'}</span>
                            <span className={`font-bold text-sm ${isIntraday ? 'text-primary' : 'text-red-700'}`}>
                                {isIntraday ? '1:1.5' : `₹${signal.stop_loss?.toLocaleString()}`}
                            </span>
                        </div>
                    </div>

                    <div className="flex-[1.5] grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                            <span className="text-[9px] font-black text-emerald-600/80 tracking-widest uppercase flex items-center gap-1">
                                <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> BULLISH DRIVERS
                            </span>
                            <div className="space-y-1">
                                {strengths.slice(0, 3).map((r, i) => (
                                    <div key={i} className="flex items-start justify-between text-[10px] p-1.5 rounded-lg border bg-emerald-500/5 border-emerald-100/30 leading-tight">
                                        <span className="font-bold text-slate-700 mr-2">{r.text}</span>
                                        <span className="font-black text-emerald-600 shrink-0">{r.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="space-y-1.5">
                            <span className="text-[9px] font-black text-red-600/80 tracking-widest uppercase flex items-center gap-1">
                                <div className="h-1.5 w-1.5 rounded-full bg-red-500" /> RISK FACTORS
                            </span>
                            <div className="space-y-1">
                                {weaknesses.slice(0, 3).map((r, i) => (
                                    <div key={i} className="flex items-start justify-between text-[10px] p-1.5 rounded-lg bg-red-500/[0.03] border border-red-100/30 leading-tight">
                                        <span className="font-bold text-slate-700 mr-2">{r.text}</span>
                                        <span className="font-black text-red-600 shrink-0">{r.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Strategy Summary Verdict */}
                <div className="flex flex-col gap-2">
                    <div className={`flex items-center gap-2.5 px-3 py-1.5 rounded-xl border border-dashed ${isBuy ? 'bg-emerald-500/[0.02] border-emerald-200/50' : isHold ? 'bg-amber-500/[0.02] border-amber-200/50' : 'bg-red-500/[0.02] border-red-200/50'}`}>
                        <div className={`h-1.5 w-1.5 rounded-full ${isBuy ? 'bg-emerald-500' : isNeutral ? 'bg-amber-500' : 'bg-red-500'} animate-pulse`} />
                        <span className={`text-[10px] font-bold italic ${textColor}/90 leading-tight`}>
                            {signal.verdict || signal.strategic_summary || "Strategic alignment confirmed by multi-engine sweep."}
                        </span>
                    </div>
                </div>

                <div className="flex items-center gap-1.5 mt-2">
                    <button className={`px-4 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest shadow-sm transition-all text-white ${isBuy ? 'bg-emerald-600 hover:bg-emerald-700' :
                        isNeutral ? 'bg-amber-500 hover:bg-amber-600' :
                            'bg-red-600 hover:bg-red-700'
                        }`}>
                        {isIntraday ? 'View Day Setup' : 'View Deep Report'}
                    </button>
                    {signal.analysis_mode === 'on-demand' && (
                        <span className="text-[9px] font-bold text-primary bg-primary/10 px-2 py-1 rounded-md ml-auto">
                            REAL-TIME ANALYSIS
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}
