import React, { useState } from 'react';
import { Lock, LogIn, UserPlus, AlertCircle, User as UserIcon } from 'lucide-react';
import { authApi } from '../services/api';

interface LoginViewProps {
    onLoginSuccess: (token: string) => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
    const [isRegistering, setIsRegistering] = useState(false);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            if (isRegistering) {
                await authApi.register(username, password);
                // Auto login after register
                const res = await authApi.login(username, password);
                if (res.data && res.data.access_token) {
                    onLoginSuccess(res.data.access_token);
                }
            } else {
                const res = await authApi.login(username, password);
                if (res.data && res.data.access_token) {
                    onLoginSuccess(res.data.access_token);
                }
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Authentication failed');
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
                        {isRegistering ? 'Create Account' : 'System Access'}
                    </h1>
                    <p className="text-sm text-center text-zinc-400 mb-8">
                        {isRegistering ? 'Register to view market data.' : 'Enter credentials to continue.'}
                    </p>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                                <UserIcon className="h-5 w-5 text-zinc-500" />
                            </div>
                            <input
                                type="text"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                placeholder="Username"
                                className="w-full pl-11 pr-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all font-mono"
                                autoFocus
                            />
                        </div>
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                                <Lock className="h-5 w-5 text-zinc-500" />
                            </div>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Password"
                                className="w-full pl-11 pr-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all font-mono"
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
                            disabled={loading || !password || !username}
                            className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl font-bold transition-all shadow-lg shadow-indigo-900/20"
                        >
                            {loading ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    {isRegistering ? <UserPlus size={18} /> : <LogIn size={18} />}
                                    {isRegistering ? 'REGISTER' : 'AUTHORIZE'}
                                </>
                            )}
                        </button>
                    </form>
                    
                    <div className="mt-6 text-center">
                        <button 
                            onClick={() => { setIsRegistering(!isRegistering); setError(''); }}
                            className="text-zinc-400 hover:text-indigo-400 text-sm transition-colors"
                        >
                            {isRegistering ? "Already have an account? Login" : "Need an account? Register"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};
