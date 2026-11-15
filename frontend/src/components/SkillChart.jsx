import React from 'react';
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
  Tooltip
} from 'recharts';

export const SkillChart = ({ presentSkills = [], missingSkills = [] }) => {
  // Taxonomy definitions to group user skills
  const categories = {
    'Languages': ['python', 'javascript', 'typescript', 'go', 'golang', 'rust', 'c++', 'c#', 'java', 'kotlin', 'swift', 'ruby', 'php', 'html', 'css', 'sql', 'bash', 'shell', 'r', 'scala'],
    'Frameworks': ['react', 'vue', 'angular', 'nextjs', 'svelte', 'express', 'fastify', 'nestjs', 'django', 'flask', 'fastapi', 'spring', 'spring boot', 'rails', 'laravel', 'tailwind', 'bootstrap', 'pandas', 'numpy', 'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'react native', 'flutter'],
    'Cloud & DevOps': ['aws', 'amazon web services', 'azure', 'gcp', 'google cloud', 'docker', 'kubernetes', 'k8s', 'terraform', 'ansible', 'jenkins', 'gitlab ci', 'github actions', 'nginx', 'apache', 'ci/cd', 'prometheus', 'grafana'],
    'Databases': ['postgresql', 'postgres', 'mysql', 'mongodb', 'redis', 'sqlite', 'cassandra', 'elasticsearch', 'dynamodb', 'mariadb', 'oracle', 'firestore', 'chromadb', 'pinecone', 'supabase', 'milvus'],
    'Methodologies & Soft': ['git', 'github', 'gitlab', 'postman', 'jira', 'confluence', 'linux', 'windows', 'macos', 'vscode', 'graphql', 'grpc', 'rest api', 'websockets', 'agile', 'scrum', 'kanban', 'microservices', 'machine learning', 'deep learning', 'nlp', 'llm', 'generative ai', 'communication', 'leadership', 'teamwork', 'problem solving', 'critical thinking', 'time management', 'collaboration', 'presentation', 'mentoring', 'negotiation']
  };

  const getCategoryCounts = (skills) => {
    const counts = { 'Languages': 0, 'Frameworks': 0, 'Cloud & DevOps': 0, 'Databases': 0, 'Methodologies & Soft': 0 };
    skills.forEach(skill => {
      const sLower = skill.toLowerCase();
      let matched = false;
      for (const [catName, catList] of Object.entries(categories)) {
        if (catList.includes(sLower) || catList.some(kw => sLower.includes(kw))) {
          counts[catName]++;
          matched = true;
          break;
        }
      }
      // If not categorized, default to Methodologies & Soft
      if (!matched) {
        counts['Methodologies & Soft']++;
      }
    });
    return counts;
  };

  const presentCounts = getCategoryCounts(presentSkills);
  const missingCounts = getCategoryCounts(missingSkills);

  // Format data for Recharts Radar
  const chartData = Object.keys(categories).map(cat => {
    const present = presentCounts[cat] || 0;
    const missing = missingCounts[cat] || 0;
    const total = present + missing;
    
    // coverage ratio
    const coverage = total > 0 ? Math.round((present / total) * 100) : 100;
    const required = total > 0 ? 100 : 0;

    return {
      subject: cat,
      Present: coverage,
      Required: required,
      presentRaw: present,
      missingRaw: missing
    };
  });

  return (
    <div className="w-full h-80 min-h-[320px]">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="75%" data={chartData}>
          <PolarGrid stroke="#334155" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: '#94a3b8', fontSize: 11 }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#64748b' }} />
          
          <Radar
            name="Your Skills Coverage (%)"
            dataKey="Present"
            stroke="#6366f1"
            fill="#6366f1"
            fillOpacity={0.3}
          />
          <Radar
            name="Job Requirements (%)"
            dataKey="Required"
            stroke="#ef4444"
            fill="#ef4444"
            fillOpacity={0.05}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '12px' }}
            itemStyle={{ color: '#f8fafc' }}
          />
          <Legend wrapperStyle={{ fontSize: '12px', marginTop: '10px' }} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
};
export default SkillChart;
