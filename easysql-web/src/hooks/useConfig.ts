import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getDatabases, getConfig, getPipelineStatus, runPipeline, type PipelineRunRequest } from '@/api';

export function useDatabases() {
  return useQuery({
    queryKey: ['databases'],
    queryFn: getDatabases,
    staleTime: 60000,
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
    staleTime: 60000,
  });
}

export function usePipelineStatus() {
  return useQuery({
    queryKey: ['pipeline-status'],
    queryFn: getPipelineStatus,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === 'running' ? 2000 : false;
    },
  });
}

export function useRunPipeline() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (request: PipelineRunRequest) => runPipeline(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline-status'] });
    },
  });
}
