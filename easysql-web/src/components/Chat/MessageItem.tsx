import { useState } from 'react';
import { Avatar, Typography, Space, Spin, Tag } from 'antd';
import { UserOutlined, RobotOutlined, TableOutlined } from '@ant-design/icons';
import { SQLBlock } from './SQLBlock';
import { ExecutionSteps } from './ExecutionSteps';
import { ClarificationButtons } from './ClarificationButtons';
import type { ChatMessage } from '@/stores';

const { Text, Paragraph } = Typography;

interface MessageItemProps {
  message: ChatMessage;
  onClarificationSelect?: (answer: string) => void;
}

export function MessageItem({ message, onClarificationSelect }: MessageItemProps) {
  const isUser = message.role === 'user';
  const [showAllTables, setShowAllTables] = useState(false);

  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        padding: '16px 0',
        flexDirection: isUser ? 'row-reverse' : 'row',
      }}
    >
      <Avatar
        icon={isUser ? <UserOutlined /> : <RobotOutlined />}
        style={{
          backgroundColor: isUser ? '#1677ff' : '#52c41a',
          flexShrink: 0,
        }}
      />

      <div
        style={{
          maxWidth: '80%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: isUser ? 'flex-end' : 'flex-start',
        }}
      >
        {isUser ? (
          <div
            style={{
              background: 'var(--user-message-bg)',
              padding: '12px 16px',
              borderRadius: 12,
              borderTopRightRadius: 4,
            }}
          >
            <Text>{message.content}</Text>
          </div>
        ) : (
          <div
            style={{
              background: 'var(--assistant-message-bg)',
              padding: '12px 16px',
              borderRadius: 12,
              borderTopLeftRadius: 4,
              width: '100%',
            }}
          >
            {message.isStreaming && !message.sql && (
              <Space>
                <Spin size="small" />
                <Text type="secondary">思考中...</Text>
              </Space>
            )}

            {message.retrievalSummary && (
              <div style={{ marginBottom: 8 }}>
                <Space size={4}>
                  <TableOutlined style={{ color: '#1677ff' }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    检索到 {message.retrievalSummary.tablesCount} 张相关表：
                  </Text>
                </Space>
                <div style={{ marginTop: 4 }}>
                  {message.retrievalSummary.tables.slice(0, showAllTables ? undefined : 5).map((table) => (
                    <Tag key={table} style={{ marginBottom: 4 }}>{table}</Tag>
                  ))}
                  {!showAllTables && message.retrievalSummary.tables.length > 5 && (
                    <Tag 
                      style={{ cursor: 'pointer', borderStyle: 'dashed' }}
                      onClick={() => setShowAllTables(true)}
                    >
                      +{message.retrievalSummary.tables.length - 5} 更多
                    </Tag>
                  )}
                  {showAllTables && message.retrievalSummary.tables.length > 5 && (
                    <Tag 
                      style={{ cursor: 'pointer', borderStyle: 'dashed' }}
                      onClick={() => setShowAllTables(false)}
                    >
                      收起
                    </Tag>
                  )}
                </div>
              </div>
            )}

            {message.trace && message.trace.length > 0 && (
              <ExecutionSteps trace={message.trace} isStreaming={message.isStreaming} />
            )}

            {message.content && (
              <Paragraph style={{ marginBottom: message.sql ? 0 : undefined }}>
                {message.content}
              </Paragraph>
            )}

            {message.sql && (
              <SQLBlock
                sql={message.sql}
                validationPassed={message.validationPassed}
                validationError={message.validationError}
              />
            )}

            {message.userAnswer && (
              <div style={{ 
                marginTop: 12, 
                padding: '8px 12px', 
                background: 'rgba(22, 119, 255, 0.1)', 
                borderRadius: 8,
                borderLeft: '3px solid #1677ff'
              }}>
                <Text type="secondary" style={{ fontSize: 12 }}>您的回答：</Text>
                <div style={{ fontSize: 14 }}>{message.userAnswer}</div>
              </div>
            )}

            {(!message.userAnswer && message.clarificationQuestions && message.clarificationQuestions.length > 0) && (
              <ClarificationButtons
                questions={message.clarificationQuestions}
                onSelect={(answer) => onClarificationSelect?.(answer)}
                disabled={message.isStreaming}
              />
            )}
          </div>
        )}

        <Text
          type="secondary"
          style={{ fontSize: 11, marginTop: 4 }}
        >
          {message.timestamp.toLocaleTimeString()}
        </Text>
      </div>
    </div>
  );
}
