import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const getCookie = (name) => {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : '';
};

export const formatApiErrorMessage = (error, fallback = 'An unexpected error occurred.') => {
  if (!error) return fallback;

  // Network or connection errors
  if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
    return 'The request timed out waiting for the server. The local AI model may be processing a heavy task.';
  }

  if (error.code === 'ERR_NETWORK' || !error.response) {
    return 'Cannot connect to AI Powered Assistance Platform backend. Please check that the server is running on http://localhost:8000.';
  }

  const { status, data } = error.response;

  // Extract backend detail message safely
  let serverDetail = '';
  if (typeof data?.detail === 'string') {
    serverDetail = data.detail;
  } else if (Array.isArray(data?.detail)) {
    serverDetail = data.detail.map((d) => d.msg || d.message || JSON.stringify(d)).join(', ');
  } else if (data?.message && typeof data.message === 'string') {
    serverDetail = data.message;
  }

  // Never display internal tracebacks or secrets
  if (serverDetail && (serverDetail.includes('Traceback') || serverDetail.includes('File "/'))) {
    serverDetail = 'A server error occurred during request processing.';
  }

  if (status === 401) {
    return serverDetail || 'Session expired. Please log in again.';
  }
  if (status === 403) {
    return serverDetail || 'Access forbidden. Please check your permissions.';
  }
  if (status === 429) {
    return serverDetail || 'Rate limit exceeded. Please wait a few moments before trying again.';
  }
  if (status === 503) {
    return serverDetail || 'Service temporarily unavailable. Required database or local AI service may be starting up.';
  }
  if (status >= 500) {
    return serverDetail || 'Internal server error. Please try again later.';
  }

  return serverDetail || fallback;
};

// Default bounded timeout for standard CRUD requests (60 seconds)
export const DEFAULT_REQUEST_TIMEOUT = 60000;

// Extended bounded timeout for AI / LLM requests (180 seconds) (R2 / M8)
// Resolves mismatch between the backend 120s OLLAMA_TIMEOUT and browser timeout
export const AI_REQUEST_TIMEOUT = 180000;

export const AI_ENDPOINT_PATTERNS = [
  '/resume/analyze',
  '/resume/ats',
  '/resume/tailor',
  '/resume/cover-letter',
  '/copilot',
  '/interview',
  '/llm',
  '/orchestrator',
  '/apply',
  '/skill-gap',
  '/market',
];

const apiClient = axios.create({
  baseURL: API_URL,
  timeout: DEFAULT_REQUEST_TIMEOUT,
  withCredentials: true,
});

// In-memory access token storage (M11: prevent XSS token theft from persistent localStorage)
let inMemoryAccessToken = null;

export const setAccessToken = (token) => {
  inMemoryAccessToken = token || null;
  if (typeof window !== 'undefined') {
    localStorage.removeItem('token');
  }
};

export const getAccessToken = () => inMemoryAccessToken;

export const clearAccessToken = () => {
  inMemoryAccessToken = null;
  if (typeof window !== 'undefined') {
    localStorage.removeItem('token');
  }
};

apiClient.interceptors.request.use(
  (config) => {
    if (inMemoryAccessToken) {
      config.headers.Authorization = `Bearer ${inMemoryAccessToken}`;
    }

    // Extended timeout for AI / LLM endpoints to eliminate frontend/backend timeout mismatch (R2 / M8)
    const requestUrl = config.url || '';
    const isAiRequest = config.isAiRequest || AI_ENDPOINT_PATTERNS.some((pattern) => requestUrl.includes(pattern));
    if (isAiRequest && (!config.timeout || config.timeout === DEFAULT_REQUEST_TIMEOUT)) {
      config.timeout = AI_REQUEST_TIMEOUT;
    }

    const method = (config.method || 'get').toLowerCase();
    const isStateChangingRequest = ['post', 'put', 'patch', 'delete'].includes(method);
    const csrfToken = getCookie('csrf_token');

    if (isStateChangingRequest && csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Single-flight refresh state and queue (H1)
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Endpoints that must NEVER trigger recursive token refresh
const EXCLUDED_AUTH_ENDPOINTS = [
  '/auth/login',
  '/auth/refresh',
  '/auth/logout',
  '/auth/register',
  '/auth/2fa/verify',
  '/auth/forgot-password',
  '/auth/reset-password',
  '/auth/verify-email',
  '/auth/resend-verification'
];

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    error.userFriendlyMessage = formatApiErrorMessage(error);

    const originalRequest = error.config;
    if (!originalRequest) {
      return Promise.reject(error);
    }

    const is401 = error.response && error.response.status === 401;
    const requestUrl = originalRequest.url || '';
    const isExcludedEndpoint = EXCLUDED_AUTH_ENDPOINTS.some((endpoint) =>
      requestUrl.includes(endpoint)
    );

    // If not a 401, or is an excluded auth endpoint, or already retried once: do not attempt refresh
    if (!is401 || isExcludedEndpoint || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Guard: retry each original request no more than once
    originalRequest._retry = true;

    // If refresh is already in progress, join the queue and wait for the single in-flight refresh to complete
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then((token) => {
          if (token) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return apiClient(originalRequest);
        })
        .catch((err) => Promise.reject(err));
    }

    // Begin single-flight refresh operation
    isRefreshing = true;

    try {
      const csrfToken = getCookie('csrf_token');
      // Direct unintercepted axios call to prevent circular interceptor loops
      const refreshResponse = await axios.post(
        `${API_URL}/auth/refresh`,
        {},
        {
          withCredentials: true,
          headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
        }
      );

      const newToken = refreshResponse.data?.access_token;
      if (newToken) {
        setAccessToken(newToken);
        apiClient.defaults.headers.common.Authorization = `Bearer ${newToken}`;
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
      }

      processQueue(null, newToken);
      return apiClient(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      clearAccessToken();

      // Redirect to authentication ONLY when refresh genuinely fails
      if (typeof window !== 'undefined') {
        const publicPaths = ['/auth', '/verify-email', '/resend-verification', '/forgot-password', '/reset-password'];
        const currentPath = window.location.pathname;

        if (!publicPaths.some((p) => currentPath.startsWith(p)) && currentPath !== '/') {
          // Preserve unsaved form data and location:
          try {
            sessionStorage.setItem('auth_redirect_target', window.location.pathname + window.location.search);
          } catch (e) {
            // Ignore storage access restrictions
          }
          window.location.href = `/auth?redirect=${encodeURIComponent(currentPath)}`;
        }
      }

      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default apiClient;
