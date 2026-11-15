import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useJobs } from '../hooks/useJobs';
import JobCard from '../components/JobCard';
import MatchScore from '../components/MatchScore';
import { LoadingSpinner } from '../components/LoadingSpinner';
import apiClient from '../api/client';
import toast from 'react-hot-toast';

export const JobMatch = () => {
  const navigate = useNavigate();
  const {
    matchedJobs,
    isLoadingMatchedJobs,
    generateApplication,
    pollJobStatus
  } = useJobs();

  const [pollingJobId, setPollingJobId] = useState(null);

  // Explanation Modal states
  const [explainingJob, setExplainingJob] = useState(null);
  const [explanationData, setExplanationData] = useState(null);
  const [isLoadingExplanation, setIsLoadingExplanation] = useState(false);

  // Tailored Resume states
  const [tailoredResumeData, setTailoredResumeData] = useState(null);
  const [_isTailoringResume, setIsTailoringResume] = useState(false);

  const handleTailorResume = async (job) => {
    setIsTailoringResume(true);
    setTailoredResumeData(null);
    const loadingToast = toast.loading('Tailoring resume to job description...');
    try {
      const res = await apiClient.post('/resume/tailor', { job_id: job.id });
      setTailoredResumeData(res.data);
      toast.success('Resume tailored successfully!', { id: loadingToast });
    } catch (err) {
      toast.error('Failed to tailor resume.', { id: loadingToast });
    } finally {
      setIsTailoringResume(false);
    }
  };

  const handleGenerateApplication = async (job) => {
    const loadingToast = toast.loading('Initiating AI Application tailoring...');
    try {
      const response = await generateApplication({ jobId: job.id });
      const { job_id } = response;
      setPollingJobId(job_id);

      pollJobStatus(
        job_id,
        (result) => {
          toast.success('Application package generated!', { id: loadingToast });
          setPollingJobId(null);
          setExplainingJob(null); // Close modal if open
          navigate('/apply-assistant', { 
            state: { 
              package: result,
              job: job 
            } 
          });
        },
        (errorMsg) => {
          toast.error(errorMsg || 'Failed to tailor application.', { id: loadingToast });
          setPollingJobId(null);
        }
      );
    } catch (err) {
      toast.error('Could not start application tailoring.', { id: loadingToast });
      setPollingJobId(null);
    }
  };

  const handleExplain = async (job) => {
    setExplainingJob(job);
    setIsLoadingExplanation(true);
    setExplanationData(null);
    try {
      const res = await apiClient.get(`/jobs/explain/${job.id}`);
      setExplanationData(res.data);
    } catch (err) {
      toast.error('Failed to generate match explanation.');
      setExplainingJob(null);
    } finally {
      setIsLoadingExplanation(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8 relative">
      {/* Generation Progress overlay */}
      {pollingJobId && (
        <div className="absolute inset-0 bg-dark-950/80 backdrop-blur-md z-50 flex items-center justify-center rounded-3xl">
          <div className="text-center space-y-4 max-w-sm p-6 bg-dark-900 border border-dark-800 rounded-2xl shadow-2xl">
            <LoadingSpinner size="lg" text="" />
            <h3 className="text-lg font-bold text-dark-100 animate-pulse">Tailoring Application Materials</h3>
            <p className="text-xs text-dark-400 leading-relaxed">
              Ollama is scanning the job description, mapping it to your profile, writing custom bullets, and composing a tailored cover letter. This takes 15-30 seconds...
            </p>
          </div>
        </div>
      )}

      {/* Explanation Modal overlay */}
      {explainingJob && (
        <div className="fixed inset-0 bg-dark-950/80 backdrop-blur-md z-40 flex items-center justify-center p-4">
          <div className="glass-panel border rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-6 shadow-2xl text-xs relative">
            
            {/* Header */}
            <div className="flex justify-between items-start pb-4 border-b border-dark-800">
              <div>
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-400">Match Insights</span>
                <h3 className="text-lg font-bold text-dark-50 mt-1">{explainingJob.title}</h3>
                <p className="text-dark-400 font-semibold">{explainingJob.company} — {explainingJob.location}</p>
              </div>
              <button 
                onClick={() => setExplainingJob(null)}
                className="text-dark-400 hover:text-dark-100 text-sm font-bold p-1"
              >
                ✕
              </button>
            </div>

            {isLoadingExplanation ? (
              <div className="py-12 flex flex-col items-center justify-center space-y-4">
                <LoadingSpinner text="" />
                <h4 className="font-bold text-dark-200 animate-pulse">Running Deep GAP Analysis</h4>
                <p className="text-[10px] text-dark-400 text-center max-w-xs leading-relaxed">
                  Comparing your resume against the target role's experience, education, and keyword requirements...
                </p>
              </div>
            ) : explanationData ? (
              <div className="space-y-6">
                
                {/* Score & Skills Row */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
                  <div className="md:col-span-1 flex flex-col items-center justify-center p-4 bg-dark-900/40 border border-dark-800 rounded-xl">
                    <span className="text-[10px] font-bold text-dark-400 uppercase pb-2">Overall Score</span>
                    <MatchScore score={explanationData.score} />
                  </div>
                  <div className="md:col-span-2 space-y-3">
                    <h4 className="font-bold text-dark-200">Skill Alignment</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {explanationData.matched_skills.map((skill) => (
                        <span key={skill} className="px-2 py-0.5 bg-emerald-950/30 text-emerald-400 border border-emerald-500/10 rounded-md font-semibold text-[10px]">
                          ✓ {skill}
                        </span>
                      ))}
                      {explanationData.missing_skills.map((skill) => (
                        <span key={skill} className="px-2 py-0.5 bg-red-950/30 text-red-400 border border-red-500/10 rounded-md font-semibold text-[10px]">
                          + {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Gaps Grid */}
                <div className="space-y-4">
                  <div className="p-4 bg-dark-900/30 border border-dark-800/40 rounded-xl space-y-1.5">
                    <h4 className="font-bold text-dark-100 flex items-center space-x-1.5">
                      <span>⏳</span>
                      <span>Experience Gap Analysis</span>
                    </h4>
                    <p className="text-dark-300 leading-relaxed font-medium">
                      {explanationData.experience_gap}
                    </p>
                  </div>

                  <div className="p-4 bg-dark-900/30 border border-dark-800/40 rounded-xl space-y-1.5">
                    <h4 className="font-bold text-dark-100 flex items-center space-x-1.5">
                      <span>🎓</span>
                      <span>Education Gap Analysis</span>
                    </h4>
                    <p className="text-dark-300 leading-relaxed font-medium">
                      {explanationData.education_gap}
                    </p>
                  </div>

                  {explanationData.keyword_gap && explanationData.keyword_gap.length > 0 && (
                    <div className="p-4 bg-dark-900/30 border border-dark-800/40 rounded-xl space-y-2">
                      <h4 className="font-bold text-dark-100 flex items-center space-x-1.5">
                        <span>🔑</span>
                        <span>Missing Resume Keywords</span>
                      </h4>
                      <div className="flex flex-wrap gap-1.5">
                        {explanationData.keyword_gap.map((kw, i) => (
                          <span key={i} className="px-2.5 py-0.5 bg-amber-950/30 text-amber-400 border border-amber-500/10 rounded font-semibold text-[10px]">
                            {kw}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="p-4 bg-indigo-950/20 border border-indigo-500/10 rounded-xl space-y-2.5">
                    <h4 className="font-bold text-indigo-400 flex items-center space-x-1.5">
                      <span>🚀</span>
                      <span>Improvement Suggestions</span>
                    </h4>
                    <ul className="list-decimal pl-4 space-y-1.5 text-dark-300 font-semibold">
                      {explanationData.recommendations.map((rec, i) => (
                        <li key={i} className="leading-relaxed">{rec}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Footer Buttons */}
                <div className="flex justify-end space-x-3 pt-4 border-t border-dark-800">
                  <button
                    onClick={() => setExplainingJob(null)}
                    className="px-4 py-2 border border-dark-800 hover:bg-dark-800 text-dark-200 font-bold rounded-xl"
                  >
                    Close
                  </button>
                  <button
                    onClick={() => {
                      const job = explainingJob;
                      setExplainingJob(null);
                      handleTailorResume(job);
                    }}
                    className="px-5 py-2 bg-gradient-to-r from-pink-600 to-pink-700 hover:from-pink-505 hover:to-pink-600 text-white font-bold rounded-xl shadow-md"
                  >
                    Tailor Resume
                  </button>
                  <button
                    onClick={() => handleGenerateApplication(explainingJob)}
                    className="px-5 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white font-bold rounded-xl shadow-md"
                  >
                    Tailor Application Materials
                  </button>
                </div>

              </div>
            ) : (
              <div className="text-center py-8 text-dark-400">Failed to load explanation.</div>
            )}
          </div>
        </div>
      )}

      {/* Tailored Resume Modal Overlay */}
      {tailoredResumeData && (
        <div className="fixed inset-0 bg-dark-950/80 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="glass-panel border rounded-3xl max-w-3xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-6 shadow-2xl text-xs relative">
            {/* Header */}
            <div className="flex justify-between items-start pb-4 border-b border-dark-800">
              <div>
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-pink-450 font-mono">Resume Tailored & Optimized</span>
                <h3 className="text-lg font-bold text-dark-50 mt-1">AI Tailoring Results</h3>
                <p className="text-dark-400 font-semibold">New Estimated ATS Match Score: <span className="text-pink-400 font-bold">{tailoredResumeData.ats_score_estimate}%</span></p>
              </div>
              <button 
                onClick={() => setTailoredResumeData(null)}
                className="text-dark-400 hover:text-dark-100 text-sm font-bold p-1"
              >
                ✕
              </button>
            </div>

            {/* Keyword changes */}
            <div className="space-y-3">
              <h4 className="font-bold text-dark-100 flex items-center space-x-1.5">
                <span>🔑</span>
                <span>Optimized Keywords & Phrasing</span>
              </h4>
              <div className="border border-dark-800 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-dark-900/60 border-b border-dark-800 text-dark-400 font-semibold text-[10px]">
                      <th className="p-3">Original Resume Keyword</th>
                      <th className="p-3">AI Tailored Phrasing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tailoredResumeData.keyword_changes.map((change, i) => (
                      <tr key={i} className="border-b border-dark-900/40 last:border-0 hover:bg-dark-900/10">
                        <td className="p-3 text-red-400 font-semibold font-mono">{change.original}</td>
                        <td className="p-3 text-emerald-400 font-semibold font-mono">{change.optimized}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Full Resume Preview Textarea */}
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <h4 className="font-bold text-dark-100 flex items-center space-x-1.5">
                  <span>📄</span>
                  <span>Optimized Resume Text</span>
                </h4>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(tailoredResumeData.tailored_resume);
                    toast.success('Resume copied to clipboard!');
                  }}
                  className="px-3 py-1 bg-dark-900 border border-dark-800 hover:bg-dark-800 text-indigo-400 text-[10px] font-bold rounded-lg transition-all"
                >
                  Copy to Clipboard
                </button>
              </div>
              <textarea
                readOnly
                value={tailoredResumeData.tailored_resume}
                rows={12}
                className="w-full bg-dark-950/60 border border-dark-850/80 rounded-xl p-4 font-mono text-[11px] leading-relaxed text-dark-200 focus:outline-none resize-none focus:border-dark-700"
              />
            </div>

            {/* Footer */}
            <div className="flex justify-end pt-4 border-t border-dark-800">
              <button
                onClick={() => setTailoredResumeData(null)}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl shadow-md transition-all duration-300"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}


      {/* Header */}
      <div className="pb-4 border-b border-dark-800">
        <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">Vector Skill Matcher</h1>
        <p className="text-xs text-dark-400 mt-1">
          Scraped positions ranked in real-time using cosine similarity calculations in ChromaDB.
        </p>
      </div>

      {isLoadingMatchedJobs ? (
        <LoadingSpinner text="Running semantic matching calculations..." />
      ) : matchedJobs.length > 0 ? (
        <div className="space-y-6">
          <div className="text-xs text-dark-400 font-semibold uppercase tracking-wider">
            Ranked Recommendations ({matchedJobs.length})
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {matchedJobs.map((job) => (
              <JobCard 
                key={job.id} 
                job={job} 
                onAction={handleGenerateApplication} 
                actionLabel="Tailor Application"
                onExplain={handleExplain}
                explainLabel="Explain Match"
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="glass-panel border rounded-2xl p-12 text-center text-xs text-dark-400 space-y-3">
          <span className="text-4xl block">🧭</span>
          <p className="font-bold text-dark-200">No Matched Jobs Found</p>
          <p className="max-w-xs mx-auto text-[11px]">
            Please upload a resume first and run job scraping in the Job Board to index positions for matching.
          </p>
        </div>
      )}
    </div>
  );
};

export default JobMatch;
