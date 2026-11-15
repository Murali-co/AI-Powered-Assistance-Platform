import React, { useState, useEffect } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  LineChart,
  Line,
  CartesianGrid,
  Legend
} from 'recharts';
import apiClient from '../api/client';
import { LoadingSpinner } from './LoadingSpinner';

export const MarketInsights = () => {
  const [skills, setSkills] = useState([]);
  const [salaries, setSalaries] = useState([]);
  const [trends, setTrends] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchMarketData();
  }, []);

  const fetchMarketData = async () => {
    setIsLoading(true);
    try {
      const [skillsRes, salaryRes, trendsRes] = await Promise.all([
        apiClient.get('/market/trending-skills'),
        apiClient.get('/market/salary-insights'),
        apiClient.get('/market/hiring-trends')
      ]);
      setSkills(skillsRes.data);
      setSalaries(salaryRes.data);
      setTrends(trendsRes.data);
    } catch (err) {
      console.error('Failed to retrieve market intelligence data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const formatCurrency = (value) => {
    return `$${(value / 1000).toFixed(0)}k`;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  if (isLoading) {
    return (
      <div className="py-12 flex justify-center items-center">
        <LoadingSpinner text="Analyzing market demand & salary brackets..." />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Overview stats header */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass-panel border rounded-2xl p-5 space-y-2">
          <span className="text-2xl">🔥</span>
          <div>
            <h4 className="text-[10px] font-bold text-dark-400 uppercase tracking-wider">Top Technology</h4>
            <p className="text-lg font-extrabold text-indigo-400 mt-0.5">
              {skills[0]?.skill || 'Python'}
            </p>
          </div>
        </div>

        <div className="glass-panel border rounded-2xl p-5 space-y-2">
          <span className="text-2xl">💰</span>
          <div>
            <h4 className="text-[10px] font-bold text-dark-400 uppercase tracking-wider">Median AI Salary</h4>
            <p className="text-lg font-extrabold text-pink-400 mt-0.5">
              {formatCurrency(salaries.find(s => s.role.includes('AI'))?.median || 160000)}
            </p>
          </div>
        </div>

        <div className="glass-panel border rounded-2xl p-5 space-y-2">
          <span className="text-2xl">📈</span>
          <div>
            <h4 className="text-[10px] font-bold text-dark-400 uppercase tracking-wider">Weekly Postings</h4>
            <p className="text-lg font-extrabold text-emerald-400 mt-0.5">
              {trends.reduce((acc, t) => acc + t.jobs_count, 0)} Active
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Chart 1: Top Requested Technologies */}
        <div className="glass-panel border rounded-2xl p-6 flex flex-col h-[380px] justify-between">
          <div>
            <h3 className="text-xs font-bold text-dark-100 flex items-center space-x-1.5">
              <span>📊</span>
              <span>Top Demanded Skills</span>
            </h3>
            <p className="text-[10px] text-dark-400 mt-0.5">Frequency count in matching job descriptions.</p>
          </div>

          <div className="w-full h-[260px] mt-4 text-[10px] font-semibold text-dark-300">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={skills}
                layout="vertical"
                margin={{ left: 10, right: 20, top: 10, bottom: 10 }}
              >
                <XAxis type="number" stroke="#475569" />
                <YAxis
                  dataKey="skill"
                  type="category"
                  stroke="#475569"
                  width={75}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    fontSize: '11px',
                    color: '#f8fafc'
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="#818cf8"
                  radius={[0, 4, 4, 0]}
                  name="Requested Postings"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Skill Demand Growth / Hiring Volume */}
        <div className="glass-panel border rounded-2xl p-6 flex flex-col h-[380px] justify-between">
          <div>
            <h3 className="text-xs font-bold text-dark-100 flex items-center space-x-1.5">
              <span>📈</span>
              <span>Hiring Volume & Trajectory</span>
            </h3>
            <p className="text-[10px] text-dark-400 mt-0.5">Active postings scraped chronologically over the past week.</p>
          </div>

          <div className="w-full h-[260px] mt-4 text-[10px] font-semibold text-dark-300">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={trends}
                margin={{ left: 5, right: 15, top: 10, bottom: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.03)" />
                <XAxis
                  dataKey="date"
                  stroke="#475569"
                  tickFormatter={formatDate}
                />
                <YAxis stroke="#475569" allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    fontSize: '11px',
                    color: '#f8fafc'
                  }}
                  labelFormatter={formatDate}
                />
                <Line
                  type="monotone"
                  dataKey="jobs_count"
                  stroke="#34d399"
                  strokeWidth={2.5}
                  dot={{ r: 4, stroke: '#34d399', strokeWidth: 2 }}
                  name="Job Postings"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 3: Salary Ranges Comparison */}
        <div className="lg:col-span-2 glass-panel border rounded-2xl p-6 flex flex-col h-[380px] justify-between">
          <div>
            <h3 className="text-xs font-bold text-dark-100 flex items-center space-x-1.5">
              <span>💼</span>
              <span>Salary Insights by Technology Role</span>
            </h3>
            <p className="text-[10px] text-dark-400 mt-0.5">Min, Median, and Max annual salary ranges in standard markets.</p>
          </div>

          <div className="w-full h-[260px] mt-4 text-[10px] font-semibold text-dark-300">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={salaries}
                margin={{ left: 10, right: 10, top: 10, bottom: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.02)" />
                <XAxis dataKey="role" stroke="#475569" />
                <YAxis stroke="#475569" tickFormatter={formatCurrency} />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.02)' }}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    fontSize: '11px',
                    color: '#f8fafc'
                  }}
                  formatter={(val) => [`$${val.toLocaleString()}`, '']}
                />
                <Legend
                  wrapperStyle={{ fontSize: '10px', paddingTop: '10px' }}
                />
                <Bar dataKey="min" fill="#818cf8" name="Minimum Salary" radius={[3, 3, 0, 0]} />
                <Bar dataKey="median" fill="#a78bfa" name="Median Salary" radius={[3, 3, 0, 0]} />
                <Bar dataKey="max" fill="#f472b6" name="Maximum Salary" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketInsights;
