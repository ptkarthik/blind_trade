
import { useState, useEffect } from 'react';
import { RefreshCw, ArrowUpRight, ArrowDownRight, AlertTriangle } from 'lucide-react';
import { StockCardLongTerm } from './StockCardLongTerm';
import { StockCardIntraday } from './StockCardIntraday';
import type { Signal } from './DealCard';

interface SectorData {
    buys: Signal[];
    sells: Signal[];
    holds: Signal[];
    last_updated?: string;
}

interface SectorDealsProps {
    data: Record<string, SectorData>;
    loading: boolean;
    mode: 'intraday' | 'longterm';
    onRefresh: () => void;
    onSignalClick: (signal: Signal) => void;
}

export function SectorDeals({ data, loading, mode, onRefresh, onSignalClick }: SectorDealsProps) {
    const [selectedSector, setSelectedSector] = useState<string>("All Sectors");
    const [capFilter, setCapFilter] = useState<"All" | "Large" | "Mid" | "Small">("All");

    useEffect(() => {
        const sectorsList = ["All Sectors", ...Object.keys(data)];
        if (sectorsList.length > 0 && !sectorsList.includes(selectedSector)) {
            setSelectedSector("All Sectors");
        }
    }, [data, selectedSector]);

    const sectors = ["All Sectors", ...Object.keys(data || {})];

    // Aggregation for "All Sectors"
    let currentData: SectorData;
    if (selectedSector === "All Sectors") {
        const allBuys: Signal[] = [];
        const allHolds: Signal[] = [];
        const allSells: Signal[] = [];
        let lastUpdated = "Never";

        Object.values(data || {}).forEach(sectorData => {
            if (!sectorData) return;
            allBuys.push(...(sectorData.buys || []));
            allHolds.push(...(sectorData.holds || []));
            allSells.push(...(sectorData.sells || []));
            if (sectorData.last_updated && sectorData.last_updated !== "Never") {
                lastUpdated = sectorData.last_updated;
            }
        });

        // Unique by symbol and sort by score
        const getUniqueSorted = (sigs: Signal[]) => {
            const unique = sigs.reduce((acc, current) => {
                const x = acc.find(item => item.symbol === current.symbol);
                if (!x) return acc.concat([current]);
                else return acc;
            }, [] as Signal[]);
            return unique.sort((a, b) => b.score - a.score);
        };

        currentData = {
            buys: getUniqueSorted(allBuys),
            holds: getUniqueSorted(allHolds),
            sells: getUniqueSorted(allSells),
            last_updated: lastUpdated
        };
    } else {
        currentData = (data && data[selectedSector]) || { buys: [], sells: [], holds: [] };
    }

    // Filter Logic
    const filterSignals = (signals: Signal[]) => {
        if (capFilter === "All") return signals;
        return signals.filter(s => s.market_cap_category === capFilter);
    };

    const displayBuys = filterSignals(currentData.buys || []);
    const displaySells = filterSignals(currentData.sells || []);
    const displayHolds = filterSignals(currentData.holds || []);

    // Helper to render correct card
    const renderCard = (signal: Signal, idx: number) => {
        if (mode === 'intraday') {
            return <StockCardIntraday key={signal.symbol} signal={signal} rank={idx + 1} onClick={() => onSignalClick(signal)} />;
        }
        return <StockCardLongTerm key={signal.symbol} signal={signal} rank={idx + 1} onClick={() => onSignalClick(signal)} />;
    };

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div className="flex flex-col">
                    <h2 className="text-2xl font-bold">Sector Opportunities</h2>
                    {currentData.last_updated && (
                        <span className="text-xs text-muted-foreground font-mono">
                            Updated: {currentData.last_updated}
                        </span>
                    )}
                </div>
                <button
                    onClick={onRefresh}
                    disabled={loading}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm bg-muted hover:bg-muted/80 rounded-md transition-colors"
                >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    Refresh Results
                </button>
            </div>

            {/* Controls Row: Sectors + Cap Filter */}
            <div className="flex flex-col gap-4">
                {/* Sector Tabs */}
                <div className="flex overflow-x-auto pb-2 gap-2 scrollbar-hide">
                    {sectors.map(sec => (
                        <button
                            key={sec}
                            onClick={() => setSelectedSector(sec)}
                            className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all ${selectedSector === sec
                                ? 'bg-primary text-primary-foreground shadow-md'
                                : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                                }`}
                        >
                            {sec}
                        </button>
                    ))}
                </div>

                {/* Market Cap Filter */}
                <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium text-muted-foreground">Market Cap:</span>
                    {["All", "Large", "Mid", "Small"].map((cap) => (
                        <button
                            key={cap}
                            onClick={() => setCapFilter(cap as any)}
                            className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors border ${capFilter === cap
                                ? "bg-secondary text-secondary-foreground border-secondary-foreground/20"
                                : "bg-background text-muted-foreground border-border hover:bg-muted"
                                }`}
                        >
                            {cap}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content Area */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {/* TOP BUYS */}
                <div className="space-y-4">
                    <h3 className="text-xl font-bold flex items-center gap-2 text-emerald-600">
                        <ArrowUpRight className="h-6 w-6" /> Top 100 Buys
                    </h3>
                    <div className="space-y-4 max-h-[800px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-emerald-200">
                        {displayBuys.length > 0 ? (
                            displayBuys.slice(0, 100).map((signal, idx) => renderCard(signal, idx))
                        ) : (
                            <EmptyState type="BUY" filter={capFilter} />
                        )}
                    </div>
                </div>

                {/* TOP HOLDS */}
                <div className="space-y-4">
                    <h3 className="text-xl font-bold flex items-center gap-2 text-amber-600">
                        <AlertTriangle className="h-6 w-6" /> Top 100 Holds
                    </h3>
                    <div className="space-y-4 max-h-[800px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-amber-200">
                        {displayHolds.length > 0 ? (
                            displayHolds.slice(0, 100).map((signal, idx) => renderCard(signal, idx))
                        ) : (
                            <EmptyState type="HOLD" filter={capFilter} />
                        )}
                    </div>
                </div>

                {/* TOP SELLS */}
                <div className="space-y-4">
                    <h3 className="text-xl font-bold flex items-center gap-2 text-red-600">
                        <ArrowDownRight className="h-6 w-6" /> Top 100 Sells
                    </h3>
                    <div className="space-y-4 max-h-[800px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-red-200">
                        {displaySells.length > 0 ? (
                            displaySells.slice(0, 100).map((signal, idx) => renderCard(signal, idx))
                        ) : (
                            <EmptyState type="SELL" filter={capFilter} />
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}


function EmptyState({ type, filter }: { type: "BUY" | "SELL" | "HOLD"; filter?: string }) {
    const isBuy = type === "BUY";
    const isHold = type === "HOLD";
    const colorClass = isBuy ? "border-emerald-200 bg-emerald-50/10 text-emerald-200" : isHold ? "border-amber-200 bg-amber-50/10 text-amber-200" : "border-red-200 bg-red-50/10 text-red-200";

    return (
        <div className={`flex flex-col items-center justify-center p-8 border border-dashed rounded-xl gap-2 ${colorClass}`}>
            <AlertTriangle className="h-8 w-8" />
            <p className="text-sm font-medium text-muted-foreground text-center">
                No reliable {type} signals found {filter !== "All" && `for ${filter} Cap`}.<br />
                <span className="text-xs opacity-70">Market conditions do not meet strategy.</span>
            </p>
        </div>
    );
}
