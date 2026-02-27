import axios from 'axios';
import axiosRetry from 'axios-retry';

const api = axios.create({
    baseURL: 'http://localhost:8010/api/v1',
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

export const signalApi = {
    getTodaySignals: (mode = 'swing') => api.get(`/signals/today?mode=${mode}`),
    analyze: (symbol: string, mode = 'swing') => api.get(`/signals/${symbol}?mode=${mode}`),
    getSectorSignals: (mode = 'intraday') => api.get(`/signals/sectors?mode=${mode}`),
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

export default api;
