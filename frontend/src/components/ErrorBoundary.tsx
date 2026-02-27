import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false
    };

    public static getDerivedStateFromError(_: Error): State {
        return { hasError: true };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('Uncaught error:', error, errorInfo);
    }

    public render() {
        if (this.state.hasError) {
            return this.props.fallback || (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <div className="bg-card w-full max-w-md p-6 rounded-2xl border border-destructive/50 shadow-2xl flex flex-col items-center text-center animate-in fade-in zoom-in-95">
                        <div className="h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
                            <span className="text-2xl">⚠️</span>
                        </div>
                        <h2 className="text-lg font-black text-destructive uppercase tracking-widest mb-2">Analysis Render Error</h2>
                        <p className="text-sm text-muted-foreground mb-6">
                            This specific stock result encountered a rendering issue. Please try a different symbol.
                        </p>
                        <button
                            onClick={() => window.location.reload()}
                            className="bg-destructive text-white px-6 py-2 rounded-lg font-bold text-xs uppercase tracking-widest hover:bg-destructive/90 transition-colors shadow-lg shadow-destructive/20"
                        >
                            Reload App
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
