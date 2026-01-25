import { Button, Tooltip } from 'antd';
import { SunOutlined, MoonOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/stores';

export function ThemeToggle() {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useAppStore();
  const isDark = theme === 'dark';

  return (
    <Tooltip title={isDark ? t('common.switchToLight') : t('common.switchToDark')}>
      <Button
        type="text"
        icon={isDark ? <SunOutlined /> : <MoonOutlined />}
        onClick={toggleTheme}
        aria-label={isDark ? t('common.switchToLight') : t('common.switchToDark')}
      />
    </Tooltip>
  );
}
