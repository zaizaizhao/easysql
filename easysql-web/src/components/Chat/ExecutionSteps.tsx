
import { Steps, theme, Typography } from 'antd';
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

const STEP_CONFIG: Record<string, { title: string; icon: React.ReactNode }> = {
  retrieve_hint: { title: '分析Schema', icon: <SearchOutlined /> },
  analyze: { title: '理解意图', icon: <RobotOutlined /> },
  clarify: { title: '需要澄清', icon: <QuestionCircleOutlined /> },
  retrieve: { title: '检索Schema', icon: <DatabaseOutlined /> },
  build_context: { title: '构建上下文', icon: <BuildOutlined /> },
  retrieve_code: { title: '业务逻辑', icon: <CodeOutlined /> },
  generate_sql: { title: '生成SQL', icon: <CodeOutlined /> },
  validate_sql: { title: '验证SQL', icon: <CheckCircleOutlined /> },
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
  const { token } = theme.useToken();
  
  // Create a map for quick lookup of executed steps
  const executedStepsMap = new Map(trace.map(t => [t.node, t]));
  
  // Find the index of the last executed step in our pipeline order
  // This helps us determine which future steps are pending vs skipped
  let lastActiveIndex = -1;
  PIPELINE_ORDER.forEach((step, index) => {
    if (executedStepsMap.has(step)) {
      lastActiveIndex = index;
    }
  });

  const getStepStatus = (stepKey: string, index: number) => {
    const executed = executedStepsMap.get(stepKey);
    
    if (executed) {
       // If it's the very last step and we are still streaming, it's processing
       // Otherwise it's finished
       const isLastExecuted = index === lastActiveIndex;
       if (isLastExecuted && isStreaming) return 'process';
       return 'finish';
    }

    // If we haven't reached this step yet (index > lastActiveIndex), it's waiting
    if (index > lastActiveIndex) {
        return 'wait';
    }

    // If we passed this step index but didn't execute it, it was skipped
    return 'skipped';
  };

  const getIcon = (stepKey: string, status: string) => {
     if (status === 'process') return <LoadingOutlined />;
     if (status === 'skipped') {
         return <div style={{ opacity: 0.3 }}>{STEP_CONFIG[stepKey].icon}</div>;
     }
     // Optional: add check mark for finished steps if we want more visual confirmation
     // But Antd's finish status already handles color.
     return STEP_CONFIG[stepKey].icon;
  };

  const renderStepDescription = (stepKey: string) => {
      const data = executedStepsMap.get(stepKey)?.data;
      if (!data) return null;
      
      // Customize hover content based on step type
      if (stepKey === 'retrieve_hint' && data.schema_hint) {
          return <Text type="secondary" style={{fontSize: 12}}>使用了Schema提示</Text>;
      }
      if (stepKey === 'retrieve' && data.retrieval_summary) {
          return <Text type="secondary" style={{fontSize: 12}}>检索到 {data.retrieval_summary.tables_count} 张表</Text>;
      }
      if (stepKey === 'validate_sql') {
          return data.validation_passed ? 
            <Text type="success" style={{fontSize: 12}}>验证通过</Text> : 
            <Text type="danger" style={{fontSize: 12}}>验证失败</Text>;
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
          const config = STEP_CONFIG[stepKey];

          const itemConfig = {
            key: stepKey,
            title: config.title,
            status: status === 'skipped' ? 'wait' : status as any,
            icon: getIcon(stepKey, status),
          };
          
          if (executedStepsMap.has(stepKey)) {
             return {
                 ...itemConfig,
                 description: renderStepDescription(stepKey),
                 // Highlight completed steps with a specific style if needed, 
                 // though Antd default 'finish' style (blue) is usually good.
             };
          }
          
          return itemConfig;
        })}
      />
    </div>
  );
}
