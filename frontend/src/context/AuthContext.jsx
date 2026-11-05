import React, { createContext, useState, useEffect, useContext } from 'react';
import apiClient, { setAccessToken, clearAccessToken } from '../api/client';

const AuthContext = createContext(null);

const formatAuthError = (error, defaultMsg) => {
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

  // Restore session on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const response = await apiClient.get('/auth/me');
        setUser(response.data);
      } catch (error) {
        clearAccessToken();
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const login = async (email, password) => {
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
    try {
      await apiClient.post('/auth/logout');
    } catch (error) {
      // Do not log tokens or secrets
    } finally {
      clearAccessToken();
      setUser(null);
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
      clearAccessToken();
      setUser(null);
      throw formatAuthError(error, "Session refresh failed.");
    }
  };

  const value = {
    user,
    loading,
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
