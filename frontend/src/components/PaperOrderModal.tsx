
import { useState } from 'react';
import { X, ShoppingCart, Info } from 'lucide-react';
import type { Signal } from './DealCard';

interface PaperOrderModalProps {
    isOpen: boolean;
    onClose: () => void;
    signal: Signal;
    onConfirm: (qty: number) => void;
    balance: number;
}

export function PaperOrderModal({ isOpen, onClose, signal, onConfirm, balance }: PaperOrderModalProps) {
    const [qty, setQty] = useState(1);
    const price = signal.price || 0;
    const totalCost = qty * price;
    const tradeType = (signal as any)._intendedTradeType || 'PAPER';
    const isReal = tradeType === 'REAL';
    const mode = (signal as any)._mode || 'swing';
    const productType = mode === 'intraday' ? 'MIS' : 'CNC';
    
    // Real trades don't use virtual balance, but we'll bypass the block if it's REAL
    const canAfford = balance >= totalCost; // Real balance is passed in now!

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-card border border-border w-full max-w-md rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
                <div className={`p-6 border-b border-border flex justify-between items-center ${signal.signal === 'BUY' ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                    <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-xl ${signal.signal === 'BUY' ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
                            <ShoppingCart size={20} />
                        </div>
                        <div>
                            <h3 className="font-black text-xl tracking-tight">
                                {isReal ? 'LIVE TRADE: ' : 'Paper Trade: '}{signal.symbol}
                            </h3>
                            <p className={`text-[10px] font-bold uppercase tracking-widest ${isReal ? 'text-red-500 animate-pulse' : 'text-muted-foreground'}`}>
                                {isReal ? `REAL MONEY EXECUTION (${productType})` : `Execute Virtual Order (${productType})`}
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-black/5 rounded-full transition-colors">
                        <X size={20} />
                    </button>
                </div>

                <div className="p-6 space-y-6">
                    {/* Price Info */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-muted/30 p-3 rounded-2xl border border-border">
                            <p className="text-[10px] font-black text-muted-foreground uppercase mb-1">Current Price</p>
                            <p className="text-xl font-mono font-black">₹{price.toLocaleString('en-IN')}</p>
                        </div>
                        <div className="bg-muted/30 p-3 rounded-2xl border border-border">
                            <p className="text-[10px] font-black text-muted-foreground uppercase mb-1">Available Cash</p>
                            <p className="text-xl font-mono font-black text-primary">₹{balance.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</p>
                        </div>
                    </div>

                    {/* Qty Input */}
                    <div>
                        <label className="block text-xs font-black text-muted-foreground uppercase tracking-widest mb-2">Quantity</label>
                        <div className="flex gap-4">
                            <input 
                                type="number" 
                                value={qty} 
                                onChange={(e) => setQty(Math.max(1, parseInt(e.target.value) || 0))}
                                className="flex-1 bg-muted/50 border border-border rounded-xl p-4 font-mono font-bold text-lg focus:ring-2 focus:ring-primary outline-none transition-all"
                            />
                            <div className="flex flex-col gap-1 justify-center">
                                <button onClick={() => setQty(q => q + 10)} className="px-3 py-1 bg-muted rounded-lg text-[10px] font-bold hover:bg-muted/80">+10</button>
                                <button onClick={() => setQty(q => Math.max(1, q - 10))} className="px-3 py-1 bg-muted rounded-lg text-[10px] font-bold hover:bg-muted/80">-10</button>
                            </div>
                        </div>
                    </div>

                    {/* Order Summary */}
                    <div className="p-4 rounded-2xl bg-slate-50 border border-slate-100 flex justify-between items-center">
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase">Margin Required</p>
                            <p className={`text-xl font-black font-mono ${canAfford ? 'text-slate-800' : 'text-red-500'}`}>
                                ₹{totalCost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                            </p>
                        </div>
                        {!canAfford && (
                            <div className="flex items-center gap-1 text-red-500 text-[10px] font-bold animate-pulse">
                                <Info size={12} /> INSUFFICIENT FUNDS
                            </div>
                        )}
                    </div>

                    <button 
                        disabled={!canAfford || qty <= 0}
                        onClick={() => onConfirm(qty)}
                        className={`w-full py-4 rounded-2xl font-black uppercase text-sm tracking-widest shadow-lg transition-all transform active:scale-95 ${!canAfford ? 'bg-muted text-muted-foreground cursor-not-allowed' : isReal ? 'bg-red-600 text-white hover:bg-red-700 shadow-red-500/30 shadow-xl border-2 border-red-500' : 'bg-primary text-primary-foreground hover:shadow-primary/20'}`}
                    >
                        {isReal ? 'CONFIRM LIVE TRADE' : 'CONFIRM PAPER BUY'}
                    </button>
                </div>
            </div>
        </div>
    );
}
