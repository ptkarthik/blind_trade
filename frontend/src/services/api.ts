import axios from 'axios';
import axiosRetry from 'axios-retry';

const api = axios.create({
    baseURL: 'http://localhost:8012/api/v1',
    timeout: 120000,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Retry failing requests 3 times with exponential backoff
// This handles the "Network Error" on app boot when frontend starts faster than backend
axiosRetry(api, {
    retries: 3,
    retryDelay: axiosRetry.exponentialDelay,
    retryCondition: (error) => {
        return axiosRetry.isNetworkOrIdempotentRequestError(error) || error.code === 'ECONNABORTED';
    }
});

export const marketApi = {
    getStatus: () => api.get('/market/status'),
    getLivePrice: (symbol: string) => api.get(`/market/live/${symbol}`),
    search: (query: string) => api.get(`/market/search?q=${query}`),
};

export const kiteApi = {
    getStatus: () => api.get('/market/kite/status'),
    login: () => api.post('/market/kite/login'),
};

export const signalApi = {
    getTodaySignals: (mode = 'swing', jobId?: string) => api.get(`/signals/today?mode=${mode}${jobId ? `&job_id=${jobId}` : ''}`),
    analyze: (symbol: string, mode = 'swing') => api.get(`/signals/${symbol}?mode=${mode}`),
    getSectorSignals: (mode = 'intraday', jobId?: string) => api.get(`/signals/sectors?mode=${mode}${jobId ? `&job_id=${jobId}` : ''}`),
    getPortfolioAnalysis: () => api.get('/signals/portfolio'),
};

export const jobsApi = {
    triggerScan: (type: string) => api.post('/jobs/scan', { type }),
    getStatus: (type?: string) => api.get(`/jobs/status${type ? `?job_type=${type}` : ''}`),
    stop: (type?: string) => api.post(`/jobs/stop${type ? `?job_type=${type}` : ''}`),
    pause: (type?: string) => api.post(`/jobs/pause${type ? `?job_type=${type}` : ''}`),
    resume: (type?: string) => api.post(`/jobs/resume${type ? `?job_type=${type}` : ''}`),
    getResults: (jobId: string) => api.get(`/jobs/${jobId}/results`),
};

export const papertradeApi = {
    getAccount: () => api.get('/papertrades/account'),
    placeOrder: (data: any) => api.post('/papertrades/buy', data),
    getTrades: () => api.get('/papertrades/trades'),
    getDailyHistory: () => api.get('/papertrades/history/daily'),
    closeTrade: (tradeId: string) => api.patch(`/papertrades/close/${tradeId}`),
    resetAccount: () => api.post('/papertrades/reset_account'),
};

export const settingsApi = {
    get: (key: string) => api.get(`/settings/${key}`),
    update: (key: string, value: string) => api.post('/settings', { key, value }),
};

export const auditApi = {
    getReport: (date?: string) => api.get(`/audit/report${date ? `?date=${date}` : ''}`),
    triggerEvaluation: (date?: string) => api.post(`/audit/evaluate${date ? `?date=${date}` : ''}`),
    getHistory: (days = 7) => api.get(`/audit/history?days=${days}`),
    getTraps: () => api.get('/audit/traps'),
};

export const liveApi = {
    getDashboard: (date?: string) => api.get(`/live${date ? `?date=${date}` : ''}`),
    triggerCheck: () => api.post('/live/run'),
};

export default api;
