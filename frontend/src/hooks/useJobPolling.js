import { useEffect, useRef } from 'react';
import apiClient from '../api/client';
import { pollJob } from '../utils/pollJob';

export const useJobPolling = (ownerId) => {
  const active = useRef(new Set());
  useEffect(() => () => {
    for (const stop of active.current) stop();
    active.current.clear();
  }, [ownerId]);

  return (jobId, onComplete, onError, intervalMs = 3000, maxAttempts = 60) => {
    let stop;
    const complete = (callback) => (value) => {
      active.current.delete(stop);
      callback?.(value);
    };
    const cancel = pollJob(async (signal) => {
      const response = await apiClient.get(`/jobs/${jobId}/status`, { signal });
      return response.data;
    }, complete(onComplete), complete(onError), intervalMs, maxAttempts);
    stop = () => {
      active.current.delete(stop);
      cancel();
    };
    active.current.add(stop);
    return stop;
  };
};
