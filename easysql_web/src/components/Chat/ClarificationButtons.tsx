import { Space, Button, Tag, Typography, Card } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

interface ClarificationButtonsProps {
  questions: string[];
  onSelect: (answer: string) => void;
  disabled?: boolean;
}

export function ClarificationButtons({ questions, onSelect, disabled }: ClarificationButtonsProps) {
  const { t } = useTranslation();
  
  if (!questions || questions.length === 0) return null;

  const isSingleQuestion = questions.length === 1;

  return (
    <Card
      size="small"
      style={{
        marginTop: 12,
        background: 'var(--clarification-bg, #fffbe6)',
        border: '1px solid #ffe58f',
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space>
          <QuestionCircleOutlined style={{ color: '#faad14' }} />
          <Text strong style={{ color: '#d48806' }}>
            {isSingleQuestion ? t('clarification.needConfirm') : t('clarification.answerQuestions')}
          </Text>
        </Space>

        {questions.map((question, index) => (
          <div key={index} style={{ paddingLeft: 20 }}>
            <Text>
              {questions.length > 1 && `${index + 1}. `}
              {question}
            </Text>
          </div>
        ))}

        <div style={{ marginTop: 8 }}>
          <Tag color="blue">{t('clarification.inputHint')}</Tag>
        </div>

        <Space wrap style={{ marginTop: 4 }}>
          <Button size="small" onClick={() => onSelect(t('clarification.optionYes'))} disabled={disabled}>
            {t('clarification.optionYes')}
          </Button>
          <Button size="small" onClick={() => onSelect(t('clarification.optionNo'))} disabled={disabled}>
            {t('clarification.optionNo')}
          </Button>
          <Button size="small" onClick={() => onSelect(t('clarification.optionFirst'))} disabled={disabled}>
            {t('clarification.optionFirst')}
          </Button>
          <Button size="small" onClick={() => onSelect(t('clarification.optionSecond'))} disabled={disabled}>
            {t('clarification.optionSecond')}
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
