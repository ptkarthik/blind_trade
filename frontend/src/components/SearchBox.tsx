import { useState, useEffect, useRef } from 'react';
import { Search, X } from 'lucide-react';
import { marketApi } from '../services/api';

interface SearchBoxProps {
    onSelect: (symbol: string) => void;
}

interface SearchResult {
    symbol: string;
    name: string;
}

export function SearchBox({ onSelect }: SearchBoxProps) {
    const [query, setQuery] = useState('');
    const [suggestions, setSuggestions] = useState<SearchResult[]>([]);
    const [isOpen, setIsOpen] = useState(false);
    const wrapperRef = useRef<HTMLDivElement>(null);

    // Debounce Search
    useEffect(() => {
        const timeoutId = setTimeout(async () => {
            if (query.trim().length >= 3) {
                try {
                    const res = await marketApi.search(query);
                    setSuggestions(res.data);
                    setIsOpen(true);
                } catch (error) {
                    console.error("Search failed", error);
                }
            } else {
                setSuggestions([]);
                setIsOpen(false);
            }
        }, 300); // 300ms debounce

        return () => clearTimeout(timeoutId);
    }, [query]);

    // Click outside to close
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const handleSelect = (symbol: string) => {
        setQuery(symbol);
        setIsOpen(false);
        onSelect(symbol);
    };

    const clearSearch = () => {
        setQuery('');
        setSuggestions([]);
        setIsOpen(false);
    };

    return (
        <div ref={wrapperRef} className="relative w-full md:w-96">
            <div className="relative">
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value.toUpperCase())}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && query.trim().length >= 3) {
                            handleSelect(query.trim().toUpperCase());
                        }
                    }}
                    placeholder="Search e.g. INFOSYS, ZOMATO..."
                    className="w-full pl-10 pr-10 py-2 rounded-full border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm font-medium uppercase placeholder:normal-case"
                />
                <button
                    type="button"
                    onClick={() => query.trim().length >= 3 && handleSelect(query.trim().toUpperCase())}
                    className="absolute left-3 top-2.5 hover:text-primary transition-colors"
                >
                    <Search className="h-4 w-4 text-muted-foreground" />
                </button>
                {query && (
                    <button type="button" onClick={clearSearch} className="absolute right-3 top-2.5">
                        <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                    </button>
                )}
            </div>

            {/* Dropdown Suggestions */}
            {isOpen && suggestions.length > 0 && (
                <div className="absolute top-full mt-2 w-full bg-popover rounded-md border border-border shadow-lg z-50 overflow-hidden">
                    <ul className="max-h-60 overflow-y-auto">
                        {suggestions.map((s) => (
                            <li
                                key={s.symbol}
                                onClick={() => handleSelect(s.symbol)}
                                className="px-4 py-2 hover:bg-muted cursor-pointer flex justify-between items-center text-sm"
                            >
                                <span className="font-bold">{s.symbol}</span>
                                <span className="text-xs text-muted-foreground truncate max-w-[150px]">{s.name}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}
