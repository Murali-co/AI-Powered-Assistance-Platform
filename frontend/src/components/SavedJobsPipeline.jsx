import React, { useEffect, useState } from 'react';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

const stages = [
  { key: 'saved', label: 'Saved' },
  { key: 'applied', label: 'Applied' },
  { key: 'interview', label: 'Interview' },
  { key: 'offer', label: 'Offer' },
];

const SavedJobsPipeline = () => {
  const [jobs, setJobs] = useState([]);

  const fetchJobs = async () => {
    try {
      const res = await apiClient.get('/jobs/saved/list');
      setJobs(res.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  const handleStageChange = async (savedJobId, stage) => {
    try {
      await apiClient.patch(`/jobs/saved/${savedJobId}/stage?stage=${stage}`);
      toast.success('Pipeline stage updated');
      fetchJobs();
    } catch (err) {
      toast.error('Unable to update stage');
    }
  };

  return (
    <div className="glass-panel border rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-dark-100">Saved Jobs Pipeline</h3>
          <p className="text-[11px] text-dark-400">Move jobs across your daily workflow.</p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {stages.map((stage) => (
          <div key={stage.key} className="rounded-xl border border-dark-800 bg-dark-950/40 p-3 min-h-[140px]">
            <div className="text-[10px] uppercase tracking-wider font-bold text-dark-400">{stage.label}</div>
            <div className="mt-2 space-y-2">
              {jobs.filter((job) => (job.stage || 'saved') === stage.key).map((job) => (
                <div key={job.id} className="rounded-lg border border-dark-800 bg-dark-900/70 p-2 text-[11px]">
                  <div className="font-semibold text-dark-100">{job.job_title || job.title || 'Untitled Role'}</div>
                  <div className="text-dark-400">{job.company || job.company_name || 'Unknown Company'}</div>
                  <select
                    value={job.stage || 'saved'}
                    onChange={(e) => handleStageChange(job.id, e.target.value)}
                    className="mt-2 w-full bg-dark-950 border border-dark-800 rounded-md px-2 py-1 text-[10px]"
                  >
                    {stages.map((option) => (
                      <option key={option.key} value={option.key}>{option.label}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SavedJobsPipeline;
