import React, { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import client from '../api/client';

const ApplicationKanban = () => {
  const [applications, setApplications] = useState({
    applied: [],
    interview_scheduled: [],
    offered: [],
    rejected: [],
  });
  const [draggedItem, setDraggedItem] = useState(null);

  // Fetch all applications
  const { data: appData } = useQuery({
    queryKey: ['applications'],
    queryFn: async () => {
      const response = await client.get('/apply/history');
      return response.data;
    },
  });

  // Update application status mutation
  const updateStatusMutation = useMutation({
    mutationFn: async ({ appId, status }) => {
      const response = await client.patch(`/apply/${appId}/status`, { status });
      return response.data;
    },
  });

  // Organize applications by status
  useEffect(() => {
    if (appData) {
      const organized = {
        applied: [],
        interview_scheduled: [],
        offered: [],
        rejected: [],
      };

      appData.forEach((app) => {
        const status = app.status?.toLowerCase() || 'applied';
        if (organized[status]) {
          organized[status].push(app);
        } else {
          organized.applied.push(app);
        }
      });

      setApplications(organized);
    }
  }, [appData]);

  const handleDragStart = (e, app, fromStatus) => {
    setDraggedItem({ app, fromStatus });
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e, toStatus) => {
    e.preventDefault();
    if (!draggedItem) return;

    const { app, fromStatus } = draggedItem;

    if (fromStatus !== toStatus) {
      // Update backend
      updateStatusMutation.mutate({
        appId: app.id,
        status: toStatus,
      });

      // Update local state
      setApplications((prev) => ({
        ...prev,
        [fromStatus]: prev[fromStatus].filter((a) => a.id !== app.id),
        [toStatus]: [...prev[toStatus], { ...app, status: toStatus }],
      }));
    }

    setDraggedItem(null);
  };

  const Column = ({ status, title, apps, color }) => (
    <div
      className={`flex-1 rounded-lg border-2 border-gray-300 p-4 min-h-96 bg-${color}-50`}
      onDragOver={handleDragOver}
      onDrop={(e) => handleDrop(e, status)}
    >
      <h3 className="text-lg font-semibold mb-4 text-gray-800">
        {title}
        <span className="ml-2 text-sm text-gray-500">({apps.length})</span>
      </h3>
      <div className="space-y-3">
        {apps.map((app) => (
          <div
            key={app.id}
            draggable
            onDragStart={(e) => handleDragStart(e, app, status)}
            className={`p-3 rounded-lg cursor-move hover:shadow-md transition-shadow bg-${color}-100 border border-${color}-300`}
          >
            <div className="font-semibold text-sm text-gray-800">{app.job_title}</div>
            <div className="text-xs text-gray-600">{app.company || app.company_name || 'Unknown Company'}</div>
            <div className="text-xs text-gray-500 mt-1">
              {app.applied_at || app.applied_date ? new Date(app.applied_at || app.applied_date).toLocaleDateString() : 'Recently'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-3xl font-bold mb-2">Application Pipeline</h1>
      <p className="text-gray-600 mb-6">Drag cards to update application status</p>

      <div className="flex gap-4 overflow-x-auto pb-4">
        <Column
          status="applied"
          title="📝 Applied"
          apps={applications.applied}
          color="blue"
        />
        <Column
          status="interview_scheduled"
          title="📞 Interview Scheduled"
          apps={applications.interview_scheduled}
          color="yellow"
        />
        <Column
          status="offered"
          title="🎉 Offered"
          apps={applications.offered}
          color="green"
        />
        <Column
          status="rejected"
          title="❌ Rejected"
          apps={applications.rejected}
          color="red"
        />
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-4 gap-4 mt-8">
        <div className="bg-blue-100 p-4 rounded-lg border border-blue-300">
          <div className="text-2xl font-bold text-blue-700">
            {applications.applied.length}
          </div>
          <div className="text-sm text-blue-600">Applied</div>
        </div>
        <div className="bg-yellow-100 p-4 rounded-lg border border-yellow-300">
          <div className="text-2xl font-bold text-yellow-700">
            {applications.interview_scheduled.length}
          </div>
          <div className="text-sm text-yellow-600">Interviews</div>
        </div>
        <div className="bg-green-100 p-4 rounded-lg border border-green-300">
          <div className="text-2xl font-bold text-green-700">
            {applications.offered.length}
          </div>
          <div className="text-sm text-green-600">Offered</div>
        </div>
        <div className="bg-red-100 p-4 rounded-lg border border-red-300">
          <div className="text-2xl font-bold text-red-700">
            {applications.rejected.length}
          </div>
          <div className="text-sm text-red-600">Rejected</div>
        </div>
      </div>
    </div>
  );
};

export default ApplicationKanban;
