
import type { Signal } from './DealCard';
import { TrendingUp, ShieldCheck, Activity, Clock } from 'lucide-react';

interface StockCardLongTermProps {
    signal: Signal;
    rank?: number;
    onClick: () => void;
}

export function StockCardLongTerm({ signal, rank, onClick }: StockCardLongTermProps) {
    if (!signal) return null;

    const isBuy = signal.signal === "BUY";

    // --- COLOR THEME (Professional & Clean) ---
    const baseColor = isBuy
        ? "bg-white border-emerald-100 hover:border-emerald-300 shadow-sm hover:shadow-emerald-100/50"
        : "bg-white border-slate-200 hover:border-slate-300 shadow-sm";

    // Paid App Feature Extraction - Defensive
    const alphaIntel = signal.alpha_intel || {};
    // Cast to any to avoid TS errors with empty object fallback
    const advisory = signal.investment_advisory || {} as any;
    const holding = advisory.holding_period || {};

    // Robust extraction for reasons
    const safeReasons = Array.isArray(signal.reasons) ? signal.reasons : [];

    // Safely extract RS Rating
    const rsReason = safeReasons.find(r => r && typeof r.text === 'string' && r.text.includes("RS"));
    const rsRating = rsReason?.value ? String(rsReason.value).replace("RS ", "") : "N/A";

    // Safely extract VCP
    const isVCP = safeReasons.some(r => r && typeof r.text === 'string' && r.text.includes("VCP"));

    // Safely extract Sponsorship
    const instReason = safeReasons.find(r => r?.label === "INSTITUTIONAL");
    const sponsorship = instReason?.value || "Neutral";

    // Value Formatting Helpers
    const formatPrice = (p: any) => typeof p === 'number' && !isNaN(p) ? `₹${p.toLocaleString()}` : '₹---';

    return (
        <div
            onClick={onClick}
            className={`relative border rounded-2xl p-4 transition-all duration-300 cursor-pointer group hover:-translate-y-1 ${baseColor}`}
        >
            {/* --- HEADER: Identity & Badges --- */}
            <div className="flex justify-between items-start mb-4">
                <div className="flex items-center gap-3">
                    {rank !== undefined && (
                        <div className={`flex items-center justify-center w-8 h-8 rounded-lg font-bold text-sm ${isBuy ? 'bg-emerald-600 text-white' : 'bg-slate-600 text-white'}`}>
                            #{rank}
                        </div>
                    )}
                    <div>
                        <h3 className="text-lg font-black tracking-tight text-slate-800">{signal.symbol}</h3>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                                {String(signal.market_cap_category || '---')} • {String(signal.sector || '---')}
                            </span>
                        </div>
                    </div>
                </div>

                {/* PAID APP BADGES */}
                <div className="flex flex-col items-end gap-1">
                    <div className="flex gap-1">
                        {rsRating !== "N/A" && (
                            <span className="text-[10px] font-black px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-100" title="Relative Strength Rating (0-99)">
                                RS {rsRating}
                            </span>
                        )}
                        {isVCP && (
                            <span className="text-[10px] font-black px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-100 animate-pulse">
                                💎 VCP
                            </span>
                        )}
                    </div>
                    {sponsorship !== "Neutral" && (
                        <span className="text-[9px] font-bold text-slate-500 flex items-center gap-1">
                            <Activity size={10} /> Inst. {String(sponsorship)}
                        </span>
                    )}
                </div>
            </div>

            {/* --- MAIN METRICS GRID (Investment Grade) --- */}
            <div className="grid grid-cols-3 gap-4 py-4 border-t border-slate-100">
                {/* 1. Price & Target */}
                <div className="space-y-1">
                    <p className="text-[10px] uppercase font-bold text-slate-400">Current Price</p>
                    <p className="text-xl font-black text-slate-700">
                        {formatPrice(signal.price)}
                    </p>
                    {typeof signal.target === 'number' && (
                        <div className="flex items-center gap-1 mt-1">
                            <TrendingUp size={12} className="text-emerald-500" />
                            <span className="text-xs font-bold text-emerald-600">
                                Target: {formatPrice(signal.target)}
                            </span>
                        </div>
                    )}
                </div>

                {/* 2. Quality & Value */}
                <div className="space-y-1 border-l border-slate-100 pl-4">
                    <p className="text-[10px] uppercase font-bold text-slate-400">Fundamentals</p>
                    <div className="flex flex-col gap-1">
                        <div className="flex justify-between text-xs">
                            <span className="text-slate-500">Quality</span>
                            <span className="font-bold text-slate-700">{alphaIntel.quality_score || 'N/A'}/100</span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-slate-500">Valuation</span>
                            <span className={`font-bold ${typeof alphaIntel.valuation_status === 'string' && alphaIntel.valuation_status.includes("Attractive") ? "text-emerald-600" : "text-amber-600"}`}>
                                {String(alphaIntel.valuation_status || "---")}
                            </span>
                        </div>
                    </div>
                </div>

                {/* 3. Strategic Horizon */}
                <div className="space-y-1 border-l border-slate-100 pl-4">
                    <p className="text-[10px] uppercase font-bold text-slate-400">Horizon</p>
                    <div className="flex items-center gap-1.5 mt-1">
                        <Clock size={14} className="text-slate-400" />
                        <span className="text-xs font-bold text-slate-700">
                            {holding.period_display || "3-5 Years"}
                        </span>
                    </div>
                    {holding.play_type && (
                        <span className="inline-block mt-1 text-[9px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 uppercase">
                            {String(holding.play_type)}
                        </span>
                    )}
                </div>
            </div>

            {/* --- STRATEGIC VERDICT (The "One Liner") --- */}
            <div className={`mt-2 p-3 rounded-xl border-l-4 ${isBuy ? "bg-emerald-50/50 border-emerald-500" : "bg-slate-50 border-slate-400"}`}>
                <p className="text-xs font-medium text-slate-700 leading-relaxed italic">
                    "{String(signal.strategic_summary || signal.verdict || '---')}"
                </p>
            </div>

            {/* --- FOOTER: Actions --- */}
            <div className="mt-4 flex items-center justify-between">
                <div className="flex gap-2">
                    {/* Dynamic Tags */}
                    {alphaIntel.moat_status === "Wide" && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-100 flex items-center gap-1">
                            <ShieldCheck size={10} /> Wide Moat
                        </span>
                    )}
                    {signal.score > 80 && (
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-100">
                            High Conviction
                        </span>
                    )}
                </div>

                <button className={`text-xs font-bold px-4 py-2 rounded-lg text-white shadow-sm hover:shadow-md transition-all ${isBuy ? "bg-emerald-600 hover:bg-emerald-700" : "bg-slate-600 hover:bg-slate-700"}`}>
                    Analysis Report
                </button>
            </div>
        </div>
    );
}
