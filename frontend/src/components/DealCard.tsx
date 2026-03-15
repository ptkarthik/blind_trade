
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
    setup_tag?: string;
    chase?: { is_chasing: boolean; distance_atr: number };
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

    // Specialist Tag Parser
    const parseSetupTags = (setupStr: string) => {
        if (!setupStr) return [];
        const matches = setupStr.match(/\[(.*?)\]/g);
        return matches ? matches.map(m => m.slice(1, -1)) : [];
    };

    const setupTags = parseSetupTags(signal.setup_tag || "");

    // Default weights for Intraday vs Long-Term
    const weights = signal.weights || (isIntraday
        ? { "Trend": 30, "Momentum": 20, "Volume": 20, "Safety": 15, "Macro": 15 }
        : { "Fundamental": 50, "Technical": 30, "Risk": 20 });

    return (
        <div
            onClick={onClick}
            className={`relative border rounded-3xl p-5 shadow-sm transition-all duration-500 cursor-pointer group hover:shadow-2xl hover:-translate-y-2 hover:border-primary/20 ${baseColor} overflow-hidden`}
        >
            <div className="flex flex-col gap-5">
                {/* Decision Rationale Line */}
                {(signal.category_rationale || signal.rationale) && (
                    <div className={`mt-1 -mb-2 px-3 py-2 rounded-xl text-xs font-semibold flex items-start gap-2 border shadow-sm transition-all group-hover:bg-opacity-100 ${isNeutral ? 'bg-amber-100/50 text-amber-800 border-amber-200' :
                        isBuy ? 'bg-emerald-100/50 text-emerald-800 border-emerald-200' :
                            'bg-red-100/50 text-red-800 border-red-200'
                        }`}>
                        <div className="mt-0.5">
                            <AlertTriangle size={14} className={isNeutral ? 'text-amber-600' : isBuy ? 'text-emerald-600' : 'text-red-600'} />
                        </div>
                        <p className="line-clamp-2">{signal.category_rationale || signal.rationale}</p>
                        {isIntraday && signal.confidence_label && (
                            <span className="ml-auto bg-white/40 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-tighter shadow-sm">{signal.confidence_label}</span>
                        )}
                    </div>
                )}

                {/* Identity, Score and Weights */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                    <div className="flex items-center gap-3">
                        {rank !== undefined && (
                            <div className={`flex items-center justify-center h-10 w-10 rounded-xl font-black text-lg shadow-sm transition-transform duration-500 group-hover:rotate-3 ${isBuy ? 'bg-emerald-600 text-white shadow-emerald-200' :
                                isNeutral ? 'bg-amber-500 text-white shadow-amber-200' :
                                    'bg-red-600 text-white shadow-red-200'
                                }`}>
                                #{rank}
                            </div>
                        )}
                        <div>
                            <div className="flex items-center gap-2">
                                <h4 className="font-black text-xl tracking-tight uppercase group-hover:text-primary transition-colors">{signal.symbol}</h4>
                                {isIntraday && (
                                    <span className="text-[10px] bg-primary/10 text-primary px-2 py-0.5 rounded-full font-black tracking-widest uppercase">INTRA</span>
                                )}
                            </div>
                            <div className="flex gap-2 mt-0.5 flex-wrap">
                                <span className={`text-[9px] font-black px-1.5 py-0.5 rounded-md bg-white border border-slate-200 text-slate-500 uppercase tracking-tighter shadow-sm`}>
                                    SCORE: {typeof signal.score === 'number' ? signal.score.toFixed(0) : signal.score}
                                </span>
                                {signal.market_cap_category && (
                                    <span className="text-[9px] font-black px-1.5 py-0.5 rounded-md bg-white border border-slate-200 text-slate-500 uppercase tracking-tighter shadow-sm">
                                        {signal.market_cap_category}
                                    </span>
                                )}
                                {signal.hold_duration && !isIntraday && (
                                    <span className="text-[9px] font-black px-1.5 py-0.5 rounded-md bg-amber-50 border border-amber-200 text-amber-700 uppercase tracking-tight flex items-center gap-1 shadow-sm">
                                        ⏱ {signal.hold_duration}
                                    </span>
                                )}
                                {signal.accumulation_status && (
                                    <span className={`text-[9px] font-black px-1.5 py-0.5 rounded-md bg-white border border-slate-200 uppercase tracking-tighter shadow-sm ${signal.accumulation_status.includes('High') ? 'text-emerald-500' : 'text-slate-500'}`}>
                                        {signal.accumulation_status}
                                    </span>
                                )}
                                {setupTags.map((tag, i) => (
                                    <span key={i} className={`text-[9px] font-black px-1.5 py-0.5 rounded-md border tracking-tighter shadow-sm ${tag.includes('💎') ? 'bg-primary text-white border-primary' : 'bg-white border-slate-200 text-slate-500'}`}>
                                        {tag}
                                    </span>
                                ))}
                                {signal.chase?.is_chasing && (
                                    <span className="text-[9px] font-black px-1.5 py-0.5 rounded-md bg-red-500 text-white border border-red-600 animate-pulse shadow-sm">
                                        🚨 CHASE
                                    </span>
                                )}
                                {signal.squeeze?.firing && (
                                    <span className="text-[9px] font-black px-1.5 py-0.5 rounded-md bg-primary text-white border border-primary capitalize animate-bounce shadow-md">
                                        🚀 BREAKOUT
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Impact Bars */}
                    <div className="flex flex-col items-end gap-1.5 w-full sm:w-auto">
                        <div className="flex gap-1 w-full sm:w-40 h-2 bg-slate-200/50 rounded-full overflow-hidden shadow-inner border border-slate-100">
                            {Object.entries(weights).map(([key, val]) => {
                                const engineScore = isIntraday ? signal.score : (signal.groups?.[key]?.score || 50);
                                const impactColor = engineScore >= 70 ? 'bg-emerald-500' : engineScore >= 40 ? 'bg-orange-400' : 'bg-red-500';
                                return (
                                    <div
                                        key={key}
                                        style={{ width: `${(val as number)}%` }}
                                        className={`${impactColor} transition-all duration-700 border-r border-white/20 last:border-none`}
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
                <div className="border-t border-b border-slate-200/40 py-4 mt-2 mb-2 bg-white/30 backdrop-blur-[2px] rounded-2xl">
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 px-4">
                        {/* Current (LTP) */}
                        <div className="flex flex-col text-left">
                            <span className="text-[10px] font-black text-slate-400 tracking-wider uppercase mb-1">LTP</span>
                            <span className="text-xl font-black tabular-nums tracking-tighter text-slate-500">
                                ₹{typeof signal.price === 'number' ? signal.price.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : 'N/A'}
                            </span>
                        </div>

                        {/* Smart Entry */}
                        <div className="flex flex-col text-left">
                            <span className="text-[10px] font-black text-slate-400 tracking-wider uppercase mb-1">SMART ENTRY</span>
                            <span className="text-xl font-black tabular-nums tracking-tighter text-slate-500">
                                ₹{typeof signal.entry === 'number' ? signal.entry.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : 'N/A'}
                            </span>
                        </div>

                        {/* Stop Loss (or Virtual SL for Intraday) */}
                        <div className="flex flex-col text-left lg:border-l lg:border-slate-200/30 lg:pl-4">
                            <span className="text-[10px] font-black text-primary tracking-wider uppercase mb-1 flex items-center gap-1">
                                <div className="h-1.5 w-1.5 rounded-full bg-primary" /> {isIntraday ? 'VIRTUAL SL' : 'STOP LOSS'}
                            </span>
                            <span className={`text-xl font-black tabular-nums tracking-tighter text-red-600 drop-shadow-sm`}>
                                {typeof signal.stop_loss === 'number' ? `₹${signal.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : 'N/A'}
                            </span>
                        </div>

                        {/* Target */}
                        <div className="flex flex-col text-left">
                            <span className="text-[10px] font-black text-emerald-600/70 tracking-wider uppercase mb-1 flex items-center gap-1">
                                <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> TARGET
                            </span>
                            <div className="flex items-baseline gap-1.5">
                                <span className="text-xl font-black tabular-nums tracking-tighter text-emerald-600 drop-shadow-sm">
                                    ₹{typeof signal.target === 'number' ? signal.target.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : 'N/A'}
                                </span>
                                {(!isIntraday && signal.investment_advisory?.targets?.projected_cagr) && (
                                    <span className="text-[10px] font-black text-emerald-500 hidden sm:inline-block">
                                        (+{signal.investment_advisory.targets.projected_cagr}%)
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                <div className="flex-[1.5] grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                        <span className="text-[9px] font-black text-emerald-600/80 tracking-widest uppercase flex items-center gap-1">
                            <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> BULLISH DRIVERS
                        </span>
                        <div className="space-y-1">
                            {strengths.slice(0, 3).map((r, i) => (
                                <div key={i} className="flex items-start justify-between text-[10px] p-2 rounded-xl border bg-emerald-500/[0.03] border-emerald-100/30 leading-tight group-hover:bg-white/60 transition-colors">
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
                                <div key={i} className="flex items-start justify-between text-[10px] p-2 rounded-xl bg-red-500/[0.03] border border-red-100/30 leading-tight group-hover:bg-white/60 transition-colors">
                                    <span className="font-bold text-slate-700 mr-2">{r.text}</span>
                                    <span className="font-black text-red-600 shrink-0">{r.value}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Strategy Summary Verdict */}
            <div className="flex flex-col gap-2 mt-2">
                <div className={`flex items-center gap-2.5 px-4 py-2 rounded-2xl border border-dashed transition-all group-hover:border-solid ${isBuy ? 'bg-emerald-500/[0.02] border-emerald-200/50 group-hover:bg-emerald-50' : isHold ? 'bg-amber-500/[0.02] border-amber-200/50 group-hover:bg-amber-50' : 'bg-red-500/[0.02] border-red-200/50 group-hover:bg-red-50'}`}>
                    <div className={`h-2 w-2 rounded-full ${isBuy ? 'bg-emerald-500' : isNeutral ? 'bg-amber-500' : 'bg-red-500'} animate-pulse`} />
                    <span className={`text-[10px] font-bold italic ${textColor}/90 leading-tight`}>
                        {signal.strategic_summary || signal.verdict || "Strategic alignment confirmed by multi-engine sweep."}
                    </span>
                </div>
            </div>

            <div className="flex items-center gap-1.5 mt-3">
                <button className={`px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest shadow-sm transition-all duration-300 transform group-hover:scale-105 text-white ${isBuy ? 'bg-emerald-600 hover:bg-emerald-700 shadow-emerald-100' :
                    isNeutral ? 'bg-amber-500 hover:bg-amber-600 shadow-amber-100' :
                        'bg-red-600 hover:bg-red-700 shadow-red-100'
                    }`}>
                    {isIntraday ? 'View Day Setup' : 'View Deep Report'}
                </button>
                {signal.analysis_mode === 'on-demand' && (
                    <span className="text-[9px] font-bold text-primary bg-primary/10 px-2 py-1.5 rounded-lg ml-auto shadow-sm">
                        REAL-TIME
                    </span>
                )}
            </div>
        </div>
    );
}
