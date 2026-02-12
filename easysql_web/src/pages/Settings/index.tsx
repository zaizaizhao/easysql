import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Descriptions,
  Divider,
  Input,
  InputNumber,
  Progress,
  Select,
  Space,
  Spin,
  Switch,
  Tabs,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  RollbackOutlined,
  SaveOutlined,
  SearchOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import {
  useConfig,
  useEditableConfig,
  usePipelineStatus,
  useResetConfigCategory,
  useRunPipeline,
  useUpdateConfigCategory,
} from '@/hooks';
import type { EditableConfigItem } from '@/types';

import './index.css';

const { Title, Text } = Typography;

type DraftValue = string | number | boolean | null;
type DraftState = Record<string, Record<string, DraftValue>>;
type EnumOption = { label: string; value: string };
type FieldEntry = [string, EditableConfigItem];

type StatusMeta = {
  icon: ReactNode;
  color: string;
  text: string;
};

function normalizeForCompare(value: unknown): string {
  if (value === null || value === undefined) {
    return 'null';
  }
  return String(value);
}

const CATEGORY_DISPLAY_ORDER = ['llm', 'retrieval', 'few_shot', 'code_context', 'langfuse'];

const LLM_FIELD_DISPLAY_ORDER = [
  'query_mode',
  'openai_llm_model',
  'temperature',
  'openai_api_key',
  'openai_api_base',
  'google_llm_model',
  'google_api_key',
  'anthropic_llm_model',
  'anthropic_api_key',
  'model_planning',
  'use_agent_mode',
  'agent_max_iterations',
  'max_sql_retries',
];

function sortByPreferredOrder(items: string[], preferred: string[]): string[] {
  const indexMap = new Map(preferred.map((value, index) => [value, index]));
  return [...items].sort((a, b) => {
    const aIndex = indexMap.get(a);
    const bIndex = indexMap.get(b);

    if (aIndex !== undefined && bIndex !== undefined) {
      return aIndex - bIndex;
    }
    if (aIndex !== undefined) {
      return -1;
    }
    if (bIndex !== undefined) {
      return 1;
    }
    return a.localeCompare(b);
  });
}

function getOrderedFieldEntries(category: string, fields: Record<string, EditableConfigItem>): FieldEntry[] {
  const entries = Object.entries(fields) as FieldEntry[];
  if (category !== 'llm') {
    return entries;
  }

  const indexMap = new Map(LLM_FIELD_DISPLAY_ORDER.map((key, index) => [key, index]));
  return entries
    .map(([key, item], index) => {
      const preferredIndex = indexMap.get(key);
      return {
        key,
        item,
        index,
        preferredIndex: preferredIndex === undefined ? Number.MAX_SAFE_INTEGER : preferredIndex,
      };
    })
    .sort((a, b) => {
      if (a.preferredIndex !== b.preferredIndex) {
        return a.preferredIndex - b.preferredIndex;
      }
      return a.index - b.index;
    })
    .map(({ key, item }) => [key, item]);
}

export default function SettingsPage() {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  const { data: config, isLoading: configLoading } = useConfig();
  const { data: editableConfig, isLoading: editableLoading } = useEditableConfig();
  const { data: pipelineStatus, isLoading: statusLoading } = usePipelineStatus();

  const runPipeline = useRunPipeline();
  const updateConfig = useUpdateConfigCategory();
  const resetCategory = useResetConfigCategory();

  const [drafts, setDrafts] = useState<DraftState>({});
  const [categorySearch, setCategorySearch] = useState<Record<string, string>>({});
  const [isSavingAll, setIsSavingAll] = useState(false);

  useEffect(() => {
    if (!editableConfig) {
      return;
    }

    const next: DraftState = {};
    Object.entries(editableConfig).forEach(([category, fields]) => {
      next[category] = {};
      Object.entries(fields).forEach(([key, item]) => {
        next[category][key] = item.value as DraftValue;
      });
    });
    setDrafts(next);
  }, [editableConfig]);

  const categoryOrder = useMemo(() => {
    if (!editableConfig) {
      return [];
    }
    return sortByPreferredOrder(Object.keys(editableConfig), CATEGORY_DISPLAY_ORDER);
  }, [editableConfig]);

  const getCategoryLabel = (category: string): string =>
    t(`settings.categories.${category}`, { defaultValue: category });

  const getValueTypeLabel = (valueType: EditableConfigItem['value_type']): string =>
    t(`settings.valueTypes.${valueType}`, { defaultValue: valueType });

  const getFieldLabel = (category: string, key: string): string =>
    t(`settings.fields.${category}.${key}.label`, { defaultValue: key });

  const getFieldDescription = (category: string, key: string): string =>
    t(`settings.fields.${category}.${key}.description`, { defaultValue: '' });

  const getConstraintLabel = (code: string): string =>
    t(`settings.constraints.${code}`, { defaultValue: code });

  const getInvalidateTagLabel = (tag: string): string =>
    t(`settings.effects.${tag}`, { defaultValue: tag });

  const getEnumOptions = (
    category: string,
    key: string,
    item: EditableConfigItem,
  ): EnumOption[] | null => {
    if (!item.constraints.includes('enum_plan_fast')) {
      return null;
    }

    return [
      {
        value: 'plan',
        label: t(`settings.fields.${category}.${key}.options.plan`, {
          defaultValue: t('settings.queryModePlan'),
        }),
      },
      {
        value: 'fast',
        label: t(`settings.fields.${category}.${key}.options.fast`, {
          defaultValue: t('settings.queryModeFast'),
        }),
      },
    ];
  };

  const isSecretMasked = (item: EditableConfigItem, draftValue: DraftValue): boolean =>
    item.is_secret && typeof draftValue === 'string' && draftValue.includes('***');

  const isFieldDirty = (category: string, key: string, item: EditableConfigItem): boolean => {
    const draftValue = drafts[category]?.[key] as DraftValue;
    const sourceValue = item.value as DraftValue;

    if (isSecretMasked(item, draftValue)) {
      return false;
    }

    if (item.nullable && draftValue === '') {
      return sourceValue !== null;
    }

    return normalizeForCompare(draftValue) !== normalizeForCompare(sourceValue);
  };

  const getDirtyCount = (category: string): number => {
    const fields = editableConfig?.[category] || {};
    return Object.entries(fields).filter(([key, item]) => isFieldDirty(category, key, item)).length;
  };

  const totalDirtyCount = useMemo(
    () => categoryOrder.reduce((sum, category) => sum + getDirtyCount(category), 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [categoryOrder, drafts, editableConfig],
  );

  const totalEditableFields = useMemo(
    () =>
      categoryOrder.reduce((sum, category) => {
        const fields = editableConfig?.[category] || {};
        return sum + Object.keys(fields).length;
      }, 0),
    [categoryOrder, editableConfig],
  );

  const totalOverriddenCount = useMemo(
    () =>
      categoryOrder.reduce((sum, category) => {
        const fields = editableConfig?.[category] || {};
        return sum + Object.values(fields).filter((item) => item.is_overridden).length;
      }, 0),
    [categoryOrder, editableConfig],
  );

  const pageStyle = useMemo(
    () =>
      ({
        '--settings-card-bg': token.colorBgContainer,
        '--settings-card-soft': token.colorFillAlter,
        '--settings-border': token.colorBorderSecondary,
        '--settings-border-strong': token.colorBorder,
        '--settings-text': token.colorText,
        '--settings-text-secondary': token.colorTextSecondary,
        '--settings-primary': token.colorPrimary,
        '--settings-primary-soft': token.colorPrimaryBg,
        '--settings-shadow': token.boxShadowSecondary,
      }) as CSSProperties,
    [token],
  );

  useEffect(() => {
    if (totalDirtyCount === 0) {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [totalDirtyCount]);

  const handleSync = async () => {
    try {
      await runPipeline.mutateAsync({});
      message.success(t('settings.pipelineStarted'));
    } catch {
      message.error(t('settings.pipelineStartFailed'));
    }
  };

  const updateDraftValue = (category: string, key: string, value: DraftValue) => {
    setDrafts((prev) => ({
      ...prev,
      [category]: {
        ...(prev[category] || {}),
        [key]: value,
      },
    }));
  };

  const buildCategoryUpdates = (category: string): Record<string, DraftValue> => {
    const categoryDraft = drafts[category] || {};
    const categorySource = editableConfig?.[category] || {};
    const updates: Record<string, DraftValue> = {};

    Object.entries(categorySource).forEach(([key, item]) => {
      const draftValue = categoryDraft[key];
      const sourceValue = item.value as DraftValue;

      if (isSecretMasked(item, draftValue)) {
        return;
      }

      if (item.nullable && draftValue === '') {
        if (sourceValue !== null) {
          updates[key] = null;
        }
        return;
      }

      if (normalizeForCompare(draftValue) === normalizeForCompare(sourceValue)) {
        return;
      }

      updates[key] = draftValue;
    });

    return updates;
  };

  const handleSaveCategory = async (category: string) => {
    const updates = buildCategoryUpdates(category);
    if (Object.keys(updates).length === 0) {
      message.info(t('settings.noChangesToSave'));
      return;
    }

    try {
      const result = await updateConfig.mutateAsync({ category, updates });
      message.success(t('settings.saveSuccess', { count: result.updated.length }));
    } catch (error) {
      message.error((error as Error).message || t('settings.saveFailed'));
    }
  };

  const handleSaveAll = async () => {
    const dirtyCategories = categoryOrder.filter((category) => getDirtyCount(category) > 0);
    if (dirtyCategories.length === 0) {
      message.info(t('settings.noCategoryChanges'));
      return;
    }

    setIsSavingAll(true);
    try {
      let savedItems = 0;
      for (const category of dirtyCategories) {
        const updates = buildCategoryUpdates(category);
        if (Object.keys(updates).length === 0) {
          continue;
        }
        const result = await updateConfig.mutateAsync({ category, updates });
        savedItems += result.updated.length;
      }
      message.success(t('settings.saveAllSuccess', { count: savedItems }));
    } catch (error) {
      message.error((error as Error).message || t('settings.saveAllFailed'));
    } finally {
      setIsSavingAll(false);
    }
  };

  const handleResetCategory = async (category: string) => {
    try {
      const result = await resetCategory.mutateAsync(category);
      message.success(
        t('settings.revertSuccess', {
          category: getCategoryLabel(category),
          count: result.deleted,
        }),
      );
    } catch (error) {
      message.error((error as Error).message || t('settings.revertFailed'));
    }
  };

  const renderPipelineStatus = () => {
    if (statusLoading) {
      return <Spin size="small" />;
    }

    if (!pipelineStatus) {
      return <Text type="secondary">{t('common.unknown')}</Text>;
    }

    const statusConfig: Record<string, StatusMeta> = {
      idle: { icon: <ClockCircleOutlined />, color: 'default', text: t('settings.statusIdle') },
      running: { icon: <SyncOutlined spin />, color: 'processing', text: t('settings.statusRunning') },
      completed: {
        icon: <CheckCircleOutlined />,
        color: 'success',
        text: t('settings.statusCompleted'),
      },
      failed: { icon: <CloseCircleOutlined />, color: 'error', text: t('settings.statusFailed') },
    };

    const cfg = statusConfig[pipelineStatus.status] || statusConfig.idle;

    return (
      <Space>
        <Tag icon={cfg.icon} color={cfg.color}>
          {cfg.text}
        </Tag>
        {pipelineStatus.started_at && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {new Intl.DateTimeFormat(undefined, {
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            }).format(new Date(pipelineStatus.started_at))}
          </Text>
        )}
      </Space>
    );
  };

  const renderEditableField = (category: string, key: string, item: EditableConfigItem) => {
    const currentValue = drafts[category]?.[key];
    const fieldAriaLabel = `${category}.${key}`;
    const enumOptions = getEnumOptions(category, key, item);

    if (item.value_type === 'str' && enumOptions) {
      return (
        <Select
          aria-label={fieldAriaLabel}
          style={{ width: '100%' }}
          value={typeof currentValue === 'string' ? currentValue : undefined}
          options={enumOptions}
          allowClear={item.nullable}
          onChange={(value) => updateDraftValue(category, key, value ?? null)}
        />
      );
    }

    if (item.value_type === 'bool') {
      return (
        <Switch
          aria-label={fieldAriaLabel}
          checked={Boolean(currentValue)}
          onChange={(checked) => updateDraftValue(category, key, checked)}
        />
      );
    }

    if (item.value_type === 'int') {
      return (
        <InputNumber
          aria-label={fieldAriaLabel}
          style={{ width: '100%' }}
          value={typeof currentValue === 'number' ? currentValue : Number(currentValue ?? 0)}
          onChange={(value) => updateDraftValue(category, key, value ?? 0)}
          precision={0}
        />
      );
    }

    if (item.value_type === 'float') {
      return (
        <InputNumber
          aria-label={fieldAriaLabel}
          style={{ width: '100%' }}
          value={typeof currentValue === 'number' ? currentValue : Number(currentValue ?? 0)}
          onChange={(value) => updateDraftValue(category, key, value ?? 0)}
        />
      );
    }

    if (item.is_secret) {
      return (
        <Input.Password
          aria-label={fieldAriaLabel}
          name={fieldAriaLabel}
          autoComplete="off"
          value={typeof currentValue === 'string' ? currentValue : ''}
          onChange={(event) => updateDraftValue(category, key, event.target.value)}
          placeholder={t('settings.secretPlaceholder')}
          allowClear
        />
      );
    }

    return (
      <Input
        aria-label={fieldAriaLabel}
        name={fieldAriaLabel}
        autoComplete="off"
        value={currentValue === null ? '' : String(currentValue ?? '')}
        onChange={(event) => updateDraftValue(category, key, event.target.value)}
        allowClear={item.nullable}
      />
    );
  };

  const renderRuntimeConfig = () => {
    if (categoryOrder.length === 0) {
      return <Text type="secondary">{t('settings.noEditableConfig')}</Text>;
    }

    return (
      <Card className="settings-panel-card" bodyStyle={{ padding: 18 }}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert type="info" showIcon message={t('settings.configEditorTip')} />

          <Tabs
            type="card"
            className="settings-category-tabs"
            items={categoryOrder.map((category) => {
              const fields = editableConfig?.[category] || {};
              const searchKeyword = categorySearch[category] || '';
              const orderedEntries = getOrderedFieldEntries(category, fields);
              const filteredEntries = orderedEntries.filter(([key]) =>
                key.toLowerCase().includes(searchKeyword.toLowerCase()),
              );
              const dirtyCount = getDirtyCount(category);

              return {
                key: category,
                label: (
                  <Space size={8}>
                    <span>{getCategoryLabel(category)}</span>
                    {dirtyCount > 0 && <Badge count={dirtyCount} size="small" color="#faad14" />}
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <div className="settings-category-toolbar">
                      <Input
                        allowClear
                        aria-label={t('settings.searchCategoryAriaLabel', {
                          category: getCategoryLabel(category),
                        })}
                        name={`search-${category}`}
                        autoComplete="off"
                        style={{ width: 300, maxWidth: '100%' }}
                        placeholder={t('settings.searchPlaceholder')}
                        prefix={<SearchOutlined />}
                        value={searchKeyword}
                        onChange={(event) =>
                          setCategorySearch((prev) => ({
                            ...prev,
                            [category]: event.target.value,
                          }))
                        }
                      />

                      <Space wrap>
                        <Tag color={dirtyCount > 0 ? 'gold' : 'default'}>
                          {t('settings.changedCount', { count: dirtyCount })}
                        </Tag>
                        <Button
                          type="primary"
                          icon={<SaveOutlined />}
                          onClick={() => void handleSaveCategory(category)}
                          loading={updateConfig.isPending}
                          disabled={dirtyCount === 0 || isSavingAll}
                        >
                          {t('settings.saveCategory', { category: getCategoryLabel(category) })}
                        </Button>
                        <Button
                          danger
                          icon={<RollbackOutlined />}
                          onClick={() => void handleResetCategory(category)}
                          loading={resetCategory.isPending}
                          disabled={isSavingAll}
                        >
                          {t('settings.revertCategory', { category: getCategoryLabel(category) })}
                        </Button>
                      </Space>
                    </div>

                    {filteredEntries.length === 0 ? (
                      <Text type="secondary">{t('settings.noSearchResults')}</Text>
                    ) : (
                      <Space direction="vertical" size={10} style={{ width: '100%' }}>
                        {filteredEntries.map(([key, item]) => {
                          const dirty = isFieldDirty(category, key, item);
                          const fieldLabel = getFieldLabel(category, key);
                          const fieldDescription = getFieldDescription(category, key);
                          const impactTags = item.invalidate_tags.filter((tag) => tag !== 'settings');
                          const envVar = item.env_var || key.toUpperCase();
                          const showEnvVar = envVar !== key && envVar !== key.toUpperCase();
                          const showSettingsPath = item.settings_path !== key;

                          return (
                            <div
                              key={`${category}-${key}`}
                              className={`settings-field-card ${dirty ? 'is-dirty' : ''}`}
                            >
                              <div className="settings-field-row">
                                <div className="settings-field-key">
                                  <Text strong>{fieldLabel}</Text>
                                  {fieldDescription && (
                                    <div className="settings-field-description">
                                      <Text type="secondary">{fieldDescription}</Text>
                                    </div>
                                  )}
                                  <Space wrap size={6} className="settings-field-tech">
                                    <Text code>{key}</Text>
                                    {showEnvVar && <Text code>{envVar}</Text>}
                                    {showSettingsPath && <Text type="secondary">{item.settings_path}</Text>}
                                  </Space>
                                  <Space wrap size={6}>
                                    {item.is_overridden && (
                                      <Tag color="blue">{t('settings.tagOverridden')}</Tag>
                                    )}
                                    {item.is_secret && (
                                      <Tag color="orange">{t('settings.tagSecret')}</Tag>
                                    )}
                                    {dirty && <Tag color="gold">{t('settings.tagChanged')}</Tag>}
                                  </Space>
                                </div>

                                <div className="settings-field-input">
                                  {renderEditableField(category, key, item)}
                                </div>

                                <div className="settings-field-meta">
                                  <Space wrap size={6}>
                                    <Tag>{getValueTypeLabel(item.value_type)}</Tag>
                                    {item.constraints.map((constraint) => (
                                      <Tag key={`${category}-${key}-${constraint}`}>
                                        {getConstraintLabel(constraint)}
                                      </Tag>
                                    ))}
                                    {impactTags.map((tag) => (
                                      <Tag key={`${category}-${key}-${tag}`} color="processing">
                                        {getInvalidateTagLabel(tag)}
                                      </Tag>
                                    ))}
                                  </Space>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </Space>
                    )}
                  </Space>
                ),
              };
            })}
          />
        </Space>
      </Card>
    );
  };

  const renderSyncStatus = () => (
    <Card className="settings-panel-card" title={t('settings.schemaSync')}>
      <Space direction="vertical" style={{ width: '100%' }}>
        <div className="settings-sync-header">
          <div>
            <Text strong>{t('settings.pipelineStatus')}</Text>
            <div>{renderPipelineStatus()}</div>
          </div>
          <Button
            type="primary"
            icon={<SyncOutlined />}
            onClick={handleSync}
            loading={runPipeline.isPending || pipelineStatus?.status === 'running'}
            disabled={pipelineStatus?.status === 'running' || isSavingAll}
          >
            {t('settings.resync')}
          </Button>
        </div>

        {pipelineStatus?.stats && (
          <>
            <Divider style={{ margin: '12px 0' }} />
            <Descriptions column={3} size="small">
              <Descriptions.Item label={t('settings.statsDatabase')}>
                {pipelineStatus.stats.databases_processed}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.statsTables')}>
                {pipelineStatus.stats.tables_extracted}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.statsColumns')}>
                {pipelineStatus.stats.columns_extracted}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.statsForeignKeys')}>
                {pipelineStatus.stats.foreign_keys_extracted}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.statsNeo4jTables')}>
                {pipelineStatus.stats.neo4j_tables_written}
              </Descriptions.Item>
              <Descriptions.Item label={t('settings.statsMilvusTables')}>
                {pipelineStatus.stats.milvus_tables_written}
              </Descriptions.Item>
            </Descriptions>
          </>
        )}

        {pipelineStatus?.status === 'running' && (
          <Progress percent={50} status="active" showInfo={false} />
        )}
      </Space>
    </Card>
  );

  const renderOverview = () => (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Card className="settings-panel-card" title={t('settings.llmConfig')}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('settings.queryMode')}>
            <Tag color={config?.llm.query_mode === 'plan' ? 'blue' : 'green'}>
              {config?.llm.query_mode === 'plan'
                ? t('settings.queryModePlan')
                : t('settings.queryModeFast')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.provider')}>
            <Tag>{config?.llm.provider}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.model')}>{config?.llm.model}</Descriptions.Item>
          <Descriptions.Item label={t('settings.temperature')}>
            {config?.llm.temperature}
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.maxRetries')}>
            {config?.llm.max_sql_retries}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="settings-panel-card" title={t('settings.retrievalConfig')}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('settings.topK')}>{config?.retrieval.search_top_k}</Descriptions.Item>
          <Descriptions.Item label={t('settings.expandFk')}>
            <Tag color={config?.retrieval.expand_fk ? 'green' : 'default'}>
              {config?.retrieval.expand_fk ? t('common.on') : t('common.off')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.semanticFilter')}>
            <Tag color={config?.retrieval.semantic_filter_enabled ? 'green' : 'default'}>
              {config?.retrieval.semantic_filter_enabled ? t('common.on') : t('common.off')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.filterThreshold')}>
            {config?.retrieval.semantic_filter_threshold}
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.coreTables')} span={2}>
            {config?.retrieval.core_tables.map((tbl) => (
              <Tag key={tbl}>{tbl}</Tag>
            ))}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="settings-panel-card" title={t('settings.embeddingConfig')}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('settings.provider')}>
            {config?.embedding.provider}
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.model')}>
            {config?.embedding.model}
          </Descriptions.Item>
          <Descriptions.Item label={t('settings.dimension')}>
            {config?.embedding.dimension}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </Space>
  );

  if (configLoading || editableLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="settings-page" style={pageStyle}>
      <div className="settings-hero">
        <div className="settings-hero-top">
          <div>
            <Title level={4} style={{ marginBottom: 4 }}>
              {t('settings.title')}
            </Title>
            <Text type="secondary">{t('settings.pageSubtitle')}</Text>
          </div>
          <Space wrap>
            {totalDirtyCount > 0 && (
              <Tag color="gold">{t('settings.unsavedChanges', { count: totalDirtyCount })}</Tag>
            )}
            <Button
              icon={<SyncOutlined />}
              onClick={handleSync}
              loading={runPipeline.isPending || pipelineStatus?.status === 'running'}
              disabled={pipelineStatus?.status === 'running' || isSavingAll}
            >
              {t('settings.resync')}
            </Button>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={() => void handleSaveAll()}
              loading={isSavingAll}
              disabled={totalDirtyCount === 0 || updateConfig.isPending || resetCategory.isPending}
            >
              {t('settings.saveAll')}
            </Button>
          </Space>
        </div>

        <div className="settings-hero-status">{renderPipelineStatus()}</div>

        <div className="settings-hero-stats">
          <div className="settings-stat-box">
            <div className="settings-stat-value">{categoryOrder.length}</div>
            <div className="settings-stat-label">{t('settings.statsEditableCategories')}</div>
          </div>
          <div className="settings-stat-box">
            <div className="settings-stat-value">{totalEditableFields}</div>
            <div className="settings-stat-label">{t('settings.statsEditableFields')}</div>
          </div>
          <div className="settings-stat-box">
            <div className="settings-stat-value">{totalOverriddenCount}</div>
            <div className="settings-stat-label">{t('settings.statsOverridden')}</div>
          </div>
        </div>
      </div>

      <Tabs
        className="settings-main-tabs"
        items={[
          {
            key: 'runtime',
            label: (
              <Space size={8}>
                <span>{t('settings.tabs.runtime')}</span>
                {totalDirtyCount > 0 && <Badge count={totalDirtyCount} size="small" color="#faad14" />}
              </Space>
            ),
            children: renderRuntimeConfig(),
          },
          {
            key: 'sync',
            label: t('settings.tabs.sync'),
            children: renderSyncStatus(),
          },
          {
            key: 'overview',
            label: t('settings.tabs.overview'),
            children: renderOverview(),
          },
        ]}
      />
    </div>
  );
}
