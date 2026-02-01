/**
 * ChartTypeSelector
 *
 * A dropdown/segmented control for switching between chart types.
 * Shows only chart types that are valid for the current data.
 */

import { Select, Tooltip, theme } from 'antd';
import {
  BarChartOutlined,
  LineChartOutlined,
  PieChartOutlined,
  DotChartOutlined,
  AreaChartOutlined,
  DashboardOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ChartType } from '@/types/chart';

interface ChartTypeSelectorProps {
  value: ChartType;
  onChange: (type: ChartType) => void;
  availableTypes: ChartType[];
  disabled?: boolean;
}

const CHART_TYPE_ICONS: Record<ChartType, React.ReactNode> = {
  bar: <BarChartOutlined />,
  horizontal_bar: <BarChartOutlined rotate={-90} />,
  line: <LineChartOutlined />,
  area: <AreaChartOutlined />,
  pie: <PieChartOutlined />,
  donut: <PieChartOutlined />,
  scatter: <DotChartOutlined />,
  metric_card: <DashboardOutlined />,
  grouped_bar: <BarChartOutlined />,
  stacked_bar: <BarChartOutlined />,
  stacked_area: <AreaChartOutlined />,
};

export function ChartTypeSelector({
  value,
  onChange,
  availableTypes,
  disabled,
}: ChartTypeSelectorProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  const options = availableTypes.map((type) => ({
    value: type,
    label: (
      <Tooltip title={t(`chart.types.${type}`)}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {CHART_TYPE_ICONS[type]}
          <span>{t(`chart.types.${type}`)}</span>
        </span>
      </Tooltip>
    ),
  }));

  return (
    <Select
      value={value}
      onChange={onChange}
      options={options}
      disabled={disabled}
      size="small"
      style={{
        minWidth: 120,
        borderColor: token.colorBorder,
      }}
      popupMatchSelectWidth={false}
    />
  );
}
