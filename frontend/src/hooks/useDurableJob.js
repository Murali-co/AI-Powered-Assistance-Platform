import { useCallback, useEffect, useRef, useState } from 'react';
import { useJobPolling } from './useJobPolling';
import { clearPendingTask, readPendingTask, writePendingTask } from '../utils/pendingTasks';

export const useDurableJob = (ownerId, kind, onComplete, onError) => {
  const poll = useJobPolling(ownerId);
  const callbacks = useRef({ onComplete, onError });
  const owner = useRef(ownerId);
  callbacks.current = { onComplete, onError };
  owner.current = ownerId;
  const [pending, setPending] = useState(null);
  useEffect(() => {
    setPending(readPendingTask(ownerId, kind));
  }, [ownerId, kind]);
  const entry = pending?.ownerId === ownerId ? pending : null;
  useEffect(() => {
    if (!entry) return;
    return poll(entry.jobId, (result, metadata) => {
      clearPendingTask(ownerId, kind, entry.jobId);
      setPending(current => current?.jobId === entry.jobId ? null : current);
      callbacks.current.onComplete?.(result, entry.context, metadata);
    }, (message, details) => {
      if (!details?.retryable) clearPendingTask(ownerId, kind, entry.jobId);
      setPending(current => current?.jobId === entry.jobId ? null : current);
      callbacks.current.onError?.(message);
    }, 3000, 300);
  }, [entry, ownerId, kind, poll]);
  const begin = useCallback((jobId, context = null) => {
    if (owner.current !== ownerId) return;
    const saved = writePendingTask(ownerId, kind, jobId, context);
    if (!saved) throw new Error('Invalid background task identifier.');
    setPending(saved);
  }, [ownerId, kind]);
  return { pendingJobId: entry?.jobId || null, begin };
};
