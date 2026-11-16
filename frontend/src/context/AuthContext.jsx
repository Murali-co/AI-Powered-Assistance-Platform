import React, { createContext, useState, useEffect, useContext, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import apiClient, { setAccessToken, clearAccessToken } from '../api/client';

const AuthContext = createContext(null);

const formatAuthError = (error, defaultMsg) => {
  if (error?.isAxiosError && !error.response) return 'Cannot reach the server. Check the connection and try again.';
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(d => d.msg || d.message || JSON.stringify(d)).join(', ');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }
  return defaultMsg;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState(null);
  const restoreRequest = useRef(null);
  const queryClient = useQueryClient();

  const restoreSession = useCallback(async () => {
    restoreRequest.current?.abort();
    const controller = new AbortController();
    restoreRequest.current = controller;
    setLoading(true);
    setSessionError(null);
    try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const response = await apiClient.get('/auth/me', { signal: controller.signal });
          if (!controller.signal.aborted) setUser(response.data);
          return;
        } catch (error) {
          if (controller.signal.aborted) return;
          if ([401, 403].includes(error.response?.status)) {
            clearAccessToken();
            setUser(null);
            return;
          }
          if (attempt === 2) throw error;
          await new Promise(resolve => {
            const timer = setTimeout(resolve, 1000 * (attempt + 1));
            controller.signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, { once: true });
          });
          if (controller.signal.aborted) return;
        }
      }
    } catch {
      if (!controller.signal.aborted) setSessionError('The server is currently unavailable. Your session has not been cleared.');
    } finally {
      if (!controller.signal.aborted && restoreRequest.current === controller) setLoading(false);
    }
  }, []);
  useEffect(() => {
    restoreSession();
    return () => restoreRequest.current?.abort();
  }, [restoreSession]);

  const login = async (email, password) => {
    restoreRequest.current?.abort();
    setSessionError(null);
    setLoading(true);
    try {
      const response = await apiClient.post('/auth/login', { email: email.trim().toLowerCase(), password });
      if (response.data?.requires_2fa) {
        setLoading(false);
        return { requires_2fa: true, pending_token: response.data.pending_token };
      }

      const { access_token } = response.data;
      if (access_token) {
        setAccessToken(access_token);
      }
      
      // Fetch user details
      const userRes = await apiClient.get('/auth/me');
      setUser(userRes.data);
      setLoading(false);
      return userRes.data;
    } catch (error) {
      setLoading(false);
      throw formatAuthError(error, "Invalid credentials. Please try again.");
    }
  };

  const verify2FA = async (pendingToken, code) => {
    restoreRequest.current?.abort();
    setSessionError(null);
    setLoading(true);
    try {
      const response = await apiClient.post('/auth/2fa/verify', {
        pending_token: pendingToken,
        code,
      });
      const { access_token } = response.data;
      if (access_token) {
        setAccessToken(access_token);
      }
      const userRes = await apiClient.get('/auth/me');
      setUser(userRes.data);
      setLoading(false);
      return userRes.data;
    } catch (error) {
      setLoading(false);
      throw formatAuthError(error, "2FA verification failed.");
    }
  };

  const register = async (email, password, fullName) => {
    restoreRequest.current?.abort();
    setSessionError(null);
    setLoading(true);
    try {
      const response = await apiClient.post('/auth/register', {
        email: email.trim().toLowerCase(),
        password,
        full_name: fullName.trim(),
      });
      setLoading(false);
      return response.data;
    } catch (error) {
      setLoading(false);
      throw formatAuthError(error, "Registration failed. Try again.");
    }
  };

  const logout = async () => {
    restoreRequest.current?.abort();
    try {
      await apiClient.post('/auth/logout');
    } catch (error) {
      // Do not log tokens or secrets
    } finally {
      clearAccessToken();
      setUser(null);
      setSessionError(null);
      setLoading(false);
      try {
        queryClient.cancelQueries();
        queryClient.clear();
      } catch (e) {
        // Safe fallback if queryClient unmounted
        void e;
      }
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('ai_powered_assistance_platform_active_interview_session');
          sessionStorage.removeItem('active_interview_session');
          sessionStorage.removeItem('auth_redirect_target');
          const keysToRemove = [];
          for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);
            if (k && (k.startsWith('draft_') || k.startsWith('interview_') || k.includes('ai_powered_assistance_platform'))) {
              keysToRemove.push(k);
            }
          }
          keysToRemove.forEach(k => localStorage.removeItem(k));
        }
      } catch (e) {
        // Safe fallback for restricted storage environments
        void e;
      }
    }
  };

  const refreshToken = async () => {
    try {
      const response = await apiClient.post('/auth/refresh');
      const { access_token } = response.data;
      if (access_token) {
        setAccessToken(access_token);
      }
      return access_token;
    } catch (error) {
      if ([401, 403].includes(error.response?.status)) {
        clearAccessToken();
        setUser(null);
      }
      throw formatAuthError(error, "Session refresh failed.");
    }
  };

  const value = {
    user,
    loading,
    sessionError,
    restoreSession,
    login,
    verify2FA,
    register,
    logout,
    refreshToken,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
