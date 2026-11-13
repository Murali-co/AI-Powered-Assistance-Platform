import React from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import SkillChart from '../components/SkillChart';
import MatchScore from '../components/MatchScore';
import { getSafeExternalUrl } from '../utils/urlSecurity';

export const SkillGap = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const data = location.state;

  if (!data || !data.skill_gap) {
    return (
      <div className="max-w-md mx-auto px-4 py-16 text-center space-y-4">
        <span className="text-5xl">🧭</span>
        <h2 className="text-xl font-bold text-dark-100">No Diagnostic Data Found</h2>
        <p className="text-xs text-dark-400">
          We couldn't locate active skill analysis details. Please choose a target job and run the analyzer first.
        </p>
        <Link
          to="/upload"
          className="inline-block px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs transition-all shadow"
        >
          Go to Analyzer
        </Link>
      </div>
    );
  }

  const { skill_gap, cover_letter, target_role } = data;
  const { present_skills = [], missing_skills = [], skill_score = 0, recommendations = [], learning_resources = [] } = skill_gap;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-4 border-b border-dark-800">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-dark-50">Skill Diagnostics Results</h1>
          <p className="text-xs text-dark-400 mt-1">Target Role: <span className="text-indigo-400 font-bold">{target_role}</span></p>
        </div>

        <button
          onClick={() => navigate('/cover-letter', { state: { cover_letter, target_role } })}
          className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl transition-all flex items-center space-x-2 shadow-md"
        >
          <span>✍️</span>
          <span>View Custom Cover Letter</span>
        </button>
      </div>

      {/* Grid: Score, Chart, Skills */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Score Card & Skills lists */}
        <div className="lg:col-span-1 space-y-6">
          {/* Big Score Card */}
          <div className="glass-panel border rounded-2xl p-6 text-center space-y-4">
            <h3 className="text-xs text-dark-400 font-bold uppercase tracking-wider">Skill Matching Quotient</h3>
            <div className="relative inline-flex items-center justify-center">
              <span className="text-5xl font-black text-indigo-400">{skill_score}</span>
              <span className="text-dark-500 text-sm font-semibold ml-0.5">/100</span>
            </div>
            
            <div className="w-full">
              <MatchScore score={skill_score} />
            </div>
          </div>

          {/* Present Skills Panel */}
          <div className="glass-panel border rounded-2xl p-6 space-y-3">
            <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider">Matched Competencies</h4>
            <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto pr-2">
              {present_skills.length > 0 ? (
                present_skills.map((skill) => (
                  <span key={skill} className="text-[10px] font-semibold px-2 py-0.5 bg-emerald-950/20 text-emerald-400 border border-emerald-500/20 rounded-md">
                    ✓ {skill}
                  </span>
                ))
              ) : (
                <span className="text-xs text-dark-400">None detected.</span>
              )}
            </div>
          </div>

          {/* Missing Skills Panel */}
          <div className="glass-panel border rounded-2xl p-6 space-y-3">
            <h4 className="text-xs font-bold text-red-400 uppercase tracking-wider">Missing Skill Gaps</h4>
            <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto pr-2">
              {missing_skills.length > 0 ? (
                missing_skills.map((skill) => (
                  <span key={skill} className="text-[10px] font-semibold px-2 py-0.5 bg-red-950/20 text-red-400 border border-red-500/20 rounded-md">
                    + {skill}
                  </span>
                ))
              ) : (
                <span className="text-xs text-emerald-400">Perfect match! No gaps found.</span>
              )}
            </div>
          </div>
        </div>

        {/* Recharts Radar Chart */}
        <div className="lg:col-span-2 glass-panel border rounded-2xl p-6 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-dark-100 mb-1">Competency Area Analysis</h3>
            <p className="text-xs text-dark-400">Visual coverage of your skills compared to the role requirements</p>
          </div>
          
          <div className="flex-1 flex items-center justify-center py-4">
            <SkillChart presentSkills={present_skills} missingSkills={missing_skills} />
          </div>
        </div>
      </div>

      {/* Bottom section: Pathways & Resources */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Recommendations */}
        <div className="glass-panel border rounded-2xl p-6 space-y-4">
          <h3 className="text-md font-bold text-dark-100 flex items-center space-x-2">
            <span>🚀</span>
            <span>Bridging the Gap Pathways</span>
          </h3>
          <ul className="space-y-2.5 text-xs text-dark-300">
            {recommendations.map((rec, idx) => (
              <li key={idx} className="flex items-start space-x-2.5 leading-relaxed">
                <span className="text-indigo-400 font-bold select-none">•</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Resources */}
        <div className="glass-panel border rounded-2xl p-6 space-y-4">
          <h3 className="text-md font-bold text-dark-100 flex items-center space-x-2">
            <span>📚</span>
            <span>Recommended Learning Resources</span>
          </h3>
          <ul className="space-y-2.5 text-xs text-dark-300">
            {learning_resources.map((res, idx) => (
              <li key={idx} className="flex items-start space-x-2.5 leading-relaxed">
                <span className="text-emerald-400 font-bold select-none">→</span>
                {typeof res === 'object' && res !== null ? (
                  (() => {
                    const safeUrl = getSafeExternalUrl(res.url);
                    return safeUrl ? (
                      <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 hover:underline transition-colors font-medium">
                        {res.title}
                      </a>
                    ) : (
                      <span>{res.title || 'Resource'}</span>
                    );
                  })()
                ) : (
                  <span>{res}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};
export default SkillGap;
