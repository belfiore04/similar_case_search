import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Space, Input, Select, Modal, Form,
  message, Popconfirm, Tag, Descriptions, Collapse, Typography,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined,
  ArrowLeftOutlined, BookOutlined,
} from '@ant-design/icons'
import { getCases, getCaseCount, createCase, updateCase, deleteCase } from '../services/api'

const { TextArea } = Input
const { Paragraph } = Typography

export default function AdminCasesPage() {
  const navigate = useNavigate()
  const [cases, setCases] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [caseType, setCaseType] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editingCase, setEditingCase] = useState(null)
  const [detailModal, setDetailModal] = useState(null)
  const [form] = Form.useForm()

  const fetchCases = async () => {
    setLoading(true)
    try {
      const params = { page, size: 15 }
      if (keyword) params.keyword = keyword
      if (caseType) params.case_type = caseType
      const [casesRes, countRes] = await Promise.all([getCases(params), getCaseCount()])
      setCases(casesRes.data)
      setTotal(countRes.data.total)
    } catch {
      message.error('加载案例失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchCases() }, [page, keyword, caseType])

  const handleSave = async (values) => {
    try {
      if (editingCase) {
        await updateCase(editingCase.id, values)
        message.success('更新成功')
      } else {
        await createCase(values)
        message.success('创建成功')
      }
      setModalOpen(false)
      setEditingCase(null)
      form.resetFields()
      fetchCases()
    } catch (err) {
      message.error('操作失败：' + (err.response?.data?.detail || err.message))
    }
  }

  const handleDelete = async (id) => {
    try {
      await deleteCase(id)
      message.success('删除成功')
      fetchCases()
    } catch {
      message.error('删除失败')
    }
  }

  const openEdit = (record) => {
    setEditingCase(record)
    form.setFieldsValue(record)
    setModalOpen(true)
  }

  const openCreate = () => {
    setEditingCase(null)
    form.resetFields()
    setModalOpen(true)
  }

  const columns = [
    {
      title: '案件名称', dataIndex: 'case_name', key: 'case_name', width: 250,
      ellipsis: true,
      render: (text, record) => <a onClick={() => setDetailModal(record)}>{text}</a>,
    },
    { title: '案号', dataIndex: 'case_number', key: 'case_number', width: 180, ellipsis: true },
    {
      title: '类型', dataIndex: 'case_type', key: 'case_type', width: 80,
      render: (t) => t ? <Tag>{t}</Tag> : '-',
    },
    { title: '案由', dataIndex: 'cause_of_action', key: 'cause_of_action', width: 130, ellipsis: true },
    { title: '审理法院', dataIndex: 'court', key: 'court', width: 160, ellipsis: true },
    { title: '裁判日期', dataIndex: 'judge_date', key: 'judge_date', width: 110 },
    {
      title: '操作', key: 'action', width: 140, fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailModal(record)} />
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm title="确认删除此案例？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="admin-page">
      <div className="admin-topbar">
        <div className="admin-topbar-title">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/')}
            style={{ marginRight: 4 }}
          />
          <BookOutlined /> 案例库管理
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新增案例
        </Button>
      </div>

      <div className="admin-content">
        <Card style={{ borderRadius: 12, border: '1px solid #f0f0f0' }}>
          <Space style={{ marginBottom: 16 }} wrap>
            <Input.Search
              placeholder="搜索案件名称/关键词"
              allowClear
              onSearch={setKeyword}
              style={{ width: 280 }}
            />
            <Select
              placeholder="案件类型"
              allowClear
              onChange={setCaseType}
              style={{ width: 120 }}
              options={[
                { value: '民事', label: '民事' },
                { value: '刑事', label: '刑事' },
                { value: '行政', label: '行政' },
              ]}
            />
            <span style={{ color: '#999', fontSize: 13 }}>共 {total} 条</span>
          </Space>

          <Table
            dataSource={cases}
            columns={columns}
            rowKey="id"
            loading={loading}
            scroll={{ x: 1000 }}
            pagination={{
              current: page,
              total,
              pageSize: 15,
              onChange: setPage,
              showTotal: (t) => `共 ${t} 条`,
            }}
          />
        </Card>
      </div>

      {/* Create/Edit modal */}
      <Modal
        title={editingCase ? '编辑案例' : '新增案例'}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditingCase(null); form.resetFields() }}
        onOk={() => form.submit()}
        width={720}
        okText="保存"
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="case_name" label="案件名称" rules={[{ required: true }]}>
            <Input placeholder="原告 + 被告 + 案由" />
          </Form.Item>
          <Space size="large" wrap style={{ width: '100%' }}>
            <Form.Item name="case_number" label="案号"><Input placeholder="（2024）京0105民初12345号" style={{ width: 240 }} /></Form.Item>
            <Form.Item name="case_type" label="案件类型">
              <Select style={{ width: 120 }} options={[
                { value: '民事', label: '民事' },
                { value: '刑事', label: '刑事' },
                { value: '行政', label: '行政' },
              ]} />
            </Form.Item>
            <Form.Item name="cause_of_action" label="案由"><Input style={{ width: 200 }} /></Form.Item>
          </Space>
          <Space size="large" wrap style={{ width: '100%' }}>
            <Form.Item name="court" label="审理法院"><Input style={{ width: 240 }} /></Form.Item>
            <Form.Item name="judge_date" label="裁判日期"><Input placeholder="2024-01-01" style={{ width: 160 }} /></Form.Item>
            <Form.Item name="plaintiff" label="原告"><Input style={{ width: 160 }} /></Form.Item>
            <Form.Item name="defendant" label="被告"><Input style={{ width: 160 }} /></Form.Item>
          </Space>
          <Form.Item name="case_summary" label="基本案情"><TextArea rows={4} /></Form.Item>
          <Form.Item name="dispute_focus" label="争议焦点"><TextArea rows={2} /></Form.Item>
          <Form.Item name="judgment_result" label="裁判结果"><TextArea rows={2} /></Form.Item>
          <Form.Item name="judgment_reason" label="裁判理由"><TextArea rows={3} /></Form.Item>
          <Form.Item name="judgment_points" label="裁判要点"><TextArea rows={2} /></Form.Item>
          <Form.Item name="related_laws" label="相关法条"><TextArea rows={2} /></Form.Item>
          <Form.Item name="keywords" label="关键词"><Input placeholder="用逗号分隔，如：合同,违约,赔偿" /></Form.Item>
        </Form>
      </Modal>

      {/* Detail modal */}
      <Modal
        title={detailModal?.case_name}
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={null}
        width={680}
      >
        {detailModal && (
          <div>
            <Descriptions bordered column={2} size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="案号">{detailModal.case_number || '-'}</Descriptions.Item>
              <Descriptions.Item label="案由">{detailModal.cause_of_action || '-'}</Descriptions.Item>
              <Descriptions.Item label="审理法院">{detailModal.court || '-'}</Descriptions.Item>
              <Descriptions.Item label="裁判日期">{detailModal.judge_date || '-'}</Descriptions.Item>
              <Descriptions.Item label="原告">{detailModal.plaintiff || '-'}</Descriptions.Item>
              <Descriptions.Item label="被告">{detailModal.defendant || '-'}</Descriptions.Item>
            </Descriptions>
            <Collapse
              defaultActiveKey={['1']}
              ghost
              items={[
                { key: '1', label: '基本案情', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.case_summary || '暂无'}</Paragraph> },
                { key: '2', label: '争议焦点', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.dispute_focus || '暂无'}</Paragraph> },
                { key: '3', label: '裁判结果', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.judgment_result || '暂无'}</Paragraph> },
                { key: '4', label: '裁判理由', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.judgment_reason || '暂无'}</Paragraph> },
                { key: '5', label: '裁判要点', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.judgment_points || '暂无'}</Paragraph> },
                { key: '6', label: '相关法条', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.related_laws || '暂无'}</Paragraph> },
              ]}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
