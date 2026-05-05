import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Input, Modal, Descriptions, Collapse, Typography, Table, Tag, Dropdown, message } from 'antd'
import {
  SendOutlined, BookOutlined, LogoutOutlined, UserOutlined,
  SettingOutlined, FileTextOutlined, BankOutlined, CalendarOutlined,
} from '@ant-design/icons'
import { searchSimilar, generateReport } from '../services/api'

const { TextArea } = Input
const { Paragraph } = Typography

export default function ChatPage() {
  const navigate = useNavigate()
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const [conversation, setConversation] = useState([])
  const [detailModal, setDetailModal] = useState(null)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)
  const user = JSON.parse(localStorage.getItem('user') || '{}')

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation, loading])

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    message.success('已退出登录')
    navigate('/login')
  }

  const isAdmin = user.role === 'admin' || user.username === 'admin'

  const userMenuItems = [
    { key: 'user', label: user.full_name || user.username, disabled: true },
    ...(isAdmin ? [{ key: 'admin', label: '案例库管理', icon: <SettingOutlined />, onClick: () => navigate('/admin/cases') }] : []),
    { type: 'divider' },
    { key: 'logout', label: '退出登录', icon: <LogoutOutlined />, onClick: handleLogout },
  ]

  const handleSubmit = async () => {
    const text = inputValue.trim()
    if (!text || loading) return

    setInputValue('')
    const userMsg = { type: 'user', text }
    setConversation(prev => [...prev, userMsg])
    setLoading(true)

    try {
      const res = await searchSimilar({
        case_name: text.slice(0, 50),
        case_description: text,
        top_k: 5,
      })

      const systemMsg = {
        type: 'system',
        results: res.data,
        query: text,
      }
      setConversation(prev => [...prev, systemMsg])
    } catch (err) {
      const errMsg = {
        type: 'system',
        error: err.response?.data?.detail || err.message || '检索失败，请重试',
      }
      setConversation(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }

  const handleGenerateReport = async (msgIndex) => {
    const msg = conversation[msgIndex]
    if (!msg?.results?.similar_cases?.length) return

    setReportLoading(true)
    try {
      const res = await generateReport({
        case_name: msg.query.slice(0, 50),
        case_description: msg.query,
        similar_case_ids: msg.results.similar_cases.map(sc => sc.case.id),
      })

      setConversation(prev => {
        const updated = [...prev]
        updated[msgIndex] = { ...updated[msgIndex], report: res.data }
        return updated
      })
      message.success('报告生成完成')
    } catch (err) {
      message.error('报告生成失败')
    } finally {
      setReportLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const getScoreClass = (score) => {
    if (score >= 80) return 'score-high'
    if (score >= 60) return 'score-medium'
    if (score >= 40) return 'score-low'
    return 'score-very-low'
  }

  const getScoreLabel = (score) => {
    const pct = Math.round(score)
    if (score >= 80) return `${pct}% 高度相似`
    if (score >= 60) return `${pct}% 较为相似`
    if (score >= 40) return `${pct}% 部分相似`
    return `${pct}%`
  }

  const getCaseText = (caseItem, field) => {
    if (!caseItem) return '暂无'
    const displayField = `${field}_display`
    return caseItem[field] || caseItem[displayField] || '暂无'
  }

  const hints = [
    '张某与李某因房屋买卖合同产生纠纷，张某已支付定金但李某拒绝过户...',
    '某公司员工在工作期间受伤，公司未缴纳工伤保险，员工要求赔偿...',
    '王某驾驶机动车与骑电动车的赵某发生碰撞，双方对事故责任有争议...',
  ]

  const hasConversation = conversation.length > 0

  return (
    <div className="chat-app">
      {/* Top bar */}
      <div className="chat-topbar">
        <div className="chat-topbar-brand">
          <div className="brand-icon"><BookOutlined /></div>
          <span>类案检索</span>
        </div>
        <div className="chat-topbar-actions">
          {hasConversation && (
            <button
              className="send-btn"
              style={{ background: 'transparent', color: '#999', width: 'auto', padding: '4px 12px', fontSize: 13 }}
              onClick={() => setConversation([])}
            >
              新对话
            </button>
          )}
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <div style={{
              width: 32, height: 32, borderRadius: 8, background: '#f0f0f0',
              display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer',
            }}>
              <UserOutlined style={{ color: '#666', fontSize: 14 }} />
            </div>
          </Dropdown>
        </div>
      </div>

      {/* Main */}
      <div className="chat-main">
        {!hasConversation ? (
          /* Welcome screen */
          <div className="chat-welcome">
            <div className="welcome-icon"><BookOutlined /></div>
            <div className="welcome-title">智能类案检索</div>
            <div className="welcome-subtitle">描述您的案件情况，AI 将为您检索相似案例</div>
            <div className="welcome-hints">
              {hints.map((hint, i) => (
                <div
                  key={i}
                  className="hint-card"
                  onClick={() => { setInputValue(hint); textareaRef.current?.focus() }}
                >
                  {hint}
                </div>
              ))}
            </div>
          </div>
        ) : (
          /* Conversation */
          <div className="chat-results">
            {conversation.map((msg, idx) => {
              if (msg.type === 'user') {
                return (
                  <div key={idx} className="msg-user animate-in">
                    <div className="msg-user-bubble">
                      <div className="msg-user-label">案情描述</div>
                      {msg.text}
                    </div>
                  </div>
                )
              }

              if (msg.error) {
                return (
                  <div key={idx} className="msg-system animate-in">
                    <div className="msg-system-header">
                      <div className="msg-system-avatar"><BookOutlined /></div>
                      <div className="msg-system-name">类案检索</div>
                    </div>
                    <div className="result-summary-text" style={{ color: '#dc2626' }}>
                      {msg.error}
                    </div>
                  </div>
                )
              }

              const cases = msg.results?.similar_cases || []
              const filters = msg.results?.extracted_filters
              return (
                <div key={idx} className="msg-system animate-in">
                  <div className="msg-system-header">
                    <div className="msg-system-avatar"><BookOutlined /></div>
                    <div className="msg-system-name">类案检索</div>
                  </div>

                  {cases.length === 0 ? (
                    <div className="result-summary-text">
                      未检索到相似案例，请尝试更详细地描述案件情况。
                    </div>
                  ) : (
                    <>
                      <div className="result-summary-text">
                        共检索到 <strong>{msg.results.total_found}</strong> 个相似案例，以下是匹配度最高的结果：
                      </div>

                      {filters && (filters.case_type || filters.time_range_start || filters.time_range_end || filters.cause_keywords?.length > 0) && (
                        <div style={{ marginBottom: 12 }}>
                          <span style={{ color: '#999', fontSize: 13, marginRight: 8 }}>已识别筛选条件</span>
                          {filters.case_type && <Tag color="blue">{filters.case_type}</Tag>}
                          {(filters.time_range_start || filters.time_range_end) && (
                            <Tag color="purple">
                              {filters.time_range_start || '不限'} 至 {filters.time_range_end || '不限'}
                            </Tag>
                          )}
                          {filters.cause_keywords?.map((keyword) => (
                            <Tag key={keyword}>{keyword}</Tag>
                          ))}
                        </div>
                      )}

                      <div className="result-cards-list">
                        {cases.map((item, i) => (
                          <div
                            key={item.case.id}
                            className="result-case-card"
                            onClick={() => setDetailModal(item.case)}
                          >
                            <div className="result-case-header">
                              <div className="result-case-title">
                                <span style={{ color: '#bbb', marginRight: 8, fontWeight: 400, fontSize: 13 }}>
                                  {i + 1}.
                                </span>
                                {item.case.case_name}
                              </div>
                              <div className={`result-case-score ${getScoreClass(item.similarity_score)}`}>
                                {getScoreLabel(item.similarity_score)}
                              </div>
                            </div>
                            <div className="result-case-meta">
                              {item.case.case_number && (
                                <span><FileTextOutlined /> {item.case.case_number}</span>
                              )}
                              {item.case.court && (
                                <span><BankOutlined /> {item.case.court}</span>
                              )}
                              {item.case.judge_date && (
                                <span><CalendarOutlined /> {item.case.judge_date}</span>
                              )}
                              {item.case.cause_of_action && (
                                <span style={{ color: '#d97706' }}>{item.case.cause_of_action}</span>
                              )}
                            </div>
                            {(item.case.case_summary || item.case.case_summary_display) && (
                              <div className="result-case-summary">
                                {item.case.case_summary || item.case.case_summary_display}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Generate report button */}
                      {!msg.report && (
                        <div className="gen-report-btn">
                          <button
                            className="send-btn"
                            style={{
                              width: 'auto',
                              padding: '8px 20px',
                              fontSize: 13,
                              borderRadius: 10,
                              gap: 6,
                              display: 'inline-flex',
                              alignItems: 'center',
                            }}
                            disabled={reportLoading}
                            onClick={(e) => { e.stopPropagation(); handleGenerateReport(idx) }}
                          >
                            <FileTextOutlined />
                            {reportLoading ? '生成中...' : '生成对比报告'}
                          </button>
                        </div>
                      )}

                      {/* Report */}
                      {msg.report && (
                        <div className="report-container animate-in">
                          <div className="report-card">
                            <div className="report-card-header">
                              <FileTextOutlined /> {msg.report.title}
                            </div>
                            <div className="report-card-body">
                              <div className="report-section">
                                <div className="report-section-title">摘要</div>
                                <p>{msg.report.summary}</p>
                              </div>

                              {msg.report.comparisons?.length > 0 && (
                                <div className="report-section">
                                  <div className="report-section-title">对比分析</div>
                                  <Table
                                    dataSource={msg.report.comparisons}
                                    columns={[
                                      { title: '维度', dataIndex: 'aspect', width: 80, render: (t) => <Tag>{t}</Tag> },
                                      { title: '用户案情', dataIndex: 'user_case', width: '28%' },
                                      { title: '类案内容', dataIndex: 'similar_case', width: '28%' },
                                      { title: '分析', dataIndex: 'analysis' },
                                    ]}
                                    pagination={false}
                                    size="small"
                                    bordered
                                    rowKey={(_, i) => i}
                                    scroll={{ x: 600 }}
                                  />
                                </div>
                              )}

                              {msg.report.legal_references?.length > 0 && (
                                <div className="report-section">
                                  <div className="report-section-title">相关法律条文</div>
                                  <div>
                                    {msg.report.legal_references.map((ref, ri) => (
                                      <span key={ri} className="report-legal-tag">{ref}</span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {msg.report.conclusion && (
                                <div className="report-section">
                                  <div className="report-section-title">综合结论与建议</div>
                                  <div className="report-conclusion">{msg.report.conclusion}</div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )
            })}

            {loading && (
              <div className="msg-system animate-in">
                <div className="msg-system-header">
                  <div className="msg-system-avatar"><BookOutlined /></div>
                  <div className="msg-system-name">类案检索</div>
                </div>
                <div className="loading-indicator">
                  <div className="loading-dots">
                    <span></span><span></span><span></span>
                  </div>
                  正在检索相似案例...
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}

        {/* Input area */}
        <div className="chat-input-area">
          <div className="chat-input-wrapper">
            <TextArea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="描述案件情况，如当事人、事实经过、争议焦点..."
              autoSize={{ minRows: 1, maxRows: 6 }}
              variant="borderless"
            />
            <div className="chat-input-toolbar">
              <div className="chat-input-toolbar-left">
                <span className="input-hint-text">Enter 发送 / Shift+Enter 换行</span>
              </div>
              <button
                className="send-btn"
                disabled={!inputValue.trim() || loading}
                onClick={handleSubmit}
              >
                <SendOutlined style={{ fontSize: 15 }} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Case detail modal */}
      <Modal
        title={detailModal?.case_name}
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={null}
        width={680}
        styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
      >
        {detailModal && (
          <div>
            <Descriptions
              bordered
              column={2}
              size="small"
              className="case-detail-meta"
              items={[
                { label: '案号', children: detailModal.case_number || '-' },
                { label: '案由', children: detailModal.cause_of_action || '-' },
                { label: '审理法院', children: detailModal.court || '-' },
                { label: '裁判日期', children: detailModal.judge_date || '-' },
                { label: '原告', children: detailModal.plaintiff || '-' },
                { label: '被告', children: detailModal.defendant || '-' },
              ]}
            />
            <Collapse
              defaultActiveKey={['1', '2', '3']}
              ghost
              items={[
                { key: '1', label: '基本案情', children: <Paragraph style={{ lineHeight: 2 }}>{getCaseText(detailModal, 'case_summary')}</Paragraph> },
                { key: '2', label: '争议焦点', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.dispute_focus || '暂无'}</Paragraph> },
                { key: '3', label: '裁判结果', children: <Paragraph style={{ lineHeight: 2 }}>{getCaseText(detailModal, 'judgment_result')}</Paragraph> },
                { key: '4', label: '裁判理由', children: <Paragraph style={{ lineHeight: 2 }}>{getCaseText(detailModal, 'judgment_reason')}</Paragraph> },
                { key: '5', label: '裁判要点', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.judgment_points || '暂无'}</Paragraph> },
                { key: '6', label: '相关法条', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.related_laws || '暂无'}</Paragraph> },
                { key: '7', label: '裁判文书摘录', children: <Paragraph style={{ lineHeight: 2 }}>{detailModal.full_text_preview || '暂无'}</Paragraph> },
              ]}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
