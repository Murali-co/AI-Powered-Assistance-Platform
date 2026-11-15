import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProfile } from '../hooks/useProfile';
import { useJobs } from '../hooks/useJobs';
import { LoadingSpinner } from '../components/LoadingSpinner';
import MarketInsights from '../components/MarketInsights';
import SavedJobsPipeline from '../components/SavedJobsPipeline';
import PendingApprovalCard from '../components/PendingApprovalCard';
import apiClient from '../api/client';
import toast from 'react-hot-toast';
import { getSafeExternalUrl } from '../utils/urlSecurity';

export const Dashboard = () => {
  const navigate = useNavigate();
  const { profile, isLoading: isLoadingProfile, refetch: refetchProfile } = useProfile();
  const { jobs, appHistory, isLoadingJobs, isLoadingHistory } = useJobs();

  // Tab State: 'overview', 'roadmap', 'versions', 'customize', 'admin'
  const [activeTab, setActiveTab] = useState('overview');

  // Overview Data from backend /dashboard/overview
  const [overviewData, setOverviewData] = useState(null);
  const [loadingOverview, setLoadingOverview] = useState(false);

  // Pending Approvals State
  const [pendingWorkflows, setPendingWorkflows] = useState([]);

  // Verified Profile State
  const [_verifiedProfile, setVerifiedProfile] = useState(null);
  const [editSkills, setEditSkills] = useState('');
  const [editText, setEditText] = useState('');
  const [consentLocalOnly, setConsentLocalOnly] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);

  // Versions State
  const [versions, setVersions] = useState([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [previewVersion, setPreviewVersion] = useState(null);
  const [compareData, setCompareData] = useState(null);
  const [compareVersionA, setCompareVersionA] = useState('');
  const [compareVersionB, setCompareVersionB] = useState('');
  const [newVersionLabel, setNewVersionLabel] = useState('');
  const [newVersionRole, setNewVersionRole] = useState('');
  const [isCreatingVersion, setIsCreatingVersion] = useState(false);

  // Roadmap State
  const [roadmap, setRoadmap] = useState([]);
  const [loadingRoadmap, setLoadingRoadmap] = useState(false);

  // Admin Stats State
  const [adminStats, setAdminStats] = useState(null);
  const [loadingAdmin, setLoadingAdmin] = useState(false);

  // Fetch real authenticated dashboard overview
  const fetchOverview = async () => {
    setLoadingOverview(true);
    try {
      const res = await apiClient.get('/dashboard/overview');
      setOverviewData(res.data);
    } catch (err) {
      console.warn('Could not fetch overview endpoint:', err);
    } finally {
      setLoadingOverview(false);
    }
  };

  // Fetch verified profile
  const fetchVerifiedProfile = async () => {
    try {
      const res = await apiClient.get('/profile/verified');
      setVerifiedProfile(res.data);
      if (res.data.skills) {
        setEditSkills(res.data.skills.join(', '));
      }
      if (res.data.consent_settings) {
        setConsentLocalOnly(res.data.consent_settings.local_only ?? true);
      }
    } catch (err) {
      console.warn('Could not fetch verified profile:', err);
    }
  };

  // Fetch versions
  const fetchVersions = async () => {
    setLoadingVersions(true);
    try {
      const res = await apiClient.get('/resume/versions');
      setVersions(res.data || []);
      if (res.data && res.data.length >= 2) {
        setCompareVersionA(res.data[0].id);
        setCompareVersionB(res.data[1].id);
      }
    } catch (err) {
      toast.error('Failed to load resume versions.');
    } finally {
      setLoadingVersions(false);
    }
  };

  // Fetch roadmap
  const fetchRoadmap = async () => {
    setLoadingRoadmap(true);
    try {
      const res = await apiClient.get('/profile/roadmap');
      setRoadmap(res.data.milestones || []);
    } catch (err) {
      toast.error('Failed to load career roadmap.');
    } finally {
      setLoadingRoadmap(false);
    }
  };

  // Fetch admin stats
  const fetchAdminStats = async () => {
    setLoadingAdmin(true);
    try {
      const res = await apiClient.get('/auth/admin/stats');
      setAdminStats(res.data);
    } catch (err) {
      toast.error('Failed to load system diagnostics.');
    } finally {
      setLoadingAdmin(false);
    }
  };

  // Load pending approvals for human-in-the-loop gate
  const fetchPendingApprovals = async () => {
    try {
      const res = await apiClient.get('/orchestrator/workflows');
      const workflows = res.data || [];
      const pendingList = [];
      for (const wf of workflows) {
        if (wf.status === 'AWAITING_APPROVAL') {
          try {
            const tasksRes = await apiClient.get(`/orchestrator/workflows/${wf.workflow_id}/pending-approval`);
            if (tasksRes.data && tasksRes.data.length > 0) {
              for (const pendingTask of tasksRes.data) {
                pendingList.push({
                  workflow_id: wf.workflow_id,
                  goal: wf.goal,
                  pendingTask
                });
              }
            }
          } catch (e) {
            console.error(e);
          }
        }
      }
      setPendingWorkflows(pendingList);
    } catch (err) {
      // Ignore if orchestrator workflows empty
    }
  };

  useEffect(() => {
    fetchOverview();
    fetchPendingApprovals();
  }, []);

  useEffect(() => {
    if (activeTab === 'overview') {
      fetchOverview();
    } else if (activeTab === 'roadmap') {
      fetchRoadmap();
    } else if (activeTab === 'versions') {
      fetchVersions();
    } else if (activeTab === 'customize') {
      fetchVerifiedProfile();
    } else if (activeTab === 'admin') {
      fetchAdminStats();
    }
  }, [activeTab]);

  useEffect(() => {
    if (profile) {
      setEditSkills(prev => prev || (profile.skills ? profile.skills.join(', ') : ''));
      setEditText(profile.resume_text || '');
    }
  }, [profile]);

  const handleSaveVerifiedProfile = async (e) => {
    e.preventDefault();
    setSavingProfile(true);
    try {
      const skillsArray = editSkills
        .split(',')
        .map(s => s.trim())
        .filter(s => s.length > 0);

      await apiClient.post('/profile/verified', {
        skills: skillsArray,
        consent_settings: {
          local_only: consentLocalOnly,
          external_ai: !consentLocalOnly
        }
      });

      await apiClient.post('/resume/profile/edit', {
        skills: skillsArray,
        resume_text: editText
      });

      toast.success('Verified career profile saved with privacy boundaries!');
      refetchProfile();
      fetchOverview();
    } catch (err) {
      toast.error('Failed to save profile updates.');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleCreateVersion = async (e) => {
    e.preventDefault();
    if (!newVersionLabel.trim()) {
      toast.error('Please enter a version name.');
      return;
    }
    setIsCreatingVersion(true);
    try {
      await apiClient.post('/resume/versions/create', {
        version_label: newVersionLabel.trim(),
        target_role: newVersionRole.trim() || 'General'
      });
      toast.success('New resume version created!');
      setNewVersionLabel('');
      setNewVersionRole('');
      fetchVersions();
      fetchOverview();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create resume version.');
    } finally {
      setIsCreatingVersion(false);
    }
  };

  const handlePreviewVersion = async (versionId) => {
    try {
      const res = await apiClient.get(`/resume/versions/${versionId}/preview`);
      setPreviewVersion(res.data);
    } catch (err) {
      toast.error('Failed to preview version.');
    }
  };

  const handleCompareVersions = async () => {
    if (!compareVersionA || !compareVersionB) {
      toast.error('Select two versions to compare.');
      return;
    }
    try {
      const res = await apiClient.post(`/resume/versions/${compareVersionA}/compare?with_version_id=${compareVersionB}`);
      setCompareData(res.data);
    } catch (err) {
      toast.error('Failed to compare versions.');
    }
  };

  const handleDeleteVersion = async (versionId) => {
    if (!window.confirm('Are you sure you want to delete this resume version?')) return;
    try {
      await apiClient.delete(`/resume/versions/${versionId}`);
      toast.success('Resume version deleted.');
      fetchVersions();
      fetchOverview();
      if (previewVersion?.id === versionId) setPreviewVersion(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete version.');
    }
  };

  const handleDownloadVersion = async (versionId) => {
    try {
      const res = await apiClient.get(`/resume/versions/${versionId}/download`);
      const blob = new Blob([res.data.content], { type: 'text/plain;charset=utf-8' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', res.data.filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Resume downloaded!');
    } catch (err) {
      toast.error('Failed to download resume version.');
    }
  };

  const handleToggleMilestone = async (milestoneId, currentStatus) => {
    const nextStatus = currentStatus === 'completed' ? 'pending' : 'completed';
    try {
      await apiClient.post(`/profile/roadmap/milestones/${milestoneId}`, { status: nextStatus });
      setRoadmap(prev => prev.map(m => m.id === milestoneId ? { ...m, status: nextStatus } : m));
      toast.success(`Milestone marked as ${nextStatus === 'completed' ? 'Completed! 🎉' : 'Pending'}`);
      fetchOverview();
    } catch (err) {
      toast.error('Failed to update milestone status.');
    }
  };

  const handleRestoreVersion = async (versionId) => {
    try {
      await apiClient.post(`/resume/versions/restore/${versionId}`);
      toast.success(`Restored Version #${versionId} as active profile!`);
      refetchProfile();
      fetchOverview();
    } catch (err) {
      toast.error('Failed to restore resume version.');
    }
  };

  if (isLoadingProfile || isLoadingJobs || isLoadingHistory || loadingOverview) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-20">
        <LoadingSpinner text="Retrieving authenticated workspace data..." />
      </div>
    );
  }

  const hasResume = profile && profile.resume_text && profile.resume_text.length > 50;
  const skillsCount = overviewData?.profile?.skills_count ?? (profile?.skills ? profile.skills.length : 0);
  const jobsCount = jobs ? jobs.length : 0;
  const appliedCount = overviewData?.application_pipeline?.applied ?? (appHistory ? appHistory.length : 0);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-2xl p-6 sm:p-8 bg-gradient-to-r from-dark-900 via-indigo-950/20 to-dark-900 border border-dark-800 flex justify-between items-center flex-wrap gap-4">
        <div className="space-y-1 relative z-10">
          <div className="flex items-center space-x-2">
            <span className="text-xl">🚀</span>
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Career Hub</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-dark-50 tracking-tight">Professional Career Dashboard</h1>
          <p className="text-xs text-dark-400 max-w-xl">
            Unified career telemetry with ESCO skill intelligence, STAR adaptive coaching, and multi-version resume management.
          </p>
        </div>

        {!hasResume && (
          <button
            onClick={() => navigate('/upload')}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs transition-all shadow-lg relative z-10"
          >
            Upload Your Resume
          </button>
        )}
      </div>

      {/* Tabs Selector */}
      <div className="flex border-b border-dark-800 space-x-6 overflow-x-auto">
        {[
          { id: 'overview', name: 'Dashboard Overview', icon: '🧭' },
          { id: 'roadmap', name: 'Career Roadmap', icon: '🗺️' },
          { id: 'versions', name: 'Resume Versions', icon: '📜' },
          { id: 'customize', name: 'Verified Profile', icon: '🛡️' },
          { id: 'admin', name: 'System Diagnostics', icon: '📊' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`pb-4 text-xs sm:text-sm font-semibold flex items-center space-x-2 border-b-2 transition-all duration-200 whitespace-nowrap ${
              activeTab === tab.id
                ? 'border-indigo-500 text-indigo-400 font-bold'
                : 'border-transparent text-dark-400 hover:text-dark-200'
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.name}</span>
          </button>
        ))}
      </div>

      {/* TAB 1: Overview */}
      {activeTab === 'overview' && (
        <div className="space-y-8">
          {/* Pending Approvals Banner */}
          {pendingWorkflows.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xs font-bold text-amber-300 flex items-center space-x-2">
                <span>⚠️</span>
                <span>Pending Agent Action Approvals ({pendingWorkflows.length})</span>
              </h2>
              {pendingWorkflows.map((item, idx) => (
                <PendingApprovalCard
                  key={idx}
                  workflowId={item.workflow_id}
                  pendingTask={item.pendingTask}
                  onActionComplete={() => fetchPendingApprovals()}
                />
              ))}
            </div>
          )}

          {/* Authenticated Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div className="glass-panel border border-dark-800 rounded-2xl p-5 flex items-center space-x-4">
              <span className="text-2xl p-3 bg-dark-900 rounded-xl">📄</span>
              <div>
                <p className="text-[10px] text-dark-400 font-bold uppercase tracking-wider">Verified Skills</p>
                <p className="text-base font-extrabold text-dark-100 mt-0.5">{skillsCount} Indexed</p>
              </div>
            </div>

            <div className="glass-panel border border-dark-800 rounded-2xl p-5 flex items-center space-x-4">
              <span className="text-2xl p-3 bg-dark-900 rounded-xl">🗣️</span>
              <div>
                <p className="text-[10px] text-dark-400 font-bold uppercase tracking-wider">Interview Coach</p>
                <p className="text-base font-extrabold text-dark-100 mt-0.5">
                  {overviewData?.interview_stats?.latest_score ? `${overviewData.interview_stats.latest_score}% Score` : 'Ready to Start'}
                </p>
              </div>
            </div>

            <div className="glass-panel border border-dark-800 rounded-2xl p-5 flex items-center space-x-4">
              <span className="text-2xl p-3 bg-dark-900 rounded-xl">🗺️</span>
              <div>
                <p className="text-[10px] text-dark-400 font-bold uppercase tracking-wider">Roadmap Progress</p>
                <p className="text-base font-extrabold text-dark-100 mt-0.5">
                  {overviewData?.roadmap_stats?.completed || 0}/{overviewData?.roadmap_stats?.total_milestones || 0} Milestones
                </p>
              </div>
            </div>

            <div className="glass-panel border border-dark-800 rounded-2xl p-5 flex items-center space-x-4">
              <span className="text-2xl p-3 bg-dark-900 rounded-xl">🚀</span>
              <div>
                <p className="text-[10px] text-dark-400 font-bold uppercase tracking-wider">Applications / Jobs</p>
                <p className="text-base font-extrabold text-dark-100 mt-0.5">{appliedCount} Applied • {jobsCount} Jobs</p>
              </div>
            </div>
          </div>

          {/* Recommended Jobs with ESCO Matching Intelligence */}
          {overviewData?.recommended_jobs && overviewData.recommended_jobs.length > 0 && (
            <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-4">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="text-sm font-bold text-dark-100">Recommended Jobs & ESCO Match Breakdown</h3>
                  <p className="text-[11px] text-dark-400">Two-stage semantic retrieval and canonical skill overlap analysis</p>
                </div>
                <button
                  onClick={() => navigate('/match')}
                  className="text-xs text-indigo-400 hover:text-indigo-300 font-bold"
                >
                  View All Matches →
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {overviewData.recommended_jobs.map((job) => (
                  <div key={job.id} className="p-4 bg-dark-900/60 border border-dark-800 rounded-xl space-y-3">
                    <div className="flex justify-between items-start">
                      <div>
                        <h4 className="text-xs font-bold text-dark-100">{job.title}</h4>
                        <p className="text-[10px] text-dark-400">{job.company} • {job.location || 'Remote'}</p>
                      </div>
                      <span className="text-xs font-extrabold px-2 py-0.5 bg-indigo-950 text-indigo-300 border border-indigo-500/20 rounded-md">
                        {job.match_score}% Match
                      </span>
                    </div>

                    <div className="space-y-1.5 text-[10px]">
                      {job.matched_skills?.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1">
                          <span className="text-dark-400 font-semibold">Matched:</span>
                          {job.matched_skills.slice(0, 4).map(s => (
                            <span key={s} className="px-1.5 py-0.5 rounded bg-emerald-950/40 text-emerald-400 border border-emerald-500/20">
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                      {job.missing_skills?.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1">
                          <span className="text-dark-400 font-semibold">Missing:</span>
                          {job.missing_skills.slice(0, 3).map(s => (
                            <span key={s} className="px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-400 border border-amber-500/20">
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Saved Jobs Pipeline & Market Insights */}
          <SavedJobsPipeline />
          <MarketInsights />
        </div>
      )}

      {/* TAB 2: Career Roadmap */}
      {activeTab === 'roadmap' && (
        <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-6">
          <div className="flex justify-between items-center border-b border-dark-800 pb-4">
            <div>
              <h3 className="text-sm font-bold text-dark-100">Actionable Career Learning Roadmap</h3>
              <p className="text-xs text-dark-400">
                Grounded learning milestones with verifiable documentation and real engineering projects.
              </p>
            </div>
            <button
              onClick={fetchRoadmap}
              className="text-xs font-bold text-indigo-400 hover:text-indigo-300"
            >
              🔄 Refresh Plan
            </button>
          </div>

          {loadingRoadmap ? (
            <LoadingSpinner text="Compiling verified curriculum milestones..." />
          ) : roadmap.length === 0 ? (
            <div className="text-center p-8 text-xs text-dark-400">
              No roadmap milestones currently generated. Click Refresh Plan to initialize.
            </div>
          ) : (
            <div className="space-y-4">
              {roadmap.map((m) => (
                <div
                  key={m.id}
                  className={`p-5 rounded-xl border transition-all space-y-4 ${
                    m.status === 'completed'
                      ? 'bg-emerald-950/10 border-emerald-500/20'
                      : 'bg-dark-900/60 border-dark-800'
                  }`}
                >
                  <div className="flex justify-between items-start flex-wrap gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <h4 className="text-sm font-bold text-dark-100">{m.skill_name}</h4>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase bg-dark-800 text-indigo-400">
                          {m.importance}
                        </span>
                        <span className="text-[10px] font-semibold text-dark-400">
                          Target: {m.target_proficiency}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleToggleMilestone(m.id, m.status)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                        m.status === 'completed'
                          ? 'bg-emerald-900/40 text-emerald-300 border-emerald-500/40'
                          : 'bg-dark-900 text-dark-300 border-dark-800 hover:border-indigo-500/40'
                      }`}
                    >
                      {m.status === 'completed' ? '✓ Completed' : 'Mark as Done'}
                    </button>
                  </div>

                  {/* Verifiable Documentation Links */}
                  {m.resources && m.resources.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="text-[10px] font-bold text-dark-400 uppercase tracking-wider block">Verifiable Resources</span>
                      <div className="flex flex-wrap gap-2">
                        {m.resources.map((res, idx) => {
                          const safeUrl = getSafeExternalUrl(res.url);
                          return safeUrl ? (
                            <a
                              key={idx}
                              href={safeUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[11px] font-semibold px-2.5 py-1 bg-dark-950 border border-dark-800 rounded-lg text-indigo-400 hover:text-indigo-300 flex items-center space-x-1"
                            >
                              <span>📖</span>
                              <span>{res.name}</span>
                              <span>↗</span>
                            </a>
                          ) : null;
                        })}
                      </div>
                    </div>
                  )}

                  {/* Practice Exercises */}
                  {m.exercises && m.exercises.length > 0 && (
                    <div className="space-y-1 text-xs text-dark-300">
                      <span className="text-[10px] font-bold text-dark-400 uppercase tracking-wider block">Recommended Projects</span>
                      <ul className="list-disc pl-4 space-y-1">
                        {m.exercises.map((ex, idx) => (
                          <li key={idx}>{ex}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Resume Versions */}
      {activeTab === 'versions' && (
        <div className="space-y-6">
          <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-6">
            <div className="flex justify-between items-center border-b border-dark-800 pb-4 flex-wrap gap-4">
              <div>
                <h3 className="text-sm font-bold text-dark-100">Multiple Resume Versions Management</h3>
                <p className="text-xs text-dark-400">
                  Maintain distinct, tailored resumes for different target roles with diff comparison and download support.
                </p>
              </div>
            </div>

            {/* Create Version Form */}
            <form onSubmit={handleCreateVersion} className="p-4 bg-dark-900/60 border border-dark-800 rounded-xl space-y-3">
              <span className="text-xs font-bold text-dark-200 block">Create Role-Specific Version</span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <input
                  type="text"
                  placeholder="Version Name (e.g. Frontend React Focus)"
                  value={newVersionLabel}
                  onChange={(e) => setNewVersionLabel(e.target.value)}
                  className="px-3 py-2 bg-dark-950 border border-dark-800 rounded-xl text-xs text-dark-100 outline-none focus:border-indigo-500/40"
                  required
                />
                <input
                  type="text"
                  placeholder="Target Role (e.g. Senior Frontend Engineer)"
                  value={newVersionRole}
                  onChange={(e) => setNewVersionRole(e.target.value)}
                  className="px-3 py-2 bg-dark-950 border border-dark-800 rounded-xl text-xs text-dark-100 outline-none focus:border-indigo-500/40"
                />
                <button
                  type="submit"
                  disabled={isCreatingVersion || !newVersionLabel.trim()}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold rounded-xl text-xs transition-all"
                >
                  {isCreatingVersion ? 'Creating...' : '+ Create Version'}
                </button>
              </div>
            </form>

            {/* Version Comparison Selector */}
            {versions.length >= 2 && (
              <div className="p-4 bg-dark-900/40 border border-dark-800 rounded-xl space-y-3 text-xs">
                <span className="font-bold text-dark-200 block">Compare Two Versions</span>
                <div className="flex flex-wrap items-center gap-3">
                  <select
                    value={compareVersionA}
                    onChange={(e) => setCompareVersionA(e.target.value)}
                    className="px-3 py-2 bg-dark-950 border border-dark-800 rounded-xl text-dark-200 text-xs"
                  >
                    {versions.map(v => (
                      <option key={v.id} value={v.id}>{v.label} (v{v.id})</option>
                    ))}
                  </select>
                  <span className="text-dark-400 font-bold">vs</span>
                  <select
                    value={compareVersionB}
                    onChange={(e) => setCompareVersionB(e.target.value)}
                    className="px-3 py-2 bg-dark-950 border border-dark-800 rounded-xl text-dark-200 text-xs"
                  >
                    {versions.map(v => (
                      <option key={v.id} value={v.id}>{v.label} (v{v.id})</option>
                    ))}
                  </select>
                  <button
                    onClick={handleCompareVersions}
                    className="px-4 py-2 bg-dark-800 hover:bg-dark-700 text-indigo-300 font-bold rounded-xl text-xs"
                  >
                    Run Comparison
                  </button>
                </div>

                {compareData && (
                  <div className="mt-4 p-4 bg-dark-950 rounded-xl border border-dark-800 space-y-3">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <span className="font-bold text-indigo-400">{compareData.version_a.label}</span>
                        <p className="text-dark-400">{compareData.version_a.word_count} words • {compareData.version_a.skills_count} skills</p>
                        {compareData.version_a.unique_skills?.length > 0 && (
                          <p className="text-dark-300">Unique: {compareData.version_a.unique_skills.join(', ')}</p>
                        )}
                      </div>
                      <div className="space-y-1">
                        <span className="font-bold text-indigo-400">{compareData.version_b.label}</span>
                        <p className="text-dark-400">{compareData.version_b.word_count} words • {compareData.version_b.skills_count} skills</p>
                        {compareData.version_b.unique_skills?.length > 0 && (
                          <p className="text-dark-300">Unique: {compareData.version_b.unique_skills.join(', ')}</p>
                        )}
                      </div>
                    </div>
                    <p className="text-dark-400 pt-2 border-t border-dark-800">
                      Shared Skills: {compareData.shared_skills.join(', ') || 'None'}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Versions List */}
            {loadingVersions ? (
              <LoadingSpinner text="Retrieving versions history..." />
            ) : versions.length === 0 ? (
              <div className="text-center p-8 text-xs text-dark-400">
                No historic resume versions found.
              </div>
            ) : (
              <div className="space-y-3">
                {versions.map((ver) => (
                  <div key={ver.id} className="p-4 bg-dark-950/60 border border-dark-800 rounded-xl flex justify-between items-center hover:border-dark-700 transition-all flex-wrap gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-dark-900 text-indigo-400 border border-indigo-500/20">
                          v#{ver.id}
                        </span>
                        <h4 className="text-xs font-bold text-dark-100">{ver.label}</h4>
                        {ver.target_role && (
                          <span className="text-[10px] text-dark-400 bg-dark-900 px-2 py-0.5 rounded">
                            {ver.target_role}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-dark-400">
                        Captured: {new Date(ver.created_at + 'Z').toLocaleString()}
                      </p>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handlePreviewVersion(ver.id)}
                        className="px-3 py-1.5 bg-dark-900 hover:bg-dark-800 text-dark-300 text-xs font-bold rounded-lg border border-dark-800"
                      >
                        Preview
                      </button>
                      <button
                        onClick={() => handleDownloadVersion(ver.id)}
                        className="px-3 py-1.5 bg-dark-900 hover:bg-dark-800 text-indigo-400 text-xs font-bold rounded-lg border border-dark-800"
                      >
                        Download
                      </button>
                      <button
                        onClick={() => handleRestoreVersion(ver.id)}
                        className="px-3 py-1.5 bg-indigo-600/10 hover:bg-indigo-600 hover:text-white border border-indigo-500/20 text-indigo-400 text-xs font-bold rounded-lg"
                      >
                        Set Active
                      </button>
                      {versions.length > 1 && (
                        <button
                          onClick={() => handleDeleteVersion(ver.id)}
                          className="px-2.5 py-1.5 hover:bg-red-950/40 text-red-400 text-xs font-bold rounded-lg border border-transparent hover:border-red-500/20"
                          title="Delete version"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Preview Modal */}
          {previewVersion && (
            <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-4 text-xs">
              <div className="flex justify-between items-center border-b border-dark-800 pb-3">
                <div>
                  <h4 className="text-sm font-bold text-dark-100">Preview: {previewVersion.label}</h4>
                  <p className="text-[10px] text-dark-400">Target Role: {previewVersion.target_role}</p>
                </div>
                <button
                  onClick={() => setPreviewVersion(null)}
                  className="text-dark-400 hover:text-dark-200 text-sm font-bold"
                >
                  ✕ Close
                </button>
              </div>
              <pre className="p-4 bg-dark-950 rounded-xl text-dark-300 font-mono text-[11px] max-h-96 overflow-y-auto whitespace-pre-wrap leading-relaxed border border-dark-800">
                {previewVersion.resume_text}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: Verified Career Profile & Privacy */}
      {activeTab === 'customize' && (
        <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-6">
          <div className="border-b border-dark-800 pb-4">
            <h3 className="text-sm font-bold text-dark-100">Verified Career Profile & Privacy Controls</h3>
            <p className="text-xs text-dark-400 mt-1">
              Confirmed skills and work experience are used as ground truth for matching and non-hallucinatory resume tailoring.
            </p>
          </div>

          <form onSubmit={handleSaveVerifiedProfile} className="space-y-5 text-xs">
            {/* Privacy Consent Boundary */}
            <div className="p-4 bg-dark-900/60 border border-dark-800 rounded-xl space-y-2">
              <span className="font-bold text-indigo-400 block text-xs">🔒 Privacy Preservation Mode</span>
              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={consentLocalOnly}
                  onChange={(e) => setConsentLocalOnly(e.target.checked)}
                  className="rounded border-dark-700 text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-dark-200 font-medium">
                  Strict Local Processing (Presidio masks all PII before any external model calls)
                </span>
              </label>
            </div>

            <div className="space-y-1.5">
              <label className="font-bold text-dark-300">Verified Technical & Professional Skills (comma-separated)</label>
              <textarea
                value={editSkills}
                onChange={(e) => setEditSkills(e.target.value)}
                rows={4}
                className="w-full p-3 bg-dark-950 border border-dark-800 rounded-xl text-dark-100 outline-none focus:border-indigo-500/40"
              />
            </div>

            <div className="space-y-1.5">
              <label className="font-bold text-dark-300">Full Resume & Experience Document</label>
              <textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={10}
                className="w-full p-3 bg-dark-950 border border-dark-800 rounded-xl text-dark-100 outline-none focus:border-indigo-500/40 font-mono text-[11px]"
              />
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={savingProfile}
                className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-bold rounded-xl text-xs transition-all"
              >
                {savingProfile ? 'Saving...' : 'Save Verified Profile'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* TAB 5: Admin Diagnostics */}
      {activeTab === 'admin' && (
        <div className="glass-panel border border-dark-800 rounded-2xl p-6 space-y-6 text-xs">
          <div className="border-b border-dark-800 pb-4">
            <h3 className="text-sm font-bold text-dark-100">System Diagnostics & Telemetry</h3>
            <p className="text-dark-400 mt-1">Live database connections and audit log metrics.</p>
          </div>

          {loadingAdmin ? (
            <LoadingSpinner text="Retrieving telemetry..." />
          ) : !adminStats ? (
            <div className="text-center p-8 text-dark-400">Failed to load system diagnostics.</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="p-4 bg-dark-900 border border-dark-800 rounded-xl">
                <span className="text-dark-400 block">Total Users</span>
                <span className="text-lg font-bold text-dark-100">{adminStats.total_users || 0}</span>
              </div>
              <div className="p-4 bg-dark-900 border border-dark-800 rounded-xl">
                <span className="text-dark-400 block">Total Interviews</span>
                <span className="text-lg font-bold text-dark-100">{adminStats.total_interviews || 0}</span>
              </div>
              <div className="p-4 bg-dark-900 border border-dark-800 rounded-xl">
                <span className="text-dark-400 block">Total Resumes</span>
                <span className="text-lg font-bold text-dark-100">{adminStats.total_resumes || 0}</span>
              </div>
              <div className="p-4 bg-dark-900 border border-dark-800 rounded-xl">
                <span className="text-dark-400 block">Audit Log Entries</span>
                <span className="text-lg font-bold text-dark-100">{adminStats.total_audit_logs || 0}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Dashboard;
