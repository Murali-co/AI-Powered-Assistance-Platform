import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useJobPolling } from './useJobPolling';
import apiClient from '../api/client';
import { useAuth } from '../context/AuthContext';

export const useJobs = ({ hoursOld = 168, title, location, includeMatches = true } = {}) => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const userId = user?.id;
  const pollJobStatus = useJobPolling(userId);
  const [queryTitle, setQueryTitle] = useState(title);
  useEffect(() => {
    const timer = setTimeout(() => setQueryTitle(title), 250);
    return () => clearTimeout(timer);
  }, [title]);

  // 1. Get raw/filtered job list
  const jobsQuery = useQuery({
    queryKey: ['jobs', userId, hoursOld, queryTitle, location],
    queryFn: async ({ signal }) => {
      const response = await apiClient.get('/jobs/list', {
        params: { hours_old: hoursOld, title: queryTitle, location },
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
    enabled: !!userId && includeMatches,
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
