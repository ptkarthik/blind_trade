import { X, AlertCircle } from 'lucide-react';

interface FailedSymbol {
    symbol: string;
    reason: string;
}

interface FailedSymbolsModalProps {
    isOpen: boolean;
    onClose: () => void;
    symbols: FailedSymbol[];
}

export function FailedSymbolsModal({ isOpen, onClose, symbols }: FailedSymbolsModalProps) {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-card w-full max-w-2xl rounded-xl shadow-2xl border border-border flex flex-col max-h-[85vh] animate-in zoom-in-95 duration-200">
                <div className="flex justify-between items-center p-4 border-b border-border">
                    <h2 className="text-lg font-bold flex items-center gap-2 text-destructive">
                        <AlertCircle className="w-5 h-5" />
                        Validation Failures ({symbols.length})
                    </h2>
                    <button onClick={onClose} className="p-1 hover:bg-muted rounded-full transition-colors">
                        <X className="w-5 h-5 text-muted-foreground hover:text-foreground" />
                    </button>
                </div>

                <div className="p-4 flex-1 overflow-y-auto">
                    <p className="text-sm text-muted-foreground mb-4 border-l-2 border-destructive pl-3 py-1 bg-destructive/5 rounded-r">
                        These symbols were skipped during the scan due to missing data, connection failures, or invalid criteria setups. They have been excluded from the results.
                    </p>
                    <div className="space-y-2">
                        {symbols.length === 0 ? (
                            <p className="text-center text-muted-foreground py-8">No failures recorded.</p>
                        ) : (
                            symbols.map((item, idx) => (
                                <div key={idx} className="flex flex-col sm:flex-row sm:justify-between sm:items-center p-3 rounded-lg bg-muted/50 border border-border text-sm gap-2">
                                    <span className="font-mono font-bold text-primary">{item.symbol}</span>
                                    <span className="text-muted-foreground text-xs sm:text-sm truncate sm:max-w-[70%]" title={item.reason}>
                                        {item.reason}
                                    </span>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
