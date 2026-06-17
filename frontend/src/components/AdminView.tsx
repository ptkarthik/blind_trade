import React, { useEffect, useState, useRef } from 'react';
import { Shield, User, Loader2, Terminal, RefreshCw } from 'lucide-react';
import { authApi, systemApi } from '../services/api';

interface UserProfile {
    id: string;
    username: string;
    is_admin: boolean;
}

export const AdminView: React.FC = () => {
    const [users, setUsers] = useState<UserProfile[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [logs, setLogs] = useState<string>('');
    const [logService, setLogService] = useState<string>('worker');
    const [logsLoading, setLogsLoading] = useState<boolean>(false);
    const [isLive, setIsLive] = useState<boolean>(true);
    const logsEndRef = useRef<HTMLDivElement>(null);

    const loadUsers = async () => {
        try {
            const res = await authApi.getUsers();
            setUsers(res.data);
        } catch (err: any) {
            setError('Failed to load users. You might not have permission.');
        } finally {
            setLoading(false);
        }
    };

    const loadLogs = async (service: string = logService, silent: boolean = false) => {
        if (!silent) setLogsLoading(true);
        setLogService(service);
        try {
            const res = await systemApi.getLogs(service);
            setLogs(res.data.logs);
        } catch (err: any) {
            setLogs('Failed to load logs. ' + (err.response?.data?.detail || err.message));
        } finally {
            if (!silent) setLogsLoading(false);
        }
    };

    useEffect(() => {
        loadUsers();
        loadLogs('worker');
    }, []);

    useEffect(() => {
        let interval: ReturnType<typeof setInterval>;
        if (isLive) {
            interval = setInterval(() => {
                loadLogs(logService, true);
            }, 3000);
        }
        return () => {
            if (interval) clearInterval(interval);
        };
    }, [isLive, logService]);

    useEffect(() => {
        if (isLive && logsEndRef.current) {
            logsEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [logs, isLive]);

    const toggleAdmin = async (userId: string) => {
        try {
            await authApi.toggleAdmin(userId);
            await loadUsers();
        } catch (err: any) {
            alert(err.response?.data?.detail || 'Failed to update user');
        }
    };

    if (loading) return <div className="p-8 flex justify-center"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>;

    if (error) return <div className="p-8 text-destructive">{error}</div>;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold flex items-center gap-2">
                    <Shield className="w-6 h-6 text-primary" />
                    User Management
                </h2>
            </div>

            <div className="bg-card border border-border rounded-xl overflow-hidden">
                <table className="w-full text-left text-sm">
                    <thead className="bg-muted/50 border-b border-border">
                        <tr>
                            <th className="p-4 font-bold text-muted-foreground uppercase tracking-wider">User</th>
                            <th className="p-4 font-bold text-muted-foreground uppercase tracking-wider">Role</th>
                            <th className="p-4 font-bold text-muted-foreground uppercase tracking-wider text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {users.map(user => (
                            <tr key={user.id} className="hover:bg-muted/30 transition-colors">
                                <td className="p-4">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-primary/10 rounded-lg">
                                            <User className="w-4 h-4 text-primary" />
                                        </div>
                                        <span className="font-mono font-medium">{user.username}</span>
                                    </div>
                                </td>
                                <td className="p-4">
                                    {user.is_admin ? (
                                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                                            <Shield className="w-3 h-3" /> ADMIN
                                        </span>
                                    ) : (
                                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">
                                            <User className="w-3 h-3" /> VIEWER
                                        </span>
                                    )}
                                </td>
                                <td className="p-4 text-right">
                                    <button
                                        onClick={() => toggleAdmin(user.id)}
                                        className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-widest transition-colors ${user.is_admin ? 'bg-destructive/10 text-destructive hover:bg-destructive/20' : 'bg-primary/10 text-primary hover:bg-primary/20'}`}
                                    >
                                        {user.is_admin ? 'Revoke Admin' : 'Make Admin'}
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="mt-8 space-y-4">
                <div className="flex items-center justify-between">
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <Terminal className="w-6 h-6 text-primary" />
                        System Logs (Production)
                    </h2>
                    <div className="flex items-center gap-4">
                        <label className="flex items-center gap-2 text-sm font-medium cursor-pointer text-muted-foreground hover:text-foreground transition-colors">
                            <input 
                                type="checkbox" 
                                checked={isLive} 
                                onChange={(e) => setIsLive(e.target.checked)}
                                className="rounded border-border text-primary focus:ring-primary bg-muted"
                            />
                            Live Auto-Scroll
                        </label>
                        <select 
                            value={logService}
                            onChange={(e) => loadLogs(e.target.value)}
                            className="bg-muted border border-border rounded-lg px-3 py-1.5 text-sm font-medium outline-none"
                        >
                            <option value="worker">Worker (Background Scan)</option>
                            <option value="fastapi">API (FastAPI Server)</option>
                        </select>
                        <button 
                            onClick={() => loadLogs(logService, false)}
                            disabled={logsLoading}
                            className="p-2 bg-primary/10 text-primary hover:bg-primary/20 rounded-lg transition-colors disabled:opacity-50"
                        >
                            <RefreshCw className={`w-4 h-4 ${logsLoading ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>
                <div className="bg-[#0a0a0a] border border-border rounded-xl p-4 overflow-hidden relative">
                    {logsLoading && (
                        <div className="absolute inset-0 bg-[#0a0a0a]/50 flex items-center justify-center backdrop-blur-sm z-10">
                            <Loader2 className="w-8 h-8 text-primary animate-spin" />
                        </div>
                    )}
                    <pre className="text-xs font-mono text-zinc-300 overflow-x-auto overflow-y-auto max-h-[500px] whitespace-pre-wrap break-all">
                        {logs || "No logs available."}
                        <div ref={logsEndRef} />
                    </pre>
                </div>
            </div>
        </div>
    );
};
