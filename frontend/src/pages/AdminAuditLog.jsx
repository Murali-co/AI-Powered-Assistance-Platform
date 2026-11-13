import React, { useState, useEffect, useCallback } from 'react';
import apiClient from '../api/client';
import toast from 'react-hot-toast';
import { LoadingSpinner } from '../components/LoadingSpinner';

const EVENT_TYPES = [
  { label: 'All Event Types', value: '' },
  { label: 'Login Success', value: 'login_success' },
  { label: 'Login Failed', value: 'login_failed' },
  { label: 'Account Locked', value: 'account_locked' },
  { label: '2FA Enabled', value: '2fa_enabled' },
  { label: '2FA Disabled', value: '2fa_disabled' },
  { label: '2FA Challenge Issued', value: '2fa_challenge_issued' },
  { label: 'Sessions Revoked', value: 'sessions_revoked' },
  { label: 'Password Reset Requested', value: 'password_reset_requested' },
  { label: 'Password Reset Completed', value: 'password_reset_completed' },
  { label: 'Admin Action', value: 'admin_action' },
];

const getBadgeStyle = (eventType) => {
  switch (eventType) {
    case 'login_success':
    case '2fa_enabled':
    case 'password_reset_completed':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    case 'login_failed':
    case 'account_locked':
      return 'bg-red-500/10 text-red-400 border-red-500/30';
    case '2fa_challenge_issued':
    case '2fa_disabled':
    case 'password_reset_requested':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
    case 'admin_action':
      return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
    default:
      return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30';
  }
};

export const AdminAuditLog = () => {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [eventType, setEventType] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const fetchAuditLogs = useCallback(async (targetPage = 1) => {
    setLoading(true);
    try {
      const params = {
        page: targetPage,
        per_page: perPage,
      };
      if (eventType) params.event_type = eventType;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;

      const res = await apiClient.get('/auth/admin/audit-log', { params });
      setLogs(res.data?.logs || []);
      setTotal(res.data?.total || 0);
      setPage(res.data?.page || 1);
      setTotalPages(res.data?.total_pages || 1);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to fetch audit logs.');
    } finally {
      setLoading(false);
    }
  }, [eventType, startDate, endDate, perPage]);

  useEffect(() => {
    fetchAuditLogs(1);
  }, [fetchAuditLogs]);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-dark-50 flex items-center space-x-2">
            <span>📊</span>
            <span>Security Audit Log</span>
          </h1>
          <p className="text-xs text-dark-400 mt-1">
            Admin-only audit trail for system authentication events, security incidents, and account activity.
          </p>
        </div>
        <button
          onClick={() => fetchAuditLogs(page)}
          className="px-3.5 py-2 rounded-xl border border-dark-700 bg-dark-900 hover:bg-dark-800 text-dark-200 text-xs font-bold transition self-start sm:self-auto flex items-center space-x-1.5"
        >
          <span>🔄</span>
          <span>Refresh</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="glass-panel border border-dark-800 rounded-2xl p-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="text-[11px] font-bold text-dark-300 block mb-1">Event Type</label>
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="w-full p-2.5 bg-dark-900 border border-dark-800 focus:border-indigo-500 rounded-xl outline-none text-xs text-dark-100 font-semibold"
          >
            {EVENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-[11px] font-bold text-dark-300 block mb-1">Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full p-2 bg-dark-900 border border-dark-800 focus:border-indigo-500 rounded-xl outline-none text-xs text-dark-100 font-semibold"
          />
        </div>

        <div>
          <label className="text-[11px] font-bold text-dark-300 block mb-1">End Date</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full p-2 bg-dark-900 border border-dark-800 focus:border-indigo-500 rounded-xl outline-none text-xs text-dark-100 font-semibold"
          />
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="glass-panel border border-dark-800 rounded-2xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="py-12 flex justify-center">
            <LoadingSpinner text="Loading audit log entries..." />
          </div>
        ) : logs.length === 0 ? (
          <div className="py-12 text-center text-dark-400 text-xs font-semibold">
            No audit log entries match the selected filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-dark-950/80 border-b border-dark-800 text-[11px] uppercase tracking-wider font-bold text-dark-400">
                <tr>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Event Type</th>
                  <th className="py-3 px-4">User ID</th>
                  <th className="py-3 px-4">IP Address</th>
                  <th className="py-3 px-4">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-800/60 font-medium">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-dark-900/40 transition">
                    <td className="py-3 px-4 text-dark-300 whitespace-nowrap">
                      {new Date(log.created_at + (log.created_at?.endsWith('Z') ? '' : 'Z')).toLocaleString()}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${getBadgeStyle(log.event_type)}`}>
                        {log.event_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-dark-200 font-mono">
                      {log.user_id ? `#${log.user_id}` : '-'}
                    </td>
                    <td className="py-3 px-4 text-dark-300 font-mono">
                      {log.ip_address || '-'}
                    </td>
                    <td className="py-3 px-4 text-dark-200 max-w-md truncate">
                      {log.detail || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        <div className="p-4 bg-dark-950/60 border-t border-dark-800 flex items-center justify-between">
          <span className="text-xs text-dark-400 font-medium">
            Showing <strong className="text-dark-200">{logs.length}</strong> of <strong className="text-dark-200">{total}</strong> events
          </span>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => fetchAuditLogs(page - 1)}
              disabled={page <= 1 || loading}
              className="px-3 py-1.5 rounded-xl border border-dark-800 text-xs font-bold text-dark-300 hover:text-dark-50 disabled:opacity-40 transition"
            >
              Previous
            </button>
            <span className="text-xs text-dark-400 px-2 font-bold">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => fetchAuditLogs(page + 1)}
              disabled={page >= totalPages || loading}
              className="px-3 py-1.5 rounded-xl border border-dark-800 text-xs font-bold text-dark-300 hover:text-dark-50 disabled:opacity-40 transition"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminAuditLog;
