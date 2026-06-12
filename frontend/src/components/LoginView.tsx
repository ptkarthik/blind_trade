import React, { useState } from 'react';
import { Lock, LogIn, AlertCircle } from 'lucide-react';
import { authApi } from '../services/api';

interface LoginViewProps {
    onLoginSuccess: (token: string) => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const res = await authApi.login(password);
            if (res.data && res.data.access_token) {
                onLoginSuccess(res.data.access_token);
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Invalid password');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(120,119,198,0.1),rgba(255,255,255,0))]">
            <div className="w-full max-w-sm p-8 bg-zinc-950 border border-zinc-800 rounded-3xl shadow-2xl relative overflow-hidden">
                {/* Decorative background blur */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full h-1/2 bg-indigo-500/10 blur-3xl rounded-full" />
                
                <div className="relative z-10">
                    <div className="flex justify-center mb-6">
                        <div className="p-4 bg-indigo-500/10 rounded-2xl border border-indigo-500/20">
                            <Lock className="w-8 h-8 text-indigo-400" />
                        </div>
                    </div>
                    
                    <h1 className="text-2xl font-black text-center text-white mb-2 tracking-tight">
                        Engine Access
                    </h1>
                    <p className="text-sm text-center text-zinc-400 mb-8">
                        Enter master password to unlock the trading core.
                    </p>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Master Password"
                                className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all text-center tracking-widest font-mono"
                                autoFocus
                            />
                        </div>

                        {error && (
                            <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
                                <AlertCircle size={16} />
                                {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading || !password}
                            className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-bold transition-all shadow-lg shadow-indigo-900/20"
                        >
                            {loading ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    <LogIn size={18} />
                                    AUTHORIZE
                                </>
                            )}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
};
