import { useQuery } from '@tanstack/react-query';
import apiClient from '../api/client';

export const useProfile = () => {
  const { data: profile, isLoading, error, refetch } = useQuery({
    queryKey: ['profile'],
    queryFn: async () => {
      try {
        const response = await apiClient.get('/resume/profile');
        return response.data;
      } catch (err) {
        if (err.response && err.response.status === 404) {
          return null; // Profile doesn't exist yet
        }
        throw err;
      }
    },
    retry: false,
  });

  return {
    profile,
    isLoading,
    error,
    refetch,
    hasProfile: !!profile,
  };
};
