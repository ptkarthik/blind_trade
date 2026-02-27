/* eslint-disable no-restricted-globals */
// Web Worker for Precise Job Polling (avoids background throttle)

let intervalId: any = null;

self.onmessage = (e: MessageEvent) => {
    const { action, interval } = e.data;

    if (action === 'START') {
        if (intervalId) clearInterval(intervalId);
        // Default to 2000ms if not provided
        intervalId = setInterval(() => {
            self.postMessage('TICK');
        }, interval || 2000);
    } else if (action === 'STOP') {
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
    }
};

export { };
