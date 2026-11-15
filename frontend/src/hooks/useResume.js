import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../api/client';

export const useResume = () => {
  const queryClient = useQueryClient();

  const uploadResumeMutation = useMutation({
    mutationFn: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      const response = await apiClient.post('/resume/upload', formData);
      return response.data;
    },
    onSuccess: () => {
      // Invalidate profile query to refetch new data
      queryClient.invalidateQueries({ queryKey: ['profile'] });
    },
  });

  const analyzeResumeMutation = useMutation({
    mutationFn: async ({ target_role }) => {
      const response = await apiClient.post('/resume/analyze', { target_role });
      return response.data; // { job_id: ..., status: ... }
    },
  });

  // Helper to poll job status
  const pollJobStatus = async (jobId, onComplete, onError, intervalMs = 3000) => {
    const timer = setInterval(async () => {
      try {
        const response = await apiClient.get(`/jobs/${jobId}/status`);
        const { status, result, error } = response.data;
        
        if (status === 'completed') {
          clearInterval(timer);
          onComplete(result);
        } else if (status === 'failed') {
          clearInterval(timer);
          onError(error || 'Analysis failed.');
        }
      } catch (err) {
        clearInterval(timer);
        onError(err.message || 'Error polling job status.');
      }
    }, intervalMs);
    
    return () => clearInterval(timer);
  };

  return {
    uploadResume: uploadResumeMutation.mutateAsync,
    isUploading: uploadResumeMutation.isPending,
    analyzeResume: analyzeResumeMutation.mutateAsync,
    isAnalyzing: analyzeResumeMutation.isPending,
    pollJobStatus,
  };
};
