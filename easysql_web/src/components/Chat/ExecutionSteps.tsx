
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
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import type { StepTrace } from '@/stores/chatStore';

interface ExecutionStepsProps {
  trace?: StepTrace[];
  isStreaming?: boolean;
}

const { Text } = Typography;

const STEP_ICONS: Record<string, React.ReactNode> = {
  shift_detect: <SafetyCertificateOutlined />,
  retrieve_hint: <SearchOutlined />,
  analyze: <RobotOutlined />,
  clarify: <QuestionCircleOutlined />,
  retrieve: <DatabaseOutlined />,
  build_context: <BuildOutlined />,
  retrieve_code: <CodeOutlined />,
  generate_sql: <CodeOutlined />,
  validate_sql: <CheckCircleOutlined />,
};

// Full flow (Plan Mode)
const PIPELINE_FULL = [
  'retrieve_hint',
  'analyze',
  'clarify',
  'retrieve',
  'build_context',
  'retrieve_code',
  'generate_sql',
  'validate_sql'
];

// Fast flow (Fast Mode)
const PIPELINE_FAST = [
  'retrieve',
  'build_context',
  'retrieve_code',
  'generate_sql',
  'validate_sql'
];

// Follow-up flow (Short - No Shift)
const PIPELINE_FOLLOWUP_SHORT = [
  'shift_detect',
  'generate_sql',
  'validate_sql'
];

// Follow-up flow (Long - Shift Detected)
const PIPELINE_FOLLOWUP_LONG = [
  'shift_detect',
  'retrieve_hint', // or retrieve depending on mode, but usually hint in plan mode
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
  const executedNodes = new Set(trace.map(s => s.node));

  // Determine which pipeline to show
  let currentPipeline = PIPELINE_FULL;

  if (executedNodes.has('shift_detect')) {
    if (executedNodes.has('retrieve') || executedNodes.has('retrieve_hint')) {
      // Follow-up with shift detected (re-retrieval)
      currentPipeline = PIPELINE_FOLLOWUP_LONG;
      
      // Special handling: if we jumped straight to retrieve (fast mode), filter out plan-mode steps
      if (!executedNodes.has('retrieve_hint') && executedNodes.has('retrieve')) {
         currentPipeline = ['shift_detect', ...PIPELINE_FAST];
      }
    } else {
      // Follow-up without shift (direct generation)
      currentPipeline = PIPELINE_FOLLOWUP_SHORT;
    }
  } else {
    // Initial query
    if (!executedNodes.has('retrieve_hint') && executedNodes.has('retrieve')) {
      currentPipeline = PIPELINE_FAST;
    }
  }

  let lastActiveIndex = -1;
  currentPipeline.forEach((step, index) => {
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
        items={currentPipeline.map((stepKey, index) => {
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
