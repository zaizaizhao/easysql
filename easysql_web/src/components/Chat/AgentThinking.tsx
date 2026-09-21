import { useState, useRef, useEffect } from 'react';
import { Typography, theme } from 'antd';
import { ThunderboltOutlined, DownOutlined, RightOutlined, CheckCircleOutlined, LoadingOutlined, ToolOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { AgentStep } from '@/types';

const { Text, Paragraph } = Typography;

const contextToolLabels: Record<string, string> = {
  describe_database_scope: '查看数据库范围', browse_wiki: '浏览知识目录',
  list_wiki_pages: '查看知识摘要', search_knowledge: '检索业务知识',
  read_wiki_page: '读取知识与原文依据', search_tables: '查找相关表',
  search_columns: '查找相关字段', list_database_tables: '查看数据库表',
  get_table_schema: '核对表结构', expand_related_tables: '扩展关联表',
  find_join_paths: '查找跨库关联', search_sql_examples: '查找 SQL 示例',
  check_dblink_routes: '检查跨库连接', assess_context: '检查上下文是否充分',
  submit_final_sql: '验证并提交 SQL', ask_clarification: '请求澄清',
  report_insufficient_context: '说明缺失的上下文',
};

interface AgentThinkingProps {
  thinkingContent?: string;
  agentSteps?: AgentStep[];
  isStreaming?: boolean;
}

export function AgentThinking({ thinkingContent, agentSteps = [], isStreaming }: AgentThinkingProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [expanded, setExpanded] = useState(true);
  const thinkingRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when thinking content updates
  useEffect(() => {
    if (thinkingRef.current && isStreaming) {
      thinkingRef.current.scrollTop = thinkingRef.current.scrollHeight;
    }
  }, [thinkingContent, isStreaming]);

  const hasContent = thinkingContent || agentSteps.length > 0;
  if (!hasContent) return null;

  const groupedByIteration = agentSteps.reduce((acc, step) => {
    const key = step.iteration;
    if (!acc[key]) acc[key] = [];
    acc[key].push(step);
    return acc;
  }, {} as Record<number, AgentStep[]>);

  const iterations = Object.keys(groupedByIteration).map(Number).sort((a, b) => a - b);
  const currentIteration = iterations[iterations.length - 1] || 0;

  const renderToolStep = (step: AgentStep) => {
    if (step.action === 'tool_start') {
      return (
        <div key={`${step.iteration}-start-${step.timestamp}`} style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: 8,
          padding: '4px 0',
          color: token.colorTextSecondary,
          fontSize: 12,
        }}>
          <ToolOutlined style={{ color: token.colorPrimary }} />
          <Text type="secondary">{t('agent.callingTool')}: </Text>
          <Text>{step.tool ? contextToolLabels[step.tool] ?? step.tool : ''}</Text>
          {step.inputPreview && (
            <Text type="secondary" ellipsis style={{ maxWidth: 300 }}>
              ({step.inputPreview})
            </Text>
          )}
        </div>
      );
    }

    if (step.action === 'tool_end') {
      return (
        <div key={`${step.iteration}-end-${step.timestamp}`} style={{ 
          display: 'flex', 
          alignItems: 'flex-start', 
          gap: 8,
          padding: '4px 0 8px 0',
          fontSize: 12,
        }}>
          {step.success ? (
            <CheckCircleOutlined style={{ color: token.colorSuccess, marginTop: 2 }} />
          ) : (
            <CheckCircleOutlined style={{ color: token.colorError, marginTop: 2 }} />
          )}
          <div style={{ flex: 1 }}>
            <Text type={step.success ? 'success' : 'danger'}>
              {step.success ? t('agent.toolSuccess') : t('agent.toolFailed')}
            </Text>
            {step.outputPreview && (
              <Paragraph 
                type="secondary" 
                style={{ 
                  fontSize: 11, 
                  margin: '4px 0 0 0',
                  background: token.colorFillTertiary,
                  padding: 8,
                  borderRadius: 4,
                  whiteSpace: 'pre-wrap',
                  maxHeight: 100,
                  overflow: 'auto',
                }}
              >
                {step.outputPreview}
              </Paragraph>
            )}
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div style={{
      marginBottom: 12,
      background: token.colorFillQuaternary,
      borderRadius: 8,
      border: `1px solid ${token.colorBorderSecondary}`,
      overflow: 'hidden',
    }}>
      <div 
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          cursor: 'pointer',
          background: token.colorFillTertiary,
        }}
      >
        {expanded ? <DownOutlined style={{ fontSize: 10 }} /> : <RightOutlined style={{ fontSize: 10 }} />}
        <ThunderboltOutlined style={{ color: token.colorWarning }} />
        <Text strong style={{ fontSize: 12 }}>
          {t('agent.thinking')}
        </Text>
        {isStreaming && <LoadingOutlined style={{ color: token.colorPrimary }} />}
        {iterations.length > 0 && (
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>
            {t('agent.iteration', { current: currentIteration })}
          </Text>
        )}
      </div>

      {expanded && (
        <div style={{ padding: '8px 12px' }}>
          {iterations.map((iteration) => (
            <div key={iteration}>
              {groupedByIteration[iteration].map(renderToolStep)}
            </div>
          ))}

          {thinkingContent && (
            <div 
              ref={thinkingRef}
              style={{
              marginTop: iterations.length > 0 ? 8 : 0,
              padding: 8,
              background: token.colorBgContainer,
              borderRadius: 4,
              fontSize: 13,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              maxHeight: 200,
              overflow: 'auto',
            }}>
              <Text>{thinkingContent}</Text>
              {isStreaming && <span className="typing-cursor">▋</span>}
            </div>
          )}
        </div>
      )}

      <style>{`
        .typing-cursor {
          animation: blink 1s infinite;
          color: ${token.colorPrimary};
        }
        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
