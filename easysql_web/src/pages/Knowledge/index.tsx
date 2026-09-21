import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, App, Breadcrumb, Button, Card, Drawer, Empty, Input, Popconfirm,
  Select, Space, Spin, Table, Tag, Typography, Upload,
} from 'antd';
import type { UploadFile } from 'antd';
import { BookOutlined, DeleteOutlined, FolderOpenOutlined, InboxOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { knowledgeApi } from '@/api/knowledge';
import type { WikiPage, WikiPageCard } from '@/api/knowledge';
import { useDatabases } from '@/hooks/useConfig';

const kindNames: Record<string, string> = {
  term: '术语', metric: '指标口径', schema: '表与字段', join_rule: '关联规则',
  sql_example: 'SQL 示例', rule: '业务规则',
};

export default function KnowledgePage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const databases = useDatabases();
  const [selected, setSelected] = useState<string[]>([]);
  const names = selected.length ? selected : (databases.data?.databases ?? []).map((db) => db.name);
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [domain, setDomain] = useState('');
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState<WikiPage | null>(null);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [uploadResult, setUploadResult] = useState('');

  const documents = useQuery({ queryKey: ['knowledge', 'documents'], queryFn: knowledgeApi.documents });
  const outline = useQuery({
    queryKey: ['knowledge', 'outline', names, domain],
    queryFn: () => knowledgeApi.outline(names, domain), enabled: names.length > 0,
  });
  const pages = useQuery({
    queryKey: ['knowledge', 'pages', names, domain, offset],
    queryFn: () => knowledgeApi.pages(names, domain, offset), enabled: names.length > 0 && !search,
  });
  const results = useQuery({
    queryKey: ['knowledge', 'search', names, search],
    queryFn: () => knowledgeApi.search(search, names), enabled: names.length > 0 && !!search,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['knowledge'] });
  const upload = useMutation({
    mutationFn: async () => {
      const completed = [];
      for (const file of files) {
        const origin = file.originFileObj;
        if (!origin) continue;
        const result = await knowledgeApi.upload(origin, names);
        completed.push(`${file.name}：${result.unchanged ? '内容未变' : `已发布 v${result.revision}，${result.page_count ?? 0} 个页面`}${result.index_status === 'pending' ? '（索引待重试）' : ''}`);
      }
      return completed;
    },
    onSuccess: (completed) => {
      setUploadResult(completed.join('\n'));
      setFiles([]);
      refresh();
    },
    onError: (error) => { message.error(error.message); refresh(); },
  });
  const remove = useMutation({
    mutationFn: knowledgeApi.remove, onSuccess: refresh, onError: (error) => message.error(error.message),
  });
  const reindex = useMutation({
    mutationFn: knowledgeApi.reindex, onSuccess: refresh, onError: (error) => message.error(error.message),
  });

  async function readPage(card: WikiPageCard, nextOffset = 0) {
    setDrawerOpen(true);
    setReading(true);
    setReadError(null);
    if (nextOffset === 0) setPage(null);
    try {
      const loaded = await knowledgeApi.read(card.id, names, nextOffset);
      setPage((previous) => nextOffset && previous?.id === card.id
        ? { ...loaded, body_md: previous.body_md + loaded.body_md }
        : loaded);
    } catch (error) {
      setReadError(error instanceof Error ? error.message : '读取失败');
    } finally {
      setReading(false);
    }
  }

  const visiblePages = search ? results.data?.pages : pages.data?.pages;
  const error = documents.error || outline.error || pages.error || results.error;
  function openDomain(value: string) { setDomain(value); setOffset(0); setSearch(''); }

  return (
    <div style={{ padding: 28, maxWidth: 1300, margin: '0 auto', width: '100%', overflowY: 'auto' }}>
      <Typography.Title level={2}><BookOutlined /> 知识库</Typography.Title>
      <Typography.Paragraph type="secondary">
        上传 Markdown，自动整理成分层 Wiki。新增文档补充知识，同名文档更新已有版本；Agent 按需阅读目录、摘要与正文。
      </Typography.Paragraph>
      {error && <Alert type="error" showIcon title={error.message} style={{ marginBottom: 16 }} />}
      <Card title="上传与增量整理" style={{ marginBottom: 24 }}>
        <Space orientation="vertical" style={{ width: '100%' }} size="middle">
          <Select mode="multiple" aria-label="适用数据库" placeholder="选择适用数据库" value={names}
            options={(databases.data?.databases ?? []).map((db) => ({ value: db.name, label: db.name }))}
            onChange={(value) => { setSelected(value); setPage(null); setDrawerOpen(false); }} style={{ width: '100%' }} />
          <Upload.Dragger accept=".md,.markdown" multiple beforeUpload={() => false}
            fileList={files} onChange={({ fileList }) => setFiles(fileList)} disabled={upload.isPending}>
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p>拖入 Markdown，或点击选择文件</p>
            <p style={{ color: '#777' }}>UTF-8，每个文件最多 512 KiB。同名文件沿用同一文档来源。</p>
          </Upload.Dragger>
          <Button type="primary" loading={upload.isPending} disabled={!files.length || !names.length}
            onClick={() => upload.mutate()}>整理并更新知识库</Button>
          {upload.isPending && <Alert type="info" title="正在整理文档并核对原文依据，已发布的知识仍可查询。" />}
          {uploadResult && <Alert type="success" title={<span style={{ whiteSpace: 'pre-line' }}>{uploadResult}</span>} />}
        </Space>
      </Card>

      <Card title="文档来源" style={{ marginBottom: 24 }} extra={<Button icon={<ReloadOutlined />} onClick={() => refresh()}>刷新</Button>}>
        <Table rowKey="id" size="small" loading={documents.isLoading} dataSource={documents.data?.documents ?? []}
          pagination={{ pageSize: 5 }} columns={[
            { title: '文档', dataIndex: 'source_key' },
            { title: '版本', dataIndex: 'revision', render: (value) => `v${value}` },
            { title: '适用数据库', dataIndex: 'db_names', render: (value: string[]) => value.join('、') },
            { title: '索引', dataIndex: 'index_status', render: (value) => <Tag color={value === 'ready' ? 'green' : 'orange'}>{value === 'ready' ? '已同步' : '待同步'}</Tag> },
            { title: '操作', render: (_, doc) => <Space>
              {doc.index_status !== 'ready' && <Button size="small" loading={reindex.isPending} onClick={() => reindex.mutate(doc.id)}>重试索引</Button>}
              <Popconfirm title="删除此文档贡献的全部知识？其他文档不受影响。" onConfirm={() => remove.mutate(doc.id)}>
                <Button size="small" danger icon={<DeleteOutlined />} aria-label={`删除 ${doc.source_key}`} />
              </Popconfirm>
            </Space> },
          ]} />
      </Card>

      <Card title="Wiki" extra={<Input.Search allowClear placeholder="搜索业务术语、指标或表名" onSearch={(value) => setSearch(value)} style={{ width: 300 }} />}>
        <Breadcrumb style={{ marginBottom: 16 }} items={[
          { title: <Button type="link" onClick={() => openDomain('')}>全部领域</Button> },
          ...domain.split('/').filter(Boolean).map((part, index, parts) => ({
            title: <Button type="link" onClick={() => openDomain(parts.slice(0, index + 1).join('/'))}>{part}</Button>,
          })),
        ]} />
        {!search && <Space wrap style={{ marginBottom: 20 }}>
          {(outline.data?.children ?? []).map((child) => <Button key={child.domain} icon={<FolderOpenOutlined />}
            onClick={() => openDomain(child.domain)}>{child.domain.split('/').at(-1)} · {child.page_count}</Button>)}
        </Space>}
        {(pages.isLoading || results.isFetching) && <Spin />}
        {!visiblePages?.length && !pages.isLoading && <Empty description="暂无页面，上传业务说明或数据字典开始建立知识库" />}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 16 }}>
          {(visiblePages ?? []).map((card) => <Card key={card.id} size="small" hoverable onClick={() => readPage(card)}>
            <Tag>{kindNames[card.kind] ?? card.kind}</Tag>
            <Typography.Title level={5}>{card.title}</Typography.Title>
            <Typography.Paragraph>{card.summary}</Typography.Paragraph>
            <Typography.Text type="secondary">{card.domain} · {card.source_key} v{card.revision}</Typography.Text>
          </Card>)}
        </div>
        {!search && <Space style={{ marginTop: 18 }}>
          <Button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</Button>
          <Button disabled={pages.data?.next_offset == null} onClick={() => setOffset(pages.data?.next_offset ?? 0)}>下一页</Button>
        </Space>}
      </Card>

      <Drawer title={page?.title ?? '读取知识'} open={drawerOpen} onClose={() => setDrawerOpen(false)} size="large">
        {reading && <Spin />}
        {readError && <Alert type="error" title={readError} />}
        {page && <>
          <Typography.Paragraph type="secondary">{page.domain} · 来源：{page.source_key} v{page.revision} 第 {page.source_line} 行</Typography.Paragraph>
          <div style={{ overflowWrap: 'anywhere', overflowX: 'auto' }}><ReactMarkdown remarkPlugins={[remarkGfm]}>{page.body_md}</ReactMarkdown></div>
          {page.next_offset != null && <Button loading={reading} onClick={() => readPage(page, page.next_offset ?? 0)}>继续阅读</Button>}
          <Typography.Title level={5}>原文依据</Typography.Title>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{page.source_quote}</Typography.Paragraph>
          {page.table_ids.map((table) => <Tag key={table}>{table}</Tag>)}
        </>}
      </Drawer>
    </div>
  );
}
