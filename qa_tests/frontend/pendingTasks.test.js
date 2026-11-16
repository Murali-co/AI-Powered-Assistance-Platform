import { beforeEach, describe, expect, it } from 'vitest';
import { clearPendingTask, ownedRouteState, readPendingTask, writePendingTask } from '../../frontend/src/utils/pendingTasks';

const first = '11111111-1111-4111-8111-111111111111';
const second = '22222222-2222-4222-8222-222222222222';
let values;
let storage;
beforeEach(() => {
  values = new Map();
  storage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
});

describe('owned pending tasks', () => {
  it('restores an opaque task across reload without sharing it with another account', () => {
    writePendingTask(1, 'live_search', first, null, storage);
    expect(readPendingTask(1, 'live_search', storage)?.jobId).toBe(first);
    expect(readPendingTask(2, 'live_search', storage)).toBeNull();
  });
  it('an older callback cannot erase a newer task', () => {
    writePendingTask(1, 'live_search', second, null, storage);
    clearPendingTask(1, 'live_search', first, storage);
    expect(readPendingTask(1, 'live_search', storage)?.jobId).toBe(second);
    clearPendingTask(1, 'live_search', second, storage);
    expect(readPendingTask(1, 'live_search', storage)).toBeNull();
  });
  it('stores only public listing context, never generated private content', () => {
    const saved = writePendingTask(1, 'application_draft', first, { id: 'listing', title: 'Engineer', cover_letter: 'PRIVATE', resume_text: 'PRIVATE', token: 'PRIVATE' }, storage);
    expect(saved.context).toEqual({ id: 'listing', title: 'Engineer' });
    expect([...values.values()].join()).not.toContain('PRIVATE');
  });
  it('rejects malformed, expired and corrupt records', () => {
    expect(writePendingTask(1, 'live_search', 'invalid', null, storage)).toBeNull();
    writePendingTask(1, 'live_search', first, null, storage);
    const key = [...values.keys()][0];
    const entry = JSON.parse(values.get(key));
    storage.setItem(key, JSON.stringify({ ...entry, createdAt: Date.now() - 25 * 3600000 }));
    expect(readPendingTask(1, 'live_search', storage)).toBeNull();
    storage.setItem(key, 'invalid-json');
    expect(readPendingTask(1, 'live_search', storage)).toBeNull();
  });
  it('optional browser storage does not prevent in-memory polling', () => {
    const blocked = { setItem: () => { throw new Error('Storage blocked'); }, getItem: () => { throw new Error('Storage blocked'); } };
    expect(writePendingTask(1, 'live_search', first, null, blocked)?.jobId).toBe(first);
    expect(readPendingTask(1, 'live_search', blocked)).toBeNull();
  });
  it('private browser history belongs to its original account', () => {
    expect(ownedRouteState({ ownerId: 1, package: 'private' }, 2)).toBeNull();
    expect(ownedRouteState({ package: 'unowned legacy data' }, 1)).toBeNull();
    const state = { ownerId: 1, package: 'private' };
    expect(ownedRouteState(state, 1)).toBe(state);
  });
});
