
import { Steps, theme, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { 
  SearchOutlined, 
  DatabaseOutlined, 
  CodeOutlined, 
  RobotOutlined, 
  CheckCircleOutlined, 
  BuildOutlined,
  LoadingOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import type { StepTrace } from '@/stores/chatStore';

interface ExecutionStepsProps {
  trace?: StepTrace[];
  isStreaming?: boolean;
}

const { Text } = Typography;

const STEP_ICONS: Record<string, React.ReactNode> = {
  retrieve_hint: <SearchOutlined />,
  analyze: <RobotOutlined />,
  clarify: <QuestionCircleOutlined />,
  retrieve: <DatabaseOutlined />,
  build_context: <BuildOutlined />,
  retrieve_code: <CodeOutlined />,
  generate_sql: <CodeOutlined />,
  validate_sql: <CheckCircleOutlined />,
};

const PIPELINE_ORDER = [
  'retrieve_hint',
  'analyze',
  'clarify',
  'retrieve',
  'build_context',
  'retrieve_code',
  'generate_sql',
  'validate_sql'
];

export function ExecutionSteps({ trace = [], isStreaming }: ExecutionStepsProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  
  const executedStepsMap = new Map(trace.map(step => [step.node, step]));
  
  let lastActiveIndex = -1;
  PIPELINE_ORDER.forEach((step, index) => {
    if (executedStepsMap.has(step)) {
      lastActiveIndex = index;
    }
  });

  const getStepStatus = (stepKey: string, index: number) => {
    const executed = executedStepsMap.get(stepKey);
    
    if (executed) {
       const isLastExecuted = index === lastActiveIndex;
       if (isLastExecuted && isStreaming) return 'process';
       return 'finish';
    }

    if (index > lastActiveIndex) {
        return 'wait';
    }

    return 'skipped';
  };

  const getIcon = (stepKey: string, status: string) => {
     if (status === 'process') return <LoadingOutlined />;
     if (status === 'skipped') {
         return <div style={{ opacity: 0.3 }}>{STEP_ICONS[stepKey]}</div>;
     }
     return STEP_ICONS[stepKey];
  };

  const renderStepDescription = (stepKey: string) => {
      const data = executedStepsMap.get(stepKey)?.data;
      if (!data) return null;
      
      if (stepKey === 'retrieve_hint' && data.schema_hint) {
          return <Text type="secondary" style={{fontSize: 12}}>{t('chat.usedSchemaHint')}</Text>;
      }
      if (stepKey === 'retrieve' && data.retrieval_summary) {
          return <Text type="secondary" style={{fontSize: 12}}>{t('chat.tablesRetrieved', { count: data.retrieval_summary.tables_count })}</Text>;
      }
      if (stepKey === 'validate_sql') {
          return data.validation_passed ? 
            <Text type="success" style={{fontSize: 12}}>{t('steps.validationPassed')}</Text> : 
            <Text type="danger" style={{fontSize: 12}}>{t('steps.validationFailed')}</Text>;
      }
      return null;
  };

  return (
    <div style={{ 
      marginBottom: 16, 
      padding: '16px 24px', 
      background: token.colorFillQuaternary, 
      borderRadius: 12,
      overflowX: 'auto',
      minWidth: '600px'
    }}>
      <Steps
        size="small"
        items={PIPELINE_ORDER.map((stepKey, index) => {
          const status = getStepStatus(stepKey, index);

          const itemConfig = {
            key: stepKey,
            title: t(`steps.${stepKey}`),
            status: status === 'skipped' ? 'wait' : status as 'wait' | 'process' | 'finish' | 'error',
            icon: getIcon(stepKey, status),
          };
          
          if (executedStepsMap.has(stepKey)) {
             return {
                 ...itemConfig,
                 description: renderStepDescription(stepKey),
             };
          }
          
          return itemConfig;
        })}
      />
    </div>
  );
}
