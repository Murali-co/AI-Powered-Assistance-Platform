import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import toast from 'react-hot-toast';
import apiClient from '../api/client';
import { getSafeExternalUrl } from '../utils/urlSecurity';

export const AppliedJobs = () => {
  const { isAuthenticated } = useAuth();
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [skip, setSkip] = useState(0);
  const [limit] = useState(20);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchApplications();
  }, [isAuthenticated, filter, skip]);

  const fetchApplications = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get('/apply/history');
      setApplications(res.data || []);
      setTotalCount(res.data?.length || 0);
    } catch (err) {
      toast.error('Failed to fetch applications');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (appId, newStatus) => {
    try {
      await apiClient.patch(`/apply/${appId}/status?new_status=${newStatus}`);
      toast.success(`Status updated to ${newStatus}`);
      fetchApplications();
    } catch (err) {
      toast.error('Failed to update status');
    }
  };

  const filteredApps = applications.filter(app => {
    const title = app.job_title || app.title || '';
    const company = app.company || app.company_name || '';
    const matchesSearch = title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          company.toLowerCase().includes(searchTerm.toLowerCase());
    if (filter === 'all') return matchesSearch;
    return matchesSearch && app.status === filter;
  });

  const paginatedApps = filteredApps.slice(skip, skip + limit);

  const statusColors = {
    applied: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    offered: 'bg-green-500/20 text-green-400 border-green-500/30',
    rejected: 'bg-red-500/20 text-red-400 border-red-500/30',
    interview_scheduled: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">My Applications</h1>
          <p className="text-slate-400">Track all your job applications in one place</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <div className="text-slate-400 text-sm mb-1">Total Applications</div>
            <div className="text-3xl font-bold text-white">{totalCount}</div>
          </div>
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <div className="text-slate-400 text-sm mb-1">Applied</div>
            <div className="text-3xl font-bold text-yellow-400">
              {applications.filter(a => a.status === 'applied').length}
            </div>
          </div>
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <div className="text-slate-400 text-sm mb-1">Offered</div>
            <div className="text-3xl font-bold text-green-400">
              {applications.filter(a => a.status === 'offered').length}
            </div>
          </div>
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <div className="text-slate-400 text-sm mb-1">Rejected</div>
            <div className="text-3xl font-bold text-red-400">
              {applications.filter(a => a.status === 'rejected').length}
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="mb-6 flex flex-col md:flex-row gap-4">
          <input
            type="text"
            placeholder="Search by job title or company..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1 px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:border-purple-500"
          />
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value);
              setSkip(0);
            }}
            className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
          >
            <option value="all">All Statuses</option>
            <option value="applied">Applied</option>
            <option value="interview_scheduled">Interviewing</option>
            <option value="offered">Offered</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>

        {/* Applications List */}
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
            <p className="text-slate-400 mt-4">Loading applications...</p>
          </div>
        ) : filteredApps.length === 0 ? (
          <div className="bg-slate-800 rounded-lg p-12 border border-slate-700 text-center">
            <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h3 className="text-xl font-semibold text-white mb-2">No Applications Yet</h3>
            <p className="text-slate-400">Start applying for jobs to see them here!</p>
          </div>
        ) : (
          <div className="space-y-4">
            {paginatedApps.map((app) => (
              <div key={app.id} className="bg-slate-800 rounded-lg p-6 border border-slate-700 hover:border-purple-500/50 transition-colors">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-white">{app.job_title || app.title}</h3>
                    <p className="text-purple-400 font-medium">{app.company}</p>
                    {app.location && (
                      <p className="text-slate-400 text-sm mt-1">📍 {app.location}</p>
                    )}
                    <p className="text-slate-500 text-sm mt-2">
                      Applied: {new Date(app.applied_at || app.applied_date).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="flex flex-col gap-2 items-start md:items-end">
                    <div className={`px-3 py-1 rounded-full text-sm font-medium border ${statusColors[app.status] || statusColors.applied}`}>
                      {app.status === 'interview_scheduled' ? 'Interviewing' :
                       app.status === 'offered' ? 'Offered' :
                       app.status === 'rejected' ? 'Rejected' : 'Applied'}
                    </div>
                    <select
                      value={app.status}
                      onChange={(e) => updateStatus(app.id, e.target.value)}
                      className="px-3 py-1 bg-slate-700 border border-slate-600 rounded text-sm text-slate-300 focus:outline-none focus:border-purple-500"
                    >
                      <option value="applied">Applied</option>
                      <option value="interview_scheduled">Interviewing</option>
                      <option value="offered">Offered</option>
                      <option value="rejected">Rejected</option>
                    </select>
                  </div>
                </div>

                {app.cover_letter && (
                  <div className="mt-4 pt-4 border-t border-slate-700">
                    <p className="text-slate-400 text-sm mb-2">Cover Letter:</p>
                    <p className="text-slate-300 text-sm line-clamp-2">{app.cover_letter}</p>
                  </div>
                )}

                {app.notes && (
                  <div className="mt-2">
                    <p className="text-slate-400 text-sm mb-1">Notes:</p>
                    <p className="text-slate-300 text-sm">{app.notes}</p>
                  </div>
                )}

                {(() => {
                  const safeJobUrl = getSafeExternalUrl(app.job_url);
                  return safeJobUrl ? (
                    <div className="mt-4">
                      <a
                        href={safeJobUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-purple-400 hover:text-purple-300 text-sm font-medium inline-flex items-center gap-1"
                      >
                        View Job Posting →
                      </a>
                    </div>
                  ) : null;
                })()}
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {filteredApps.length > limit && (
          <div className="flex justify-center items-center gap-4 mt-8">
            <button
              onClick={() => setSkip(Math.max(0, skip - limit))}
              disabled={skip === 0}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
            >
              ← Previous
            </button>
            <span className="text-slate-400">
              {skip / limit + 1} / {Math.ceil(filteredApps.length / limit)}
            </span>
            <button
              onClick={() => setSkip(skip + limit)}
              disabled={skip + limit >= filteredApps.length}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default AppliedJobs;
