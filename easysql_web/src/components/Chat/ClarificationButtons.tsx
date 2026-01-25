import { useState, type KeyboardEvent } from 'react';
import { Space, Button, Card, theme, Input } from 'antd';
import { QuestionCircleOutlined, SendOutlined, LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { TextArea } = Input;

interface ClarificationButtonsProps {
  questions: string[];
  onSelect: (answer: string) => void;
  disabled?: boolean;
  isLoading?: boolean;
}

export function ClarificationButtons({ questions, onSelect, disabled, isLoading }: ClarificationButtonsProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [inputValue, setInputValue] = useState('');
  
  if (!questions || questions.length === 0) return null;

  const handleSubmit = () => {
    const trimmed = inputValue.trim();
    if (!trimmed || disabled || isLoading) return;
    onSelect(trimmed);
    setInputValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleQuickAnswer = (answer: string) => {
    if (disabled || isLoading) return;
    onSelect(answer);
  };

  return (
    <Card
      size="small"
      style={{
        marginTop: 12,
        background: token.colorWarningBg,
        border: `1px solid ${token.colorWarningBorder}`,
      }}
    >
      <Space orientation="vertical" style={{ width: '100%' }} size="middle">
        <Space>
          <QuestionCircleOutlined style={{ color: token.colorWarning, fontSize: 16 }} />
          <span style={{ color: token.colorWarningText, fontWeight: 500 }}>
            {t('clarification.needConfirm')}
          </span>
        </Space>

        <div style={{ paddingLeft: 4 }}>
          {questions.map((question, index) => (
            <div key={index} style={{ 
              color: token.colorText, 
              marginBottom: questions.length > 1 ? 4 : 0 
            }}>
              {questions.length > 1 && `${index + 1}. `}
              {question}
            </div>
          ))}
        </div>

        <Space wrap size="small">
          <Button size="small" onClick={() => handleQuickAnswer(t('clarification.optionYes'))} disabled={disabled || isLoading}>
            {t('clarification.optionYes')}
          </Button>
          <Button size="small" onClick={() => handleQuickAnswer(t('clarification.optionNo'))} disabled={disabled || isLoading}>
            {t('clarification.optionNo')}
          </Button>
          <Button size="small" onClick={() => handleQuickAnswer(t('clarification.optionFirst'))} disabled={disabled || isLoading}>
            {t('clarification.optionFirst')}
          </Button>
          <Button size="small" onClick={() => handleQuickAnswer(t('clarification.optionSecond'))} disabled={disabled || isLoading}>
            {t('clarification.optionSecond')}
          </Button>
        </Space>

        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('clarification.inputPlaceholder') + '…'}
            disabled={disabled || isLoading}
            autoSize={{ minRows: 1, maxRows: 3 }}
            style={{ 
              flex: 1,
              background: token.colorBgContainer,
              borderColor: token.colorBorder,
            }}
            autoComplete="off"
          />
          <Button
            type="primary"
            icon={isLoading ? <LoadingOutlined /> : <SendOutlined />}
            onClick={handleSubmit}
            disabled={!inputValue.trim() || disabled || isLoading}
            style={{ height: 32 }}
            aria-label={t('chat.send')}
          />
        </div>
      </Space>
    </Card>
  );
}
