import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getDatabases,
  getConfig,
  getConfigOverrides,
  getEditableConfig,
  getPipelineStatus,
  resetConfigCategory,
  runPipeline,
  type PipelineRunRequest,
  updateConfigCategory,
} from '@/api';
import type { ConfigCategory } from '@/types';

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

export function useEditableConfig() {
  return useQuery({
    queryKey: ['config-editable'],
    queryFn: getEditableConfig,
    staleTime: 30000,
  });
}

export function useConfigOverrides() {
  return useQuery({
    queryKey: ['config-overrides'],
    queryFn: getConfigOverrides,
    staleTime: 30000,
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

export function useUpdateConfigCategory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      category,
      updates,
    }: {
      category: ConfigCategory | string;
      updates: Record<string, string | number | boolean | null>;
    }) => updateConfigCategory(category, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
      queryClient.invalidateQueries({ queryKey: ['config-editable'] });
      queryClient.invalidateQueries({ queryKey: ['config-overrides'] });
    },
  });
}

export function useResetConfigCategory() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (category: ConfigCategory | string) => resetConfigCategory(category),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] });
      queryClient.invalidateQueries({ queryKey: ['config-editable'] });
      queryClient.invalidateQueries({ queryKey: ['config-overrides'] });
    },
  });
}
