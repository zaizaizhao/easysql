import { useState } from 'react';
import { Avatar, Typography, Space, Spin, Tag, theme, Flex } from 'antd';
import { UserOutlined, RobotOutlined, TableOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { SQLBlock } from './SQLBlock';
import { ExecutionSteps } from './ExecutionSteps';
import { ClarificationButtons } from './ClarificationButtons';
import { AgentThinking } from './AgentThinking';
import { useChatStore } from '@/stores';
import type { ChatMessage } from '@/types';

const { Text, Paragraph } = Typography;

interface MessageItemProps {
  message: ChatMessage;
  onClarificationSelect?: (answer: string) => void;
  isLoading?: boolean;
  userQuestion?: string;
  isLatestAssistant?: boolean;
}

export function MessageItem({
  message,
  onClarificationSelect,
  isLoading,
  userQuestion,
  isLatestAssistant,
}: MessageItemProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { sessionId } = useChatStore();
  const isUser = message.role === 'user';
  const [showAllTables, setShowAllTables] = useState(false);
  const turnScopedMessageId =
    sessionId && message.turnId ? `turn_${sessionId}_${message.turnId}` : undefined;
  const fewShotMessageIds = Array.from(
    new Set(
      [message.serverId, turnScopedMessageId, message.id].filter(
        (value): value is string => Boolean(value)
      )
    )
  );

  return (
    <Flex
      gap={12}
      vertical={false}
      style={{
        padding: '16px 0',
        flexDirection: isUser ? 'row-reverse' : 'row',
      }}
    >
      <Avatar
        icon={isUser ? <UserOutlined /> : <RobotOutlined />}
        style={{
          backgroundColor: isUser ? token.colorPrimary : '#52c41a',
          flexShrink: 0,
        }}
      />

      <Flex
        vertical
        align={isUser ? 'flex-end' : 'flex-start'}
        style={{ width: isUser ? undefined : '75%', maxWidth: isUser ? '60%' : undefined }}
      >
        {isUser ? (
          <div
            style={{
              background: token.colorPrimaryBg,
              padding: '12px 16px',
              borderRadius: 12,
              borderTopRightRadius: 4,
            }}
          >
            <Text style={{ color: token.colorText }}>{message.content}</Text>
          </div>
        ) : (
          <div
            style={{
              background: token.colorFillQuaternary,
              padding: '12px 16px',
              borderRadius: 12,
              borderTopLeftRadius: 4,
              width: '100%',
            }}
          >
            {message.isStreaming && !message.sql && (
              <Space>
                <Spin size="small" />
                <Text type="secondary">{t('chat.thinking')}</Text>
              </Space>
            )}

            {message.retrievalSummary && (
              <div style={{ marginBottom: 8 }}>
                <Space size={4}>
                  <TableOutlined style={{ color: token.colorPrimary }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t('chat.retrievedTables', { count: message.retrievalSummary.tablesCount })}
                  </Text>
                </Space>
                <div style={{ marginTop: 4 }}>
                  {message.retrievalSummary.tables.slice(0, showAllTables ? undefined : 5).map((table: string) => (
                    <Tag key={table} style={{ marginBottom: 4 }}>{table}</Tag>
                  ))}
                  {!showAllTables && message.retrievalSummary.tables.length > 5 && (
                    <Tag
                      style={{ cursor: 'pointer', borderStyle: 'dashed' }}
                      onClick={() => setShowAllTables(true)}
                    >
                      {t('common.more', { count: message.retrievalSummary.tables.length - 5 })}
                    </Tag>
                  )}
                  {showAllTables && message.retrievalSummary.tables.length > 5 && (
                    <Tag
                      style={{ cursor: 'pointer', borderStyle: 'dashed' }}
                      onClick={() => setShowAllTables(false)}
                    >
                      {t('common.collapse')}
                    </Tag>
                  )}
                </div>
              </div>
            )}

            {message.trace && message.trace.length > 0 && (
              <ExecutionSteps trace={message.trace} isStreaming={message.isStreaming} />
            )}

            {(message.agentSteps || message.thinkingContent) && (
              <AgentThinking
                thinkingContent={message.thinkingContent}
                agentSteps={message.agentSteps}
                isStreaming={message.isStreaming}
              />
            )}

            {message.content && (
              <Paragraph style={{ marginBottom: 8 }}>
                {message.content}
              </Paragraph>
            )}

            {message.userAnswer && (
              <div style={{
                marginTop: 12,
                marginBottom: 12,
                padding: '12px',
                background: token.colorFillTertiary,
                borderRadius: 8,
                borderLeft: `3px solid ${token.colorPrimary}`
              }}>
                {message.clarificationQuestions && message.clarificationQuestions.length > 0 && (
                  <div style={{ marginBottom: 12, paddingBottom: 12, borderBottom: `1px dashed ${token.colorBorder}` }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      {message.clarificationQuestions.length > 1 ? t('clarification.answerQuestions') : t('clarification.needConfirm')}
                    </Text>
                    <div style={{ fontSize: 13, color: token.colorTextSecondary }}>
                      {message.clarificationQuestions.map((q: string, idx: number) => (
                        <div key={idx}>{message.clarificationQuestions!.length > 1 ? `${idx + 1}. ${q}` : q}</div>
                      ))}
                    </div>
                  </div>
                )}

                <Text type="secondary" style={{ fontSize: 12 }}>{t('chat.yourAnswer')}</Text>
                <div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{message.userAnswer}</div>
              </div>
            )}

            {(!message.userAnswer && message.clarificationQuestions && message.clarificationQuestions.length > 0) && (
              <ClarificationButtons
                questions={message.clarificationQuestions}
                onSelect={(answer) => onClarificationSelect?.(answer)}
                disabled={message.isStreaming}
                isLoading={isLoading}
              />
            )}

            {message.sql && (
              <div style={{ marginTop: 12 }}>
                <SQLBlock
                  sql={message.sql}
                  validationPassed={message.validationPassed}
                  validationError={message.validationError}
                  autoExecute={!message.isStreaming}
                  question={userQuestion}
                  messageIds={fewShotMessageIds}
                  turnId={message.turnId}
                  isFewShot={message.isFewShot}
                  tablesUsed={message.retrievalSummary?.tables}
                  enableLlmCharts={
                    !!message.chartPlan ||
                    (!!message.turnId && !message.isHistorical) ||
                    (!!isLatestAssistant && !message.isHistorical)
                  }
                  chartPlan={message.chartPlan}
                  chartReasoning={message.chartReasoning}
                />
              </div>
            )}
          </div>
        )}

        <Text
          type="secondary"
          style={{ fontSize: 11, marginTop: 4 }}
        >
          {message.timestamp.toLocaleTimeString()}
        </Text>
      </Flex>
    </Flex>
  );
}
