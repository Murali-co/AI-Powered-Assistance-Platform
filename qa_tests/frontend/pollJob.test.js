import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { pollJob } from '../../frontend/src/utils/pollJob';

describe('background task polling', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('waits for slow requests instead of overlapping them', async () => {
    let resolve;
    const request = vi.fn(() => new Promise(r => { resolve = r; }));
    const done = vi.fn();
    pollJob(request, done, vi.fn(), 10);
    await vi.advanceTimersByTimeAsync(100);
    expect(request).toHaveBeenCalledTimes(1);
    resolve({ status: 'completed', result: { count: 0 } });
    await vi.advanceTimersByTimeAsync(100);
    expect(done).toHaveBeenCalledWith({ count: 0 });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('aborts in-flight requests and suppresses callbacks on cleanup', async () => {
    let resolve;
    let signal;
    const done = vi.fn();
    const stop = pollJob(s => {
      signal = s;
      return new Promise(r => { resolve = r; });
    }, done, vi.fn(), 10);
    await vi.advanceTimersByTimeAsync(10);
    stop();
    expect(signal.aborted).toBe(true);
    resolve({ status: 'completed' });
    await vi.advanceTimersByTimeAsync(100);
    expect(done).not.toHaveBeenCalled();
  });

  it.each(['failed', 'cancelled'])('stops on %s', async status => {
    const request = vi.fn().mockResolvedValue({ status });
    const fail = vi.fn();
    pollJob(request, vi.fn(), fail, 10);
    await vi.advanceTimersByTimeAsync(100);
    expect(request).toHaveBeenCalledTimes(1);
    expect(fail).toHaveBeenCalledTimes(1);
  });

  it('bounds attempts and reports timeout once', async () => {
    const request = vi.fn().mockResolvedValue({ status: 'processing' });
    const fail = vi.fn();
    pollJob(request, vi.fn(), fail, 10, 2);
    await vi.advanceTimersByTimeAsync(100);
    expect(request).toHaveBeenCalledTimes(2);
    expect(fail).toHaveBeenCalledTimes(1);
    expect(fail.mock.calls[0][0]).toContain('timed out');
  });

  it('reconnects after a temporary API restart without overlapping requests', async () => {
    const unavailable = Object.assign(new Error('Unavailable'), { response: { status: 503 } });
    const request = vi.fn().mockRejectedValueOnce(unavailable).mockResolvedValue({ status: 'completed', result: { count: 2 } });
    const done = vi.fn();
    const fail = vi.fn();
    pollJob(request, done, fail, 10);
    await vi.advanceTimersByTimeAsync(100);
    expect(done).toHaveBeenCalledWith({ count: 2 });
    expect(fail).not.toHaveBeenCalled();
  });

  it('bounds repeated outages while retaining the right to resume a saved task', async () => {
    const request = vi.fn().mockRejectedValue(Object.assign(new Error('Offline'), { isAxiosError: true }));
    const fail = vi.fn();
    pollJob(request, vi.fn(), fail, 10);
    await vi.advanceTimersByTimeAsync(1000);
    expect(request).toHaveBeenCalledTimes(5);
    expect(fail.mock.calls[0][1]).toEqual({ retryable: true });
  });
});
