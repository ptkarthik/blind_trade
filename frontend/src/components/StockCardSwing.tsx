import { TrendingUp, Target, Shield, Clock, Sparkles, BrainCircuit } from 'lucide-react';
import type { Signal } from './DealCard';
import { ScoreGauge } from './ScoreGauge';

interface Props {
    signal: Signal;
    onClick: () => void;
    onBuy?: (e: React.MouseEvent, tradeType: 'PAPER' | 'REAL') => void;
}

export const StockCardSwing: React.FC<Props> = ({ signal, onClick, onBuy }) => {
    // Specialist Tag Parser
    const parseSetupTags = (setupStr: string) => {
        if (!setupStr) return [];
        const matches = setupStr.match(/\[(.*?)\]/g);
        return matches ? matches.map(m => m.slice(1, -1)) : [];
    };

    const setupTags = parseSetupTags(signal.setup_tag || "");

    return (
        <div
            className="bg-card border border-border shadow-md rounded-2xl p-5 hover:border-primary/50 transition-all cursor-pointer relative overflow-hidden group flex flex-col h-full"
            onClick={onClick}
        >
            {/* Background Decor */}
            <div className="absolute top-0 right-0 p-8 opacity-[0.03] group-hover:opacity-10 transition-opacity">
                <TrendingUp size={120} />
            </div>

            <div className="flex justify-between items-start mb-4 relative z-10">
                <div>
                    <h3 className="font-black text-2xl tracking-tight text-foreground">{signal.symbol}</h3>
                    <p className="text-sm font-semibold tracking-widest text-muted-foreground uppercase">{signal.name}</p>
                </div>

                <div className="flex flex-col items-end">
                    {signal.tradability?.is_kite_restricted && (
                        <div className="flex items-center gap-1 bg-red-500/10 border border-red-500/30 px-2 py-0.5 rounded-md mb-2 animate-pulse">
                            <span className="text-[9px] font-black text-red-600 uppercase tracking-tighter">Kite: MIS Blocked</span>
                        </div>
                    )}
                    <ScoreGauge score={signal.score} />
                    <div className="flex gap-1 mt-1">
                        {setupTags.map((tag, i) => (
                            <span key={i} className={`text-[8px] font-black px-1.5 py-0.5 rounded border border-slate-200 uppercase tracking-tighter ${tag.includes('💎') ? 'bg-primary text-white border-primary' : 'bg-white text-muted-foreground'}`}>
                                {tag}
                            </span>
                        ))}
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-widest text-primary mt-1">{signal.confidence}</span>
                    {signal.ai_confidence !== undefined && (
                        <div className="mt-2 flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 px-2 py-1 rounded-md">
                            <BrainCircuit size={12} className="text-emerald-600" />
                            <div className="flex flex-col items-end leading-none">
                                <span className="text-[8px] font-black tracking-widest uppercase text-emerald-600">AI Match</span>
                                <span className="text-xs font-black text-emerald-700">{signal.ai_confidence}%</span>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div className="mb-4 flex items-center justify-between relative z-10 bg-slate-50/50 p-3 rounded-xl border border-border/50">
                <div className="flex flex-col">
                    <span className="text-[9px] uppercase font-black tracking-widest text-muted-foreground mb-0.5 flex items-center gap-1">
                        {signal.ltp_source === 'kite_live' && <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />}
                        CURRENT (LTP)
                    </span>
                    <span className="text-xl font-black tracking-tighter text-slate-500">
                        ₹{signal.price ? Number(signal.price).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '---'}
                    </span>
                    {signal.ltp_change_pct !== undefined && signal.ltp_change_pct !== 0 && (
                        <span className={`text-[9px] font-bold ${signal.ltp_change_pct > 0 ? 'text-emerald-500' : 'text-destructive'}`}>
                            {signal.ltp_change_pct > 0 ? '+' : ''}{Number(signal.ltp_change_pct).toFixed(2)}%
                        </span>
                    )}
                </div>

                <div className="h-8 w-px bg-border/50 mx-2" />

                {signal.delivery_pct !== undefined && (
                    <>
                        <div className="flex flex-col items-center">
                            <span className="text-[9px] uppercase font-black tracking-widest text-muted-foreground mb-0.5">
                                DELIVERY
                            </span>
                            <span className={`text-xl font-black tracking-tighter ${signal.delivery_pct >= 60 ? 'text-emerald-500' : signal.delivery_pct >= 45 ? 'text-blue-500' : signal.delivery_pct < 25 ? 'text-destructive' : 'text-slate-500'}`}>
                                {signal.delivery_pct}%
                            </span>
                        </div>
                        <div className="h-8 w-px bg-border/50 mx-2" />
                    </>
                )}

                <div className="flex flex-col text-right">
                    <span className="text-[9px] uppercase font-black tracking-widest text-primary flex items-center justify-end gap-1 mb-0.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-primary" /> SMART ENTRY
                    </span>
                    <span className="text-2xl font-black tracking-tighter text-foreground">
                        ₹{(signal.scan_price || signal.entry) ? Number(signal.scan_price || signal.entry).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '---'}
                    </span>
                </div>
            </div>

            {/* Logistics Grid (Specific to Swing Trading) */}
            <div className="grid grid-cols-2 gap-3 mb-5 mt-auto relative z-10">
                <div className="bg-muted/50 p-3 rounded-xl border border-border/50 flex flex-col items-center">
                    <span className="text-[9px] uppercase font-bold tracking-widest text-muted-foreground flex items-center gap-1"><Shield size={12} /> Stop Loss</span>
                    <span className="font-mono font-bold text-destructive">
                        ₹{signal.stop_loss ? Number(signal.stop_loss).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '---'}
                    </span>
                </div>
                <div className="bg-primary/5 p-3 rounded-xl border border-primary/20 flex flex-col items-center">
                    <span className="text-[9px] uppercase font-bold tracking-widest text-primary flex items-center gap-1"><Target size={12} /> Target</span>
                    <span className="font-mono font-bold text-emerald-500">
                        ₹{signal.target ? Number(signal.target).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '---'}
                    </span>
                </div>
                <div className="bg-muted/50 p-3 rounded-xl border border-border/50 flex flex-col items-center col-span-2">
                    <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground flex items-center gap-1"><Clock size={12} /> Holding Period</span>
                    <span className="font-mono font-bold text-foreground">{signal.hold_duration || '---'}</span>
                </div>
                {signal.ai_reason && (
                    <div className="bg-emerald-500/5 p-3 rounded-xl border border-emerald-500/20 col-span-2 flex flex-col gap-1">
                        <span className="text-[9px] uppercase font-black tracking-widest text-emerald-700 flex items-center gap-1">
                            <Sparkles size={10} /> AI RATIONALE
                        </span>
                        <span className="text-[10px] font-medium text-emerald-800 italic leading-relaxed">"{signal.ai_reason}"</span>
                    </div>
                )}
            </div>

            <div className="space-y-2 relative z-10 border-t border-border pt-4">
                {signal.reasons?.slice(0, 3).map((r: any, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                        <span className={`px-1.5 py-0.5 rounded uppercase font-black tracking-widest text-[9px] ${r.type === 'positive' ? 'bg-emerald-500/10 text-emerald-500' :
                            r.type === 'negative' ? 'bg-red-500/10 text-red-500' :
                                'bg-blue-500/10 text-blue-500'
                            }`}>
                            {r.label}
                        </span>
                        <span className="text-muted-foreground truncate">{r.text}</span>
                        {r.value && <span className="ml-auto font-mono text-[10px] font-bold text-foreground">{r.value}</span>}
                    </div>
                ))}
                {signal.reasons && signal.reasons.length > 3 && (
                    <div className="text-[10px] font-bold tracking-widest text-muted-foreground/60 mt-2 text-center w-full uppercase">
                        + {signal.reasons.length - 3} More Triggers
                    </div>
                )}
            </div>

            {/* AMO & Pre-Market Strategy */}
            {(signal.amo_action || (signal.premarket_checks && signal.premarket_checks.length > 0)) && (
                <div className="mt-4 pt-4 border-t border-border flex flex-col gap-2 relative z-10">
                    <span className="text-[10px] font-black tracking-widest uppercase text-muted-foreground mb-1">Execution Strategy</span>
                    {signal.amo_action && (
                        <div className={`p-2.5 rounded-xl border flex flex-col gap-1 ${signal.amo_action.includes('✅') ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
                            <div className={`text-[11px] font-black ${signal.amo_action.includes('✅') ? 'text-emerald-700' : 'text-red-700'}`}>{signal.amo_action}</div>
                            <span className="text-[10px] font-medium text-muted-foreground leading-tight">{signal.amo_reason}</span>
                        </div>
                    )}
                    {signal.premarket_checks && signal.premarket_checks.length > 0 && (
                        <div className="flex flex-col gap-1.5 p-2.5 rounded-xl bg-amber-500/5 border border-amber-500/20 mt-1">
                            <span className="text-[9px] font-black tracking-widest text-amber-700 uppercase flex items-center gap-1">
                                <Clock size={10} /> 9:00 AM Preconditions
                            </span>
                            {signal.premarket_checks.map((chk, i) => (
                                <div key={i} className="text-[10px] text-amber-800 font-medium flex items-start gap-1.5 leading-tight">
                                    <div className="w-1 h-1 rounded-full bg-amber-500 shrink-0 mt-1.5" />
                                    {chk}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* --- ACTION BUTTONS (Manual Trade) --- */}
            {onBuy && (
                <div className="mt-4 pt-4 border-t border-border flex items-center justify-end gap-2 relative z-10">
                    <button 
                        onClick={(e) => {
                            e.stopPropagation();
                            onBuy(e, 'PAPER');
                        }}
                        className="text-[10px] font-black uppercase px-3 py-1.5 rounded border transition-all text-emerald-600 bg-emerald-50 border-emerald-100 hover:bg-emerald-500 hover:text-white"
                    >
                        BUY (PAPER)
                    </button>
                    <button 
                        onClick={(e) => {
                            e.stopPropagation();
                            if(confirm("⚠️ Place REAL LIVE ORDER on Zerodha?")) onBuy(e, 'REAL');
                        }}
                        className="text-[10px] font-black uppercase px-3 py-1.5 rounded border transition-all shadow-sm text-white bg-emerald-600 border-emerald-700 hover:bg-emerald-700"
                    >
                        BUY (REAL)
                    </button>
                </div>
            )}
        </div>
    );
};
