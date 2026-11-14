import React, { useState, useEffect } from 'react';
import apiClient, { clearAccessToken } from '../api/client';
import toast from 'react-hot-toast';
import { LoadingSpinner } from '../components/LoadingSpinner';

// Helper to parse user-agent strings into readable Device/Browser names
const parseUserAgent = (uaString) => {
  if (!uaString) return { browser: 'Unknown Browser', os: 'Unknown OS', icon: '💻' };

  let browser = 'Browser';
  let os = 'Device';
  let icon = '💻';

  if (uaString.includes('iPhone') || uaString.includes('iPad')) {
    os = 'iOS Device';
    icon = '📱';
  } else if (uaString.includes('Android')) {
    os = 'Android Device';
    icon = '📱';
  } else if (uaString.includes('Macintosh') || uaString.includes('Mac OS')) {
    os = 'macOS';
    icon = '💻';
  } else if (uaString.includes('Windows')) {
    os = 'Windows PC';
    icon = '🖥️';
  } else if (uaString.includes('Linux')) {
    os = 'Linux';
    icon = '🐧';
  }

  if (uaString.includes('Edg/')) browser = 'Edge';
  else if (uaString.includes('Chrome/')) browser = 'Chrome';
  else if (uaString.includes('Firefox/')) browser = 'Firefox';
  else if (uaString.includes('Safari/')) browser = 'Safari';

  return { browser, os, icon };
};

export const SecuritySettings = () => {
  const [sessions, setSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [revokingId, setRevokingId] = useState(null);
  const [revokingOthers, setRevokingOthers] = useState(false);

  // 2FA state
  const [twoFactorStatus, setTwoFactorStatus] = useState(false);
  const [showSetupModal, setShowSetupModal] = useState(false);
  const [showDisableModal, setShowDisableModal] = useState(false);
  const [showBackupCodesModal, setShowBackupCodesModal] = useState(false);

  // Auto-approval state
  const [autoApproveExternal, setAutoApproveExternal] = useState(false);
  const [updatingAutoApprove, setUpdatingAutoApprove] = useState(false);

  // Delete Account state (F-010)
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');

  const [setupData, setSetupData] = useState(null); // { secret, otpauth_url }
  const [totpCode, setTotpCode] = useState('');
  const [disablePassword, setDisablePassword] = useState('');
  const [backupCodes, setBackupCodes] = useState([]);
  const [actionLoading, setActionLoading] = useState(false);

  // Fetch active sessions & 2FA status
  const fetchData = async () => {
    try {
      setLoadingSessions(true);
      const [sessionsRes, userRes] = await Promise.all([
        apiClient.get('/auth/sessions'),
        apiClient.get('/auth/me'),
      ]);
      setSessions(sessionsRes.data || []);
      setTwoFactorStatus(userRes.data?.two_factor_enabled || false);
      setAutoApproveExternal(userRes.data?.auto_approve_external_actions || false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to load security settings.');
    } finally {
      setLoadingSessions(false);
    }
  };

  const handleToggleAutoApprove = async (newValue) => {
    setUpdatingAutoApprove(true);
    try {
      const res = await apiClient.patch('/auth/preferences/auto-approve-external', {
        auto_approve_external_actions: newValue
      });
      setAutoApproveExternal(res.data?.auto_approve_external_actions ?? newValue);
      toast.success(
        newValue
          ? 'Auto-approval for external actions enabled.'
          : 'Auto-approval disabled. External actions require explicit human approval.'
      );
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update auto-approval preference.');
    } finally {
      setUpdatingAutoApprove(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Delete Account action (F-010)
  const handleDeleteAccount = async (e) => {
    e.preventDefault();
    if (!deletePassword) return;
    try {
      setActionLoading(true);
      await apiClient.delete('/auth/account', {
        data: { password: deletePassword }
      });
      toast.success('Your account has been deleted.');
      setShowDeleteModal(false);
      clearAccessToken();
      window.location.href = '/auth';
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete account. Please verify your password.');
    } finally {
      setActionLoading(false);
    }
  };

  // Session actions
  const handleRevokeSession = async (sessionId) => {
    setRevokingId(sessionId);
    try {
      await apiClient.delete(`/auth/sessions/${sessionId}`);
      toast.success('Session revoked successfully.');
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to revoke session.');
    } finally {
      setRevokingId(null);
    }
  };

  const handleRevokeOtherSessions = async () => {
    setRevokingOthers(true);
    try {
      const res = await apiClient.post('/auth/sessions/revoke-others');
      toast.success(res.data?.message || 'Logged out other devices successfully.');
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to revoke other sessions.');
    } finally {
      setRevokingOthers(false);
    }
  };

  // 2FA Actions
  const handleStart2FASetup = async () => {
    setActionLoading(true);
    try {
      const res = await apiClient.post('/auth/2fa/setup');
      setSetupData(res.data);
      setTotpCode('');
      setShowSetupModal(true);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to initiate 2FA setup.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleConfirm2FA = async (e) => {
    e.preventDefault();
    if (!totpCode || totpCode.trim().length !== 6) {
      toast.error('Please enter a 6-digit code.');
      return;
    }
    setActionLoading(true);
    try {
      const res = await apiClient.post('/auth/2fa/confirm', {
        secret: setupData.secret,
        code: totpCode.trim(),
      });
      toast.success('Two-Factor Authentication enabled!');
      setBackupCodes(res.data?.backup_codes || []);
      setShowSetupModal(false);
      setShowBackupCodesModal(true);
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Invalid verification code.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDisable2FA = async (e) => {
    e.preventDefault();
    if (!disablePassword) {
      toast.error('Password is required.');
      return;
    }
    setActionLoading(true);
    try {
      await apiClient.post('/auth/2fa/disable', { password: disablePassword });
      toast.success('Two-factor authentication disabled.');
      setShowDisableModal(false);
      setDisablePassword('');
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to disable 2FA.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRegenerateBackupCodes = async () => {
    setActionLoading(true);
    try {
      const res = await apiClient.post('/auth/2fa/backup-codes/regenerate');
      setBackupCodes(res.data?.backup_codes || []);
      setShowBackupCodesModal(true);
      toast.success('New backup codes generated.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to regenerate backup codes.');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-dark-50 flex items-center space-x-2">
          <span>🛡️</span>
          <span>Security & Sessions</span>
        </h1>
        <p className="text-xs text-dark-400 mt-1">
          Manage your active device sessions, multi-factor authentication, and account security.
        </p>
      </div>

      {/* Two-Factor Authentication Section */}
      <div className="glass-panel border border-dark-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-dark-800">
          <div>
            <h2 className="text-base font-bold text-dark-50 flex items-center space-x-2">
              <span>🔐</span>
              <span>Two-Factor Authentication (2FA)</span>
            </h2>
            <p className="text-xs text-dark-400 mt-1">
              Add an extra layer of security using an authenticator app (Google Authenticator, Authy, etc.).
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <span
              className={`px-3 py-1 rounded-full text-xs font-bold border ${
                twoFactorStatus
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              }`}
            >
              {twoFactorStatus ? '✓ Enabled' : '⚠ Disabled'}
            </span>
            {twoFactorStatus ? (
              <div className="flex space-x-2">
                <button
                  onClick={handleRegenerateBackupCodes}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded-xl border border-dark-700 bg-dark-900 hover:bg-dark-800 text-dark-200 text-xs font-bold transition"
                >
                  Regenerate Backup Codes
                </button>
                <button
                  onClick={() => setShowDisableModal(true)}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-bold transition"
                >
                  Disable 2FA
                </button>
              </div>
            ) : (
              <button
                onClick={handleStart2FASetup}
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition shadow-md"
              >
                {actionLoading ? 'Loading...' : 'Enable 2FA'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Agent Risk Controls & Auto-Approval Section */}
      <div className="glass-panel border border-dark-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-dark-800">
          <div>
            <h2 className="text-base font-bold text-dark-50 flex items-center space-x-2">
              <span>🤖</span>
              <span>Agent Auto-Approval for External Actions</span>
            </h2>
            <p className="text-xs text-dark-400 mt-1">
              Control whether autonomous agents require human confirmation before executing high-risk external actions.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={() => handleToggleAutoApprove(!autoApproveExternal)}
              disabled={updatingAutoApprove}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                autoApproveExternal ? 'bg-amber-600' : 'bg-dark-700'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  autoApproveExternal ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <span className="text-xs font-bold text-dark-200 min-w-[70px]">
              {updatingAutoApprove ? 'Saving...' : autoApproveExternal ? 'Enabled' : 'Disabled'}
            </span>
          </div>
        </div>

        {/* Warning Callout Box */}
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs leading-relaxed flex items-start space-x-3">
          <span className="text-lg">⚠️</span>
          <div>
            <span className="font-bold text-amber-300 block mb-0.5">Warning</span>
            <span>
              Enabling auto-approval permits the agent to execute irreversible external actions (such as submitting job applications or sending emails) automatically without asking for human approval each time.
            </span>
          </div>
        </div>
      </div>

      {/* Active Sessions Section */}
      <div className="glass-panel border border-dark-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-dark-800">
          <div>
            <h2 className="text-base font-bold text-dark-50 flex items-center space-x-2">
              <span>📱</span>
              <span>Active Sessions & Devices</span>
            </h2>
            <p className="text-xs text-dark-400 mt-1">
              Devices currently logged into your AI Powered Assistance Platform account.
            </p>
          </div>
          {sessions.length > 1 && (
            <button
              onClick={handleRevokeOtherSessions}
              disabled={revokingOthers}
              className="px-3.5 py-2 rounded-xl border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-bold transition shadow-sm self-start sm:self-auto"
            >
              {revokingOthers ? 'Logging out...' : 'Log out all other devices'}
            </button>
          )}
        </div>

        {loadingSessions ? (
          <div className="py-8 flex justify-center">
            <LoadingSpinner text="Fetching active sessions..." />
          </div>
        ) : sessions.length === 0 ? (
          <p className="text-xs text-dark-400 py-4 text-center">No active sessions found.</p>
        ) : (
          <div className="grid gap-3">
            {sessions.map((s) => {
              const { browser, os, icon } = parseUserAgent(s.user_agent);
              return (
                <div
                  key={s.id}
                  className={`p-4 rounded-xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                    s.is_current
                      ? 'bg-indigo-950/20 border-indigo-500/30 shadow-inner'
                      : 'bg-dark-900/40 border-dark-800 hover:border-dark-700'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <span className="text-2xl mt-0.5">{icon}</span>
                    <div className="space-y-0.5">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-dark-100">
                          {browser} on {os}
                        </span>
                        {s.is_current && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-400 border border-indigo-500/40">
                            This Device
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-dark-400 space-x-3 font-medium">
                        <span>IP: {s.ip_address || 'Unknown'}</span>
                        <span>•</span>
                        <span>Logged in: {new Date(s.created_at + (s.created_at?.endsWith('Z') ? '' : 'Z')).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>

                  <div>
                    {s.is_current ? (
                      <span className="text-[11px] text-dark-500 font-semibold italic">
                        Active now
                      </span>
                    ) : (
                      <button
                        onClick={() => handleRevokeSession(s.id)}
                        disabled={revokingId === s.id}
                        className="px-3 py-1.5 rounded-xl border border-red-500/20 bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs font-bold transition"
                      >
                        {revokingId === s.id ? 'Revoking...' : 'Log out device'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Danger Zone: Account Deletion (F-010) */}
      <div className="glass-panel p-6 rounded-2xl border border-red-500/20 bg-red-950/10 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-base font-bold text-red-400 flex items-center space-x-2">
              <span>⚠️</span>
              <span>Danger Zone — Delete Account</span>
            </h2>
            <p className="text-xs text-dark-400 leading-relaxed font-medium">
              Permanently delete your account, profile, uploaded files, and vector embeddings. This action is irreversible.
            </p>
          </div>
          <button
            onClick={() => setShowDeleteModal(true)}
            className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 text-xs font-bold rounded-xl transition flex items-center justify-center space-x-1.5 shrink-0"
          >
            <span>🗑️</span>
            <span>Delete My Account</span>
          </button>
        </div>
      </div>

      {/* 2FA Setup Modal */}
      {showSetupModal && setupData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md glass-panel border border-dark-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-dark-800">
              <h3 className="text-base font-bold text-dark-50 flex items-center space-x-2">
                <span>📲</span>
                <span>Setup Authenticator App</span>
              </h3>
              <button
                onClick={() => setShowSetupModal(false)}
                className="text-dark-400 hover:text-dark-200 text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-dark-400 leading-relaxed font-medium">
              Enter the setup key into your authenticator app (Google Authenticator, Authy, etc.):
            </p>

            <div className="bg-dark-900 border border-dark-800 rounded-xl p-3 text-center space-y-1">
              <span className="text-[10px] uppercase font-bold text-dark-400 block tracking-wider">Secret Key</span>
              <span className="font-mono text-sm font-bold text-indigo-400 select-all tracking-widest">
                {setupData.secret}
              </span>
            </div>

            <form onSubmit={handleConfirm2FA} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-dark-200 block">
                  Enter 6-digit Code from Authenticator:
                </label>
                <input
                  type="text"
                  maxLength={6}
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="123456"
                  className="w-full p-3 bg-dark-900 border border-dark-800 focus:border-indigo-500 rounded-xl outline-none text-center font-mono text-lg tracking-widest text-dark-50 font-bold"
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowSetupModal(false)}
                  className="px-4 py-2 border border-dark-800 text-dark-400 hover:text-dark-200 text-xs font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || totpCode.length !== 6}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-dark-800 text-white text-xs font-bold rounded-xl transition"
                >
                  {actionLoading ? 'Verifying...' : 'Verify & Enable'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Backup Codes Display Modal */}
      {showBackupCodesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md glass-panel border border-dark-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="pb-2 border-b border-dark-800">
              <h3 className="text-base font-bold text-dark-50 flex items-center space-x-2">
                <span>🔑</span>
                <span>Your Single-Use Backup Codes</span>
              </h3>
            </div>

            <p className="text-xs text-dark-300 leading-relaxed font-medium">
              Save these backup codes in a safe place. If you lose access to your authenticator app, each code can be used ONCE to log in.
            </p>

            <div className="grid grid-cols-2 gap-2 bg-dark-900 border border-dark-800 rounded-xl p-3">
              {backupCodes.map((code, idx) => (
                <div key={idx} className="font-mono text-xs font-bold text-emerald-400 text-center p-1 bg-dark-950/60 rounded border border-dark-800 select-all">
                  {code}
                </div>
              ))}
            </div>

            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(backupCodes.join('\n'));
                  toast.success('Backup codes copied to clipboard!');
                }}
                className="px-4 py-2 border border-dark-700 bg-dark-900 text-dark-200 hover:bg-dark-800 text-xs font-bold rounded-xl"
              >
                Copy Codes
              </button>
              <button
                onClick={() => setShowBackupCodesModal(false)}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Disable 2FA Modal */}
      {showDisableModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md glass-panel border border-dark-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-dark-800">
              <h3 className="text-base font-bold text-dark-50 flex items-center space-x-2">
                <span>⚠️</span>
                <span>Disable Two-Factor Authentication</span>
              </h3>
              <button
                onClick={() => setShowDisableModal(false)}
                className="text-dark-400 hover:text-dark-200 text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-dark-400 leading-relaxed font-medium">
              Please enter your current account password to confirm disabling 2FA.
            </p>

            <form onSubmit={handleDisable2FA} className="space-y-4">
              <input
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                placeholder="Enter account password"
                className="w-full p-3 bg-dark-900 border border-dark-800 focus:border-red-500 rounded-xl outline-none text-xs text-dark-50 font-bold"
              />

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowDisableModal(false)}
                  className="px-4 py-2 border border-dark-800 text-dark-400 hover:text-dark-200 text-xs font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !disablePassword}
                  className="px-5 py-2 bg-red-600 hover:bg-red-500 text-white text-xs font-bold rounded-xl transition"
                >
                  {actionLoading ? 'Disabling...' : 'Confirm Disable'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Account Modal (F-010) */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm">
          <div className="w-full max-w-md glass-panel border border-red-500/30 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-dark-800">
              <h3 className="text-base font-bold text-red-400 flex items-center space-x-2">
                <span>⚠️</span>
                <span>Confirm Account Deletion</span>
              </h3>
              <button
                onClick={() => { setShowDeleteModal(false); setDeletePassword(''); }}
                className="text-dark-400 hover:text-dark-200 text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-dark-300 leading-relaxed font-medium">
              This action is permanent. All your resumes, vector profiles, job applications, and active sessions will be deleted immediately.
            </p>

            <form onSubmit={handleDeleteAccount} className="space-y-4">
              <div>
                <label className="text-[11px] font-semibold text-dark-400 block mb-1">
                  Enter your password to confirm deletion:
                </label>
                <input
                  type="password"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  placeholder="Enter account password"
                  className="w-full p-3 bg-dark-900 border border-dark-800 focus:border-red-500 rounded-xl outline-none text-xs text-dark-50 font-bold"
                  autoFocus
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => { setShowDeleteModal(false); setDeletePassword(''); }}
                  className="px-4 py-2 border border-dark-800 text-dark-400 hover:text-dark-200 text-xs font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !deletePassword}
                  className="px-5 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition"
                >
                  {actionLoading ? 'Deleting Account...' : 'Permanently Delete'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default SecuritySettings;
