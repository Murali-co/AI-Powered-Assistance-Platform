// Schedule the next request only after the previous one finishes.
export const pollJob = (request, onComplete, onError, intervalMs = 3000, maxAttempts = 60) => {
  const controller = new AbortController();
  let timer;
  let stopped = false;
  let attempts = 0;
  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    controller.abort();
  };
  const fail = (message) => {
    stop();
    onError?.(message);
  };
  const tick = async () => {
    if (stopped) return;
    if (attempts >= maxAttempts) {
      fail('Task timed out waiting for results. Please check its status again later.');
      return;
    }
    attempts += 1;
    try {
      const { status, result, error } = await request(controller.signal);
      if (stopped) return;
      if (status === 'completed') {
        stop();
        onComplete?.(result ?? {});
        return;
      }
      if (status === 'failed' || status === 'cancelled') {
        fail(error || (status === 'cancelled' ? 'Task was cancelled.' : 'Task execution failed.'));
        return;
      }
    } catch (error) {
      if (stopped) return;
      fail(error?.userFriendlyMessage || error?.message || 'Error checking task status.');
      return;
    }
    timer = setTimeout(tick, intervalMs);
  };
  timer = setTimeout(tick, intervalMs);
  return stop;
};
