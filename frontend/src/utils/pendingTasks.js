const TTL = 24 * 60 * 60 * 1000;
const kinds = new Set(['live_search', 'resume_analysis', 'application_draft']);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const keyFor = (ownerId, kind) => Number.isSafeInteger(ownerId) && ownerId > 0 && kinds.has(kind)
  ? `ai-powered-assistance-platform:pending:${ownerId}:${kind}` : null;

export const readPendingTask = (ownerId, kind, storage) => {
  const key = keyFor(ownerId, kind);
  if (!key) return null;
  try {
    storage ??= globalThis.localStorage;
    const entry = JSON.parse(storage.getItem(key));
    if (entry?.ownerId === ownerId && uuid.test(entry.jobId) && Number.isFinite(entry.createdAt)
      && Date.now() - entry.createdAt >= 0 && Date.now() - entry.createdAt < TTL) return entry;
    storage.removeItem(key);
  } catch { /* Restricted/corrupt browser storage must not prevent execution. */ }
  return null;
};

export const writePendingTask = (ownerId, kind, jobId, context = null, storage) => {
  const key = keyFor(ownerId, kind);
  if (!key || !uuid.test(jobId)) return null;
  // Only public listing fields may accompany an opaque task ID. Generated
  // cover letters, resumes and authentication tokens are never stored here.
  const publicContext = context ? Object.fromEntries(['id', 'title', 'company', 'location', 'description', 'url']
    .filter(field => typeof context[field] === 'string').map(field => [field, context[field].slice(0, field === 'description' ? 20000 : 2000)])) : null;
  const entry = { ownerId, jobId, createdAt: Date.now(), context: publicContext };
  try { (storage ?? globalThis.localStorage).setItem(key, JSON.stringify(entry)); } catch { /* In-memory polling still works. */ }
  return entry;
};

export const clearPendingTask = (ownerId, kind, jobId, storage) => {
  const key = keyFor(ownerId, kind);
  if (!key) return;
  try {
    storage ??= globalThis.localStorage;
    if (JSON.parse(storage.getItem(key))?.jobId === jobId) storage.removeItem(key);
  } catch { /* Storage is optional. */ }
};

export const ownedRouteState = (state, ownerId) => ownerId && state?.ownerId === ownerId ? state : null;
