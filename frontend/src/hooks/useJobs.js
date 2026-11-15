import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';
import { useAuth } from '../context/AuthContext';

export const useJobs = ({ hoursOld = 48 } = {}) => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const userId = user?.id;

  // 1. Get raw/filtered job list
  const jobsQuery = useQuery({
    queryKey: ['jobs', userId, hoursOld],
    queryFn: async ({ signal }) => {
      const response = await apiClient.get('/jobs/list', {
        params: { hours_old: hoursOld },
        signal,
      });
      const data = response?.data;
      if (Array.isArray(data?.jobs)) return data.jobs;
      if (Array.isArray(data)) return data;
      return [];
    },
    enabled: !!userId,
  });

  // 2. Get matched jobs
  const matchedJobsQuery = useQuery({
    queryKey: ['matchedJobs', userId, hoursOld],
    queryFn: async ({ signal }) => {
      const response = await apiClient.post('/jobs/match', null, {
        params: { hours_old: hoursOld },
        signal,
      });
      const data = response?.data;
      if (Array.isArray(data?.jobs)) return data.jobs;
      if (Array.isArray(data)) return data;
      return [];
    },
    enabled: !!userId,
  });

  // 3. Get filter criteria
  const criteriaQuery = useQuery({
    queryKey: ['criteria', userId],
    queryFn: async () => {
      const response = await apiClient.get('/jobs/criteria');
      return response.data;
    },
    enabled: !!userId,
  });

  // 4. Save filter criteria mutation
  const saveCriteriaMutation = useMutation({
    mutationFn: async (criteriaData) => {
      const response = await apiClient.post('/jobs/criteria', criteriaData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['criteria', userId] });
      queryClient.invalidateQueries({ queryKey: ['jobs', userId] });
      queryClient.invalidateQueries({ queryKey: ['matchedJobs', userId] });
    },
  });

  // 5. Fetch jobs manually mutation (returns background job_id)
  const fetchJobsMutation = useMutation({
    mutationFn: async ({ title, location, hours_old, job_type } = {}) => {
      const params = {};
      if (title) params.title = title;
      if (location) params.location = location;
      if (hours_old) params.hours_old = hours_old;
      if (job_type) params.job_type = job_type;
      const response = await apiClient.get('/jobs/fetch', { params });
      return response.data; // { job_id: ..., status: ... }
    },
  });

  // 6. Generate application package mutation (returns background job_id)
  const generateApplicationMutation = useMutation({
    mutationFn: async ({ jobId }) => {
      const response = await apiClient.post(`/apply/generate/${jobId}`);
      return response.data; // { job_id: ..., status: ... }
    },
  });

  // 7. Submit application record
  const submitApplicationMutation = useMutation({
    mutationFn: async (submitData) => {
      const response = await apiClient.post('/apply/submit', submitData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['appHistory', userId] });
    },
  });

  // 8. Application history list
  const historyQuery = useQuery({
    queryKey: ['appHistory', userId],
    queryFn: async () => {
      const response = await apiClient.get('/apply/history');
      return response.data;
    },
    enabled: !!userId,
  });

  // 9. Saved jobs list
  const savedJobsQuery = useQuery({
    queryKey: ['savedJobs', userId],
    queryFn: async () => {
      const response = await apiClient.get('/jobs/saved/list');
      return response.data;
    },
    enabled: !!userId,
  });

  // 10. Save job mutation
  const saveJobMutation = useMutation({
    mutationFn: async (jobData) => {
      const response = await apiClient.post('/jobs/saved/save', jobData);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savedJobs', userId] });
    },
  });

  // 11. Remove saved job mutation
  const removeSavedJobMutation = useMutation({
    mutationFn: async (savedJobId) => {
      const response = await apiClient.delete(`/jobs/saved/${savedJobId}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savedJobs', userId] });
    },
  });

  // 12. Update saved job notes mutation
  const updateSavedJobNotesMutation = useMutation({
    mutationFn: async ({ savedJobId, notes }) => {
      const response = await apiClient.patch(
        `/jobs/saved/${savedJobId}/notes`,
        { notes }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['savedJobs', userId] });
    },
  });

  // Polling helper with cancellation and max-attempts timeout
  const pollJobStatus = (jobId, onComplete, onError, intervalMs = 3000, maxAttempts = 60) => {
    let isCancelled = false;
    let attempts = 0;

    const timer = setInterval(async () => {
      if (isCancelled) return;
      attempts += 1;

      if (attempts > maxAttempts) {
        clearInterval(timer);
        if (!isCancelled && onError) {
          onError('Scraping task timed out waiting for results. Please refresh the page to view current listings.');
        }
        return;
      }

      try {
        const response = await apiClient.get(`/jobs/${jobId}/status`);
        if (isCancelled) return;
        const { status, result, error } = response?.data || {};

        if (status === 'completed') {
          clearInterval(timer);
          if (!isCancelled && onComplete) {
            onComplete(result || {});
          }
        } else if (status === 'failed') {
          clearInterval(timer);
          if (!isCancelled && onError) {
            onError(error || 'Task execution failed.');
          }
        }
      } catch (err) {
        if (isCancelled) return;
        clearInterval(timer);
        if (onError) {
          onError(err?.userFriendlyMessage || err?.message || 'Error checking task status.');
        }
      }
    }, intervalMs);

    return () => {
      isCancelled = true;
      clearInterval(timer);
    };
  };

  return {
    jobs: jobsQuery.data || [],
    isLoadingJobs: jobsQuery.isLoading,
    isJobsError: jobsQuery.isError,
    jobsError: jobsQuery.error,
    refetchJobs: jobsQuery.refetch,
    
    matchedJobs: matchedJobsQuery.data || [],
    isLoadingMatchedJobs: matchedJobsQuery.isLoading,
    isMatchedJobsError: matchedJobsQuery.isError,
    matchedJobsError: matchedJobsQuery.error,
    refetchMatchedJobs: matchedJobsQuery.refetch,
    
    criteria: criteriaQuery.data,
    isLoadingCriteria: criteriaQuery.isLoading,
    saveCriteria: saveCriteriaMutation.mutateAsync,
    
    fetchJobs: fetchJobsMutation.mutateAsync,
    isFetchingJobs: fetchJobsMutation.isPending,
    
    generateApplication: generateApplicationMutation.mutateAsync,
    isGeneratingApp: generateApplicationMutation.isPending,
    
    submitApplication: submitApplicationMutation.mutateAsync,
    isSubmittingApp: submitApplicationMutation.isPending,
    
    appHistory: historyQuery.data || [],
    isLoadingHistory: historyQuery.isLoading,

    savedJobs: savedJobsQuery.data || [],
    isLoadingSavedJobs: savedJobsQuery.isLoading,
    refetchSavedJobs: savedJobsQuery.refetch,
    saveJob: saveJobMutation.mutateAsync,
    isSavingJob: saveJobMutation.isPending,
    removeSavedJob: removeSavedJobMutation.mutateAsync,
    isRemovingSavedJob: removeSavedJobMutation.isPending,
    updateSavedJobNotes: updateSavedJobNotesMutation.mutateAsync,
    isUpdatingSavedJobNotes: updateSavedJobNotesMutation.isPending,
    
    pollJobStatus,
  };
};
