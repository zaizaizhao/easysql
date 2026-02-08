import { useEffect } from 'react';
import { Select } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/stores';
import { supportedLanguages, type SupportedLanguage } from '@/i18n';

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const { locale, setLocale } = useAppStore();

  useEffect(() => {
    if (locale && i18n.language !== locale) {
      i18n.changeLanguage(locale);
    }
  }, [locale, i18n]);

  const handleChange = (value: SupportedLanguage) => {
    setLocale(value);
    i18n.changeLanguage(value);
  };

  const options = supportedLanguages.map((lang) => ({
    value: lang.code,
    label: t(lang.labelKey),
  }));

  return (
    <Select
      value={locale}
      onChange={handleChange}
      options={options}
      variant="borderless"
      suffixIcon={<GlobalOutlined />}
      style={{ width: 90 }}
    />
  );
}
