import { TrendingUp, Target, Shield, Clock } from 'lucide-react';
import type { Signal } from './DealCard';
import { ScoreGauge } from './ScoreGauge';

interface Props {
    signal: Signal;
    onClick: () => void;
}

export const StockCardSwing: React.FC<Props> = ({ signal, onClick }) => {
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
                    <ScoreGauge score={signal.score} />
                    <div className="flex gap-1 mt-1">
                        {setupTags.map((tag, i) => (
                            <span key={i} className={`text-[8px] font-black px-1.5 py-0.5 rounded border border-slate-200 uppercase tracking-tighter ${tag.includes('💎') ? 'bg-primary text-white border-primary' : 'bg-white text-muted-foreground'}`}>
                                {tag}
                            </span>
                        ))}
                    </div>
                    <span className="text-[10px] font-bold uppercase tracking-widest text-primary mt-1">{signal.confidence}</span>
                </div>
            </div>

            <div className="mb-4 flex items-center justify-between relative z-10 bg-slate-50/50 p-3 rounded-xl border border-border/50">
                <div className="flex flex-col">
                    <span className="text-[9px] uppercase font-black tracking-widest text-muted-foreground mb-0.5">CURRENT (LTP)</span>
                    <span className="text-xl font-black tracking-tighter text-slate-500">
                        ₹{signal.price ? Number(signal.price).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '---'}
                    </span>
                </div>

                <div className="h-8 w-px bg-border/50 mx-2" />

                <div className="flex flex-col text-right">
                    <span className="text-[9px] uppercase font-black tracking-widest text-primary flex items-center justify-end gap-1 mb-0.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-primary" /> SMART ENTRY
                    </span>
                    <span className="text-2xl font-black tracking-tighter text-foreground">
                        ₹{signal.entry ? Number(signal.entry).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '---'}
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
        </div>
    );
};
