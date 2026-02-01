import { Typography, Statistic, theme } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import type { MetricCardData } from '@/types/chart';

const { Text } = Typography;

interface MetricCardProps {
  data: MetricCardData;
  height?: number;
}

export function MetricCard({ data, height = 120 }: MetricCardProps) {
  const { token } = theme.useToken();
  const numValue = typeof data.value === 'number' ? data.value : parseFloat(String(data.value));
  const isNumber = !isNaN(numValue);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height,
        padding: 24,
        background: token.colorBgContainer,
        borderRadius: 8,
      }}
    >
      {data.label && (
        <Text type="secondary" style={{ fontSize: 14, marginBottom: 8 }}>
          {data.label}
        </Text>
      )}
      <Statistic
        value={isNumber ? numValue : data.value}
        precision={data.precision ?? (isNumber && !Number.isInteger(numValue) ? 2 : 0)}
        prefix={data.prefix}
        suffix={data.suffix}
        valueStyle={{ fontSize: 36, fontWeight: 600, color: token.colorText }}
      />
      {data.trend && data.trendValue !== undefined && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
          {data.trend === 'up' ? (
            <ArrowUpOutlined style={{ color: token.colorSuccess, fontSize: 12 }} />
          ) : data.trend === 'down' ? (
            <ArrowDownOutlined style={{ color: token.colorError, fontSize: 12 }} />
          ) : null}
          <Text
            style={{
              fontSize: 12,
              color:
                data.trend === 'up'
                  ? token.colorSuccess
                  : data.trend === 'down'
                    ? token.colorError
                    : token.colorTextSecondary,
            }}
          >
            {data.trendValue}%
          </Text>
        </div>
      )}
    </div>
  );
}
