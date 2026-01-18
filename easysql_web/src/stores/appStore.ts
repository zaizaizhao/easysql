import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { DatabaseInfo } from '@/types';
import type { SupportedLanguage } from '@/i18n';

interface AppState {
  currentDatabase: string | null;
  databases: DatabaseInfo[];
  theme: 'light' | 'dark';
  locale: SupportedLanguage;
  sidebarCollapsed: boolean;
  
  setCurrentDatabase: (dbName: string | null) => void;
  setDatabases: (databases: DatabaseInfo[]) => void;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleTheme: () => void;
  setLocale: (locale: SupportedLanguage) => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      currentDatabase: null,
      databases: [],
      theme: 'light',
      locale: 'zh',
      sidebarCollapsed: false,

      setCurrentDatabase: (dbName) => set({ currentDatabase: dbName }),
      setDatabases: (databases) => set({ databases }),
      setTheme: (theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        set({ theme });
      },
      toggleTheme: () => set((state) => {
        const newTheme = state.theme === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', newTheme);
        return { theme: newTheme };
      }),
      setLocale: (locale) => set({ locale }),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
    }),
    {
      name: 'easysql-app-store',
      partialize: (state) => ({
        currentDatabase: state.currentDatabase,
        theme: state.theme,
        locale: state.locale,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
      onRehydrateStorage: () => (state) => {
        // Sync theme to DOM after hydration from localStorage
        if (state?.theme) {
          document.documentElement.setAttribute('data-theme', state.theme);
        }
      },
    }
  )
);
