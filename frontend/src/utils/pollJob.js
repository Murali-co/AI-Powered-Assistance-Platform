// Schedule the next request only after the previous one finishes.
export const pollJob = (request, onComplete, onError, intervalMs = 3000, maxAttempts = 60) => {
  const controller = new AbortController();
  let timer;
  let stopped = false;
  let attempts = 0;
  let consecutiveFailures = 0;
  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    controller.abort();
  };
  const fail = (message, retryable = false) => {
    stop();
    onError?.(message, { retryable });
  };
  const tick = async () => {
    if (stopped) return;
    if (attempts >= maxAttempts) {
      fail('Task timed out waiting for results. Your task is saved; reload this page to reconnect.', true);
      return;
    }
    attempts += 1;
    try {
      const state = await request(controller.signal);
      if (stopped) return;
      if (!state || typeof state !== 'object') {
        fail('Unexpected task status. Reload this page to reconnect.', true);
        return;
      }
      const { status, result, error, completed_at } = state;
      consecutiveFailures = 0;
      if (status === 'completed') {
        stop();
        if (completed_at) onComplete?.(result ?? {}, { completedAt: completed_at });
        else onComplete?.(result ?? {});
        return;
      }
      if (status === 'failed' || status === 'cancelled') {
        fail(error || (status === 'cancelled' ? 'Task was cancelled.' : 'Task execution failed.'));
        return;
      }
      if (status !== 'pending' && status !== 'processing') {
        fail('Unexpected task status. Reload this page to reconnect.', true);
        return;
      }
    } catch (error) {
      if (stopped) return;
      const status = error?.response?.status;
      const transient = status >= 500 || status === 408 || status === 429 || (error?.isAxiosError && !error.response);
      if (transient) {
        consecutiveFailures += 1;
        if (consecutiveFailures < 5) {
          timer = setTimeout(tick, intervalMs * Math.min(consecutiveFailures, 5));
          return;
        }
        fail('Connection interrupted. Your task is saved; reload this page to reconnect.', true);
        return;
      }
      fail(error?.userFriendlyMessage || error?.message || 'Error checking task status.');
      return;
    }
    timer = setTimeout(tick, intervalMs);
  };
  timer = setTimeout(tick, intervalMs);
  return stop;
};
