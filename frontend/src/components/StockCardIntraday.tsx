
import type { Signal } from './DealCard';
import { Target, Zap, TrendingUp, BarChart2, Activity, ArrowRight } from 'lucide-react';

interface StockCardIntradayProps {
    signal: Signal;
    rank?: number;
    onClick: () => void;
}

export function StockCardIntraday({ signal, onClick }: StockCardIntradayProps) {
    const isBuy = signal.intraday_signal?.includes("BUY") || signal.signal === "BUY";
    const isHighConviction = signal.score >= 80;

    // --- COLOR THEME (High Contrast / Action Oriented) ---
    const baseColor = isBuy
        ? "bg-emerald-950/5 border-emerald-500/20 hover:border-emerald-500/50 shadow-sm"
        : "bg-red-950/5 border-red-500/20 hover:border-red-500/50 shadow-sm";

    const scoreColor = signal.score >= 80 ? "text-emerald-500" : signal.score >= 50 ? "text-amber-500" : "text-red-500";

    // Paid App Feature Extraction
    const instBias = signal.reasons?.find(r => r.label === "INSTITUTIONAL")?.value || "Neutral";
    const rsLeader = signal.verdict?.includes("LEADER RS");

    return (
        <div
            onClick={onClick}
            className={`relative border rounded-2xl p-4 transition-all duration-300 cursor-pointer group hover:-translate-y-1 ${baseColor} overflow-hidden`}
        >
            {/* Momentum Background Pulse (Subtle) */}
            {isHighConviction && (
                <div className={`absolute -top-10 -right-10 w-32 h-32 rounded-full blur-3xl opacity-20 ${isBuy ? 'bg-emerald-400' : 'bg-red-400'}`} />
            )}

            {/* --- HEADER: Momentum Identity --- */}
            <div className="relative flex justify-between items-start mb-3">
                <div className="flex items-center gap-3">
                    <div className={`flex items-center justify-center w-10 h-10 rounded-xl font-black text-lg shadow-sm ${isBuy ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
                        {signal.intraday_signal === "STRONG BUY" ? <Zap size={20} fill="currentColor" /> : <Target size={20} />}
                    </div>
                    <div>
                        <h3 className="text-xl font-black tracking-tight text-slate-800 leading-none">{signal.symbol}</h3>
                        <div className="flex items-center gap-2 mt-1">
                            <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${isBuy ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                {signal.intraday_signal || signal.signal}
                            </span>
                            <span className="text-[10px] font-bold text-slate-400 tracking-wider">
                                SCORE: <span className={scoreColor}>{signal.score}</span>
                            </span>
                        </div>
                    </div>
                </div>

                {/* Institutional Context (Paid App) */}
                <div className="flex flex-col items-end gap-1">
                    {rsLeader && (
                        <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 border border-blue-200 animate-pulse">
                            🔥 LEADER
                        </span>
                    )}
                    {instBias !== "Neutral" && (
                        <span className="text-[9px] font-bold text-slate-500 flex items-center gap-1">
                            <Activity size={10} /> Inst: {instBias}
                        </span>
                    )}
                </div>
            </div>

            {/* --- ACTION ZONE (The "Trade" Setup) --- */}
            <div className="grid grid-cols-4 gap-2 py-3 border-t border-b border-slate-200/50 my-2">
                <div className="flex flex-col gap-0.5">
                    <span className="text-[8px] sm:text-[9px] uppercase font-bold text-slate-400">LTP</span>
                    <span className="font-mono font-bold text-slate-600 text-xs sm:text-sm">
                        {typeof signal.price === 'number' ? `₹${signal.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '---'}
                    </span>
                </div>

                <div className="flex flex-col gap-0.5 border-l border-slate-200/50 pl-2">
                    <span className="text-[8px] sm:text-[9px] uppercase font-bold text-emerald-500">Entry</span>
                    <span className="font-mono font-bold text-emerald-600 text-xs sm:text-sm">
                        {typeof signal.entry === 'number' ? `₹${signal.entry.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '---'}
                    </span>
                </div>

                <div className="flex flex-col gap-0.5 border-l border-slate-200/50 pl-2">
                    <span className="text-[8px] sm:text-[9px] uppercase font-bold text-red-500">Stop Loss</span>
                    <span className="font-mono font-bold text-red-600 text-xs sm:text-sm">
                        {typeof signal.stop_loss === 'number' ? `₹${signal.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '---'}
                    </span>
                </div>

                <div className="flex flex-col gap-0.5 border-l border-slate-200/50 pl-2">
                    <span className="text-[8px] sm:text-[9px] uppercase font-bold text-blue-500">Target</span>
                    <span className="font-mono font-bold text-blue-600 text-xs sm:text-sm">
                        {typeof signal.target === 'number' ? `₹${signal.target.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '---'}
                    </span>
                </div>
            </div>

            {/* --- MOMENTUM METRICS --- */}
            <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-white/50 p-2 rounded-lg border border-slate-100">
                    <div className="flex justify-between items-center mb-1">
                        <span className="text-[9px] font-bold text-slate-400 uppercase">Trend Strength</span>
                        <TrendingUp size={12} className={signal.score > 60 ? "text-emerald-500" : "text-amber-500"} />
                    </div>
                    <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${signal.score > 60 ? 'bg-emerald-500' : 'bg-amber-500'}`} style={{ width: `${Math.min(100, signal.score)}%` }} />
                    </div>
                </div>
                <div className="bg-white/50 p-2 rounded-lg border border-slate-100">
                    <div className="flex justify-between items-center mb-1">
                        <span className="text-[9px] font-bold text-slate-400 uppercase">Volume Flow</span>
                        <BarChart2 size={12} className={signal.groups?.Volume?.score > 60 ? "text-blue-500" : "text-slate-400"} />
                    </div>
                    <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${signal.groups?.Volume?.score > 60 ? 'bg-blue-500' : 'bg-slate-300'}`} style={{ width: `${Math.min(100, signal.groups?.Volume?.score || 50)}%` }} />
                    </div>
                </div>
            </div>

            {/* --- FOOTER: Verdict --- */}
            <div className="flex items-center justify-between mt-1">
                <p className="text-[10px] font-medium text-slate-500 italic truncate max-w-[70%]">
                    {signal.strategic_summary || signal.verdict}
                </p>
                <button className={`p-2 rounded-lg shadow-sm transition-all text-white ${isBuy ? "bg-emerald-500 hover:bg-emerald-600" : "bg-red-500 hover:bg-red-600"}`}>
                    <ArrowRight size={16} />
                </button>
            </div>
        </div>
    );
}
