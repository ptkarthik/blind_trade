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
                <div className="p-6 rounded-2xl border border-dashed border-destructive/30 bg-destructive/5 text-center">
                    <h2 className="text-sm font-bold text-destructive uppercase tracking-widest mb-2">Analysis Render Error</h2>
                    <p className="text-xs text-muted-foreground italic">
                        This specific stock result encountered a rendering issue. Please try a different symbol.
                    </p>
                </div>
            );
        }

        return this.props.children;
    }
}
