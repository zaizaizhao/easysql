import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { DatabaseInfo } from '@/types';

interface AppState {
  currentDatabase: string | null;
  databases: DatabaseInfo[];
  theme: 'light' | 'dark';
  sidebarCollapsed: boolean;
  
  setCurrentDatabase: (dbName: string | null) => void;
  setDatabases: (databases: DatabaseInfo[]) => void;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleTheme: () => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      currentDatabase: null,
      databases: [],
      theme: 'light',
      sidebarCollapsed: false,

      setCurrentDatabase: (dbName) => set({ currentDatabase: dbName }),
      setDatabases: (databases) => set({ databases }),
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((state) => ({ theme: state.theme === 'light' ? 'dark' : 'light' })),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
    }),
    {
      name: 'easysql-app-store',
      partialize: (state) => ({
        currentDatabase: state.currentDatabase,
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
);
