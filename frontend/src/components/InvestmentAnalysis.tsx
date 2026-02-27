

interface InvestmentAnalysisProps {
    data: any;
}

export function InvestmentAnalysis({ data }: InvestmentAnalysisProps) {
    const { groups, score, signal, entry, stop_loss, target, strategic_summary } = data;

    const allIndicators = groups ? Object.entries(groups).flatMap(([groupName, group]: [string, any]) => {
        if (!group || !group.details) return [];
        return (group.details || []).map((d: any) => ({
            ...d,
            src: groupName.split(' ')[0], // Short name like 'TECH' or 'FUND'
            groupName
        }));
    }) : [];

    const bullishDrivers = allIndicators.filter(i => i.type === 'positive');
    const riskFactors = allIndicators.filter(i => i.type === 'negative');

    const getScoreColor = (s: number) => {
        if (s >= 75) return "text-emerald-500";
        if (s >= 50) return "text-blue-500";
        if (s >= 30) return "text-orange-500";
        return "text-red-500";
    };

    return (
        <div className="space-y-6">

            {/* 1. Executive Summary Card */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="col-span-1 bg-muted/20 rounded-xl p-6 border border-border flex flex-col items-center justify-center text-center">
                    <h3 className="text-sm font-bold uppercase text-muted-foreground mb-2">AI Conviction Score</h3>
                    <div className={`text-6xl font-black ${getScoreColor(score)}`}>{score}</div>
                    <div className={`mt-2 px-3 py-1 rounded-full text-xs font-bold text-white ${signal === "BUY" ? "bg-emerald-600" : signal === "SELL" ? "bg-red-600" : "bg-gray-500"}`}>
                        {signal}
                    </div>
                </div>

                <div className="col-span-2 grid grid-cols-2 gap-4">
                    <div className="bg-muted/10 rounded-xl p-4 border border-border">
                        <div className="text-xs text-muted-foreground uppercase font-bold">Recommended Entry</div>
                        <div className="text-2xl font-mono font-bold mt-1">₹{typeof entry === 'number' ? entry.toLocaleString() : entry || 'N/A'}</div>
                        <div className="grid grid-cols-2 gap-2 mt-2">
                            <div className="text-[10px] text-muted-foreground">Target: <span className="text-emerald-500 font-bold">₹{typeof target === 'number' ? target.toLocaleString() : target || 'N/A'}</span></div>
                            <div className="text-[10px] text-muted-foreground">Stop: <span className="text-red-500 font-bold">₹{typeof stop_loss === 'number' ? stop_loss.toLocaleString() : stop_loss || 'N/A'}</span></div>
                        </div>
                    </div>

                    <div className="bg-muted/10 rounded-xl p-4 border border-border flex flex-col justify-between relative overflow-hidden">
                        {data.drawdown && (
                            <div className="absolute top-0 right-0 px-2 py-0.5 bg-red-500/10 text-red-600 text-[8px] font-black uppercase rounded-bl-lg border-l border-b border-red-500/20">
                                Max DD: {data.drawdown.max_drawdown_pct}%
                            </div>
                        )}
                        <div>
                            <div className="text-xs text-muted-foreground uppercase font-bold">Analyst Verdict</div>
                            <div className="text-sm font-semibold mt-1 line-clamp-3 italic">
                                "{strategic_summary || data.reason || "AI model confirms alignment across technical and fundamental layers."}"
                            </div>
                        </div>
                    </div>
                    {Array.isArray(data.levels?.support) && data.levels.support.some((s: any) => s.strength === "Ironclad") && (
                        <div className="text-[9px] font-black text-emerald-600 flex items-center gap-1 mt-2">
                            <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            IRONCLAD SUPPORT DETECTED
                        </div>
                    )}
                </div>
            </div>

            {/* 1.5 Professional Alpha Metrics (Phase 30) */}
            {
                data.alpha_intel && (
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                        <div className="bg-primary/5 border border-primary/10 rounded-xl p-3 text-center">
                            <div className="text-[9px] font-black text-primary/60 uppercase tracking-widest">Growth Prob.</div>
                            <div className={`text-sm font-black mt-1 ${data.alpha_intel.growth_probability === 'High' ? 'text-emerald-600' : 'text-amber-600'}`}>
                                {data.alpha_intel.growth_probability}
                            </div>
                        </div>
                        <div className="bg-primary/5 border border-primary/10 rounded-xl p-3 text-center">
                            <div className="text-[9px] font-black text-primary/60 uppercase tracking-widest">Risk Level</div>
                            <div className={`text-sm font-black mt-1 ${data.alpha_intel.risk_level === 'Low' ? 'text-emerald-600' : data.alpha_intel.risk_level === 'High' ? 'text-red-600' : 'text-amber-600'}`}>
                                {data.alpha_intel.risk_level}
                            </div>
                        </div>
                        <div className="bg-primary/5 border border-primary/10 rounded-xl p-3 text-center">
                            <div className="text-[9px] font-black text-primary/60 uppercase tracking-widest">Valuation</div>
                            <div className="text-sm font-black mt-1 text-slate-700">{data.alpha_intel.valuation_status}</div>
                        </div>
                        <div className="bg-primary/5 border border-primary/10 rounded-xl p-3 text-center">
                            <div className="text-[9px] font-black text-primary/60 uppercase tracking-widest">Suggested Hold</div>
                            <div className="text-sm font-black mt-1 text-slate-700">{data.alpha_intel.suggested_hold}</div>
                        </div>
                        <div className="bg-primary/5 border border-primary/10 rounded-xl p-3 text-center">
                            <div className="text-[9px] font-black text-primary/60 uppercase tracking-widest">Confidence</div>
                            <div className="text-sm font-black mt-1 text-primary">{data.alpha_intel.confidence}</div>
                        </div>
                    </div>
                )
            }

            {/* 1.6 Professional Resilience (Phase 32-34) */}
            <div className="flex flex-wrap gap-2 py-2">
                {data.alpha_intel?.moat_status && (
                    <div className="flex items-center gap-1.5 px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full">
                        <div className="text-[8px] font-black text-blue-600 uppercase">Moat:</div>
                        <div className="text-[10px] font-bold text-slate-700">{data.alpha_intel.moat_status}</div>
                    </div>
                )}
                {data.alpha_intel?.recovery_vibe && (
                    <div className="flex items-center gap-1.5 px-3 py-1 bg-purple-500/10 border border-purple-500/20 rounded-full">
                        <div className="text-[8px] font-black text-purple-600 uppercase">Recovery:</div>
                        <div className="text-[10px] font-bold text-slate-700">{data.alpha_intel.recovery_vibe}</div>
                    </div>
                )}
                {data.weights?.regime && (
                    <div className="flex items-center gap-1.5 px-3 py-1 bg-amber-500/10 border border-amber-500/20 rounded-full">
                        <div className="text-[8px] font-black text-amber-600 uppercase">Weighting:</div>
                        <div className="text-[10px] font-bold text-slate-700">{data.weights.regime}</div>
                    </div>
                )}
            </div>

            {/* 2. Analysis Grid: Dynamic Drivers vs Risk Factors */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 border-t border-border pt-8">
                {/* Pros Column */}
                <div className="space-y-6">
                    <div className="flex items-center gap-3 border-b border-emerald-100 pb-3">
                        <div className="h-5 w-1.5 bg-emerald-500 rounded-full" />
                        <h3 className="font-black text-sm uppercase tracking-[0.2em] text-emerald-600">Bullish Drivers</h3>
                    </div>

                    <div className="space-y-3">
                        {bullishDrivers.length > 0 ? bullishDrivers.map((indicator, idx) => (
                            <div key={`pos-${idx}`} className="flex items-center justify-between p-4 rounded-2xl border border-emerald-100 bg-emerald-500/[0.02] hover:bg-emerald-500/[0.05] transition-all group">
                                <div className="flex items-center gap-4">
                                    <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] group-hover:scale-125 transition-transform" />
                                    <div className="flex flex-col">
                                        <div className="flex items-center gap-2">
                                            <span className="text-sm font-bold text-slate-700">{indicator.text}</span>
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200 uppercase tracking-tighter">
                                                {indicator.label || indicator.src}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div className="text-[11px] font-black px-2.5 py-1 rounded-lg bg-white shadow-sm border border-emerald-100 text-emerald-600 tabular-nums">
                                    {indicator.value || 'Verified'}
                                </div>
                            </div>
                        )) : (
                            <div className="p-8 border border-dashed border-slate-200 rounded-3xl text-center text-xs text-muted-foreground italic">
                                No strong bullish drivers detected.
                            </div>
                        )}
                    </div>
                </div>

                {/* Risks Column */}
                <div className="space-y-6">
                    <div className="flex items-center gap-3 border-b border-red-100 pb-3">
                        <div className="h-5 w-1.5 bg-red-500 rounded-full" />
                        <h3 className="font-black text-sm uppercase tracking-[0.2em] text-red-600">Risk Factors</h3>
                    </div>

                    <div className="space-y-3">
                        {riskFactors.length > 0 ? riskFactors.map((indicator, idx) => (
                            <div key={`neg-${idx}`} className="flex items-center justify-between p-4 rounded-2xl border border-red-100 bg-red-500/[0.02] hover:bg-red-500/[0.05] transition-all group">
                                <div className="flex items-center gap-4">
                                    <div className="h-2 w-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)] group-hover:scale-125 transition-transform" />
                                    <div className="flex flex-col">
                                        <div className="flex items-center gap-2">
                                            <span className="text-sm font-bold text-slate-700">{indicator.text}</span>
                                            <span className="text-[8px] font-black px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200 uppercase tracking-tighter">
                                                {indicator.label || indicator.src}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div className="text-[11px] font-black px-2.5 py-1 rounded-lg bg-white shadow-sm border border-red-100 text-red-600 tabular-nums">
                                    {indicator.value || 'Risk'}
                                </div>
                            </div>
                        )) : (
                            <div className="p-8 border border-dashed border-slate-200 rounded-3xl text-center text-xs text-muted-foreground italic">
                                No major risks identified in this cycle.
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* 3. Professional Advisor Logic (Phase 40) */}
            {
                data.investment_advisory && (
                    <div className="mt-8 pt-8 border-t border-border space-y-6">
                        <div className="flex items-center gap-3">
                            <div className="h-5 w-1.5 bg-indigo-500 rounded-full" />
                            <h3 className="font-black text-sm uppercase tracking-[0.2em] text-indigo-600">Investment Advisor Console</h3>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {/* Scenario Engine */}
                            <div className="bg-muted/5 rounded-2xl border border-border overflow-hidden">
                                <div className="bg-muted/10 px-4 py-2 border-b border-border flex justify-between items-center">
                                    <span className="text-[10px] font-black uppercase text-muted-foreground tracking-widest">Scenario Engine (Price Projections)</span>
                                    <span className="text-[9px] font-bold text-indigo-600 italic">Expected Horizon: {data.investment_advisory.holding_period?.period_display || 'Mid-Term'}</span>
                                </div>
                                <div className="p-4 space-y-3">
                                    {Array.isArray(data.investment_advisory.scenarios) ? data.investment_advisory.scenarios.map((sc: any, idx: number) => (
                                        <div key={idx} className="flex items-center justify-between">
                                            <div className="flex items-center gap-3">
                                                <div className={`h-1.5 w-1.5 rounded-full ${idx === 0 ? 'bg-red-400' : idx === 1 ? 'bg-blue-400' : 'bg-emerald-400'}`} />
                                                <span className="text-xs font-bold text-slate-600 w-24">{sc.label}</span>
                                                <span className="text-[10px] font-medium text-muted-foreground italic w-12">({sc.probability})</span>
                                            </div>
                                            <div className="flex flex-col items-end">
                                                <span className="text-sm font-black text-slate-800">₹{sc.target}</span>
                                                <div className="flex items-center gap-1.5 justify-end">
                                                    <span className="text-[9px] font-bold text-emerald-600">+{data.price ? Math.round(((sc.target - data.price) / data.price) * 100) : 0}%</span>
                                                    <span className="text-[9px] font-medium text-muted-foreground opacity-60">@{(sc as any).cagr || "-"}%</span>
                                                </div>
                                            </div>
                                        </div>
                                    )) : <div className="text-xs text-muted-foreground italic p-4">Detailed scenario projections unavailable.</div>}
                                </div>
                            </div>

                            {/* Stop-Loss & Risk Management */}
                            <div className="space-y-4">
                                <div className="bg-red-500/[0.03] rounded-2xl border border-red-500/10 p-5">
                                    <div className="text-[10px] font-black uppercase text-red-600 mb-4 tracking-widest">Advanced Risk Guard</div>
                                    <div className="grid grid-cols-2 gap-6">
                                        <div>
                                            <div className="text-[10px] text-muted-foreground font-bold uppercase mb-1">Structural Stop</div>
                                            <div className="text-2xl font-black text-red-600">₹{data.investment_advisory.stop_loss?.stop_price || 'N/A'}</div>
                                            <div className="text-[9px] font-bold text-slate-500 mt-1 uppercase">{data.investment_advisory.stop_loss?.type || 'Standard'}</div>
                                        </div>
                                        <div>
                                            <div className="text-[10px] text-muted-foreground font-bold uppercase mb-1">Trailing Activation</div>
                                            <div className="text-2xl font-black text-indigo-600">₹{data.investment_advisory.stop_loss?.trailing_logic?.activation_target || 'N/A'}</div>
                                            <div className="text-[9px] font-bold text-slate-500 mt-1 uppercase">25% Upside Trigger</div>
                                        </div>
                                    </div>
                                    <div className="mt-4 pt-4 border-t border-red-500/10 text-[10px] italic text-slate-600 leading-tight">
                                        Trailing Buffer: <span className="font-bold text-indigo-600">{data.investment_advisory.stop_loss?.trailing_logic?.buffer || "10% Trailing (Est)"}</span>
                                    </div>
                                </div>

                                <div className="bg-indigo-500/[0.03] rounded-2xl border border-indigo-500/10 p-4 flex items-center justify-between">
                                    <div>
                                        <div className="text-[10px] font-black uppercase text-indigo-600 tracking-widest">Recommended Review Cycle</div>
                                        <div className="text-sm font-black text-slate-700 mt-1">{data.investment_advisory.review_cycle || 'Quarterly'}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-[10px] font-black uppercase text-indigo-600 tracking-widest">Trend Slope</div>
                                        <div className="text-[11px] font-black text-slate-700 mt-1">{data.investment_advisory.trend_status?.slope || 'Neutral'}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )
            }
        </div >
    );
}
