import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts';
import client from '../api/client';

const AnalyticsDashboard = () => {

  // Fetch dashboard data
  const { data: dashboardData, isLoading } = useQuery({
    queryKey: ['analyticsDashboard'],
    queryFn: async () => {
      const response = await client.get('/analytics/dashboard');
      return response.data;
    },
  });

  // Fetch conversion funnel
  const { data: funnelData } = useQuery({
    queryKey: ['conversionFunnel'],
    queryFn: async () => {
      const response = await client.get('/analytics/conversion-funnel');
      return response.data;
    },
  });

  if (isLoading) {
    return <div className="p-8 text-center text-gray-500">Loading analytics...</div>;
  }

  const summary = dashboardData?.summary || {};
  const timeline = dashboardData?.timeline || [];
  const statusData = dashboardData?.status_distribution || [];
  const companies = dashboardData?.top_companies || [];
  const titles = dashboardData?.top_job_titles || [];
  const monthlyTrend = dashboardData?.monthly_trend || [];
  const recommendations = dashboardData?.recommendations || [];
  const funnel = funnelData?.funnel || [];

  return (
    <div className="bg-gray-50 min-h-screen p-6">
      <h1 className="text-3xl font-bold mb-2">Analytics Dashboard</h1>
      <p className="text-gray-600 mb-6">Track your job search progress and identify opportunities</p>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-blue-500">
          <div className="text-2xl font-bold text-gray-800">{summary.total_applications || 0}</div>
          <div className="text-sm text-gray-600">Total Applications</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-green-500">
          <div className="text-2xl font-bold text-gray-800">{summary.success_count || 0}</div>
          <div className="text-sm text-gray-600">Interviews/Offers</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-purple-500">
          <div className="text-2xl font-bold text-gray-800">{summary.success_rate}</div>
          <div className="text-sm text-gray-600">Success Rate</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-yellow-500">
          <div className="text-2xl font-bold text-gray-800">{summary.avg_per_week}</div>
          <div className="text-sm text-gray-600">Avg per Week</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border-l-4 border-red-500">
          <div className="text-2xl font-bold text-gray-800">{summary.status_breakdown?.rejected || 0}</div>
          <div className="text-sm text-gray-600">Rejections</div>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Application Timeline */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Application Timeline (Last 30 Days)</h2>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={timeline}>
              <defs>
                <linearGradient id="colorCum" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Area type="monotone" dataKey="cumulative" stroke="#3b82f6" fillOpacity={1} fill="url(#colorCum)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Status Distribution */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Application Status</h2>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={statusData} cx="50%" cy="50%" labelLine={false} label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`} outerRadius={80} fill="#8884d8" dataKey="value">
                {statusData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Top Companies */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Top Companies Applied To</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={companies}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="company" angle={-45} textAnchor="end" height={100} interval={0} tick={{ fontSize: 12 }} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="applications" fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Monthly Trend */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Monthly Trend</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={monthlyTrend}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="count" stroke="#10b981" strokeWidth={2} name="Applications" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Conversion Funnel */}
      {funnel.length > 0 && (
        <div className="bg-white p-6 rounded-lg shadow mb-6">
          <h2 className="text-lg font-semibold mb-4">Conversion Funnel</h2>
          <div className="space-y-4">
            {funnel.map((stage, idx) => (
              <div key={idx}>
                <div className="flex justify-between mb-1">
                  <span className="font-semibold text-gray-700">{stage.stage}</span>
                  <span className="text-gray-600">{stage.count}</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-8 overflow-hidden">
                  <div
                    className={`h-full flex items-center justify-end pr-2 text-white font-semibold ${
                      idx === 0 ? 'bg-blue-500' : idx === 1 ? 'bg-yellow-500' : 'bg-green-500'
                    }`}
                    style={{ width: `${stage.percentage}%` }}
                  >
                    {stage.percentage > 10 && `${stage.percentage.toFixed(1)}%`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Applications */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Recent Applications</h2>
          <div className="space-y-3">
            {(dashboardData?.recent_applications || []).map((app, idx) => (
              <div key={idx} className="border-l-4 border-blue-500 pl-4 py-2">
                <div className="font-semibold text-gray-800">{app.job_title}</div>
                <div className="text-sm text-gray-600">{app.company}</div>
                <div className="flex justify-between items-center mt-1">
                  <span className={`text-xs px-2 py-1 rounded ${_getStatusBgColor(app.status)}`}>
                    {app.status}
                  </span>
                  <span className="text-xs text-gray-500">{app.days_ago} days ago</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recommendations */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">📊 Recommendations</h2>
          <div className="space-y-3">
            {recommendations.length > 0 ? (
              recommendations.map((rec, idx) => (
                <div key={idx} className="bg-blue-50 border-l-4 border-blue-500 p-3 rounded">
                  <p className="text-sm text-gray-800">{rec}</p>
                </div>
              ))
            ) : (
              <p className="text-gray-600">You're on track! Keep applying and practicing.</p>
            )}
          </div>
        </div>
      </div>

      {/* Top Job Titles */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h2 className="text-lg font-semibold mb-4">Most Applied Job Titles</h2>
        <div className="flex flex-wrap gap-2">
          {titles.map((title, idx) => (
            <div key={idx} className="bg-gray-100 px-3 py-1 rounded-full text-sm">
              {title.title} <span className="font-semibold text-gray-700">({title.count})</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

function _getStatusBgColor(status) {
  const colors = {
    applied: 'bg-blue-100 text-blue-800',
    interview_scheduled: 'bg-yellow-100 text-yellow-800',
    offered: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
  };
  return colors[status] || 'bg-gray-100 text-gray-800';
}

export default AnalyticsDashboard;
