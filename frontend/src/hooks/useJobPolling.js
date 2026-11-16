import { useCallback, useEffect, useRef } from 'react';
import apiClient from '../api/client';
import { pollJob } from '../utils/pollJob';

export const useJobPolling = (ownerId) => {
  const active = useRef(new Set());
  const owner = useRef(ownerId);
  const alive = useRef(false);
  owner.current = ownerId;
  useEffect(() => {
    alive.current = true;
    const tracked = active.current;
    return () => {
      alive.current = false;
      for (const stop of tracked) stop();
      tracked.clear();
    };
  }, [ownerId]);

  return useCallback((jobId, onComplete, onError, intervalMs = 3000, maxAttempts = 60) => {
    if (!alive.current || !ownerId || owner.current !== ownerId) return () => {};
    let stop;
    const complete = (callback) => (...values) => {
      active.current.delete(stop);
      if (alive.current && owner.current === ownerId) callback?.(...values);
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
  }, [ownerId]);
};
