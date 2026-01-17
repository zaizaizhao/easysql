import { Space, Button, Tag, Typography, Card } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface ClarificationButtonsProps {
  questions: string[];
  onSelect: (answer: string) => void;
  disabled?: boolean;
}

export function ClarificationButtons({ questions, onSelect, disabled }: ClarificationButtonsProps) {
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
            {isSingleQuestion ? '需要您确认：' : '请回答以下问题：'}
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
          <Tag color="blue">您可以在下方输入框中回答，或点击快捷选项</Tag>
        </div>

        <Space wrap style={{ marginTop: 4 }}>
          <Button size="small" onClick={() => onSelect('是')} disabled={disabled}>
            是
          </Button>
          <Button size="small" onClick={() => onSelect('否')} disabled={disabled}>
            否
          </Button>
          <Button size="small" onClick={() => onSelect('按第一种方式')} disabled={disabled}>
            按第一种方式
          </Button>
          <Button size="small" onClick={() => onSelect('按第二种方式')} disabled={disabled}>
            按第二种方式
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
