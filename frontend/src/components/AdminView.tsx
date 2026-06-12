import React, { useEffect, useState } from 'react';
import { Shield, ShieldAlert, User, Loader2 } from 'lucide-react';
import { authApi } from '../services/api';

interface UserProfile {
    id: string;
    username: string;
    is_admin: boolean;
}

export const AdminView: React.FC = () => {
    const [users, setUsers] = useState<UserProfile[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

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

    useEffect(() => {
        loadUsers();
    }, []);

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
        </div>
    );
};
