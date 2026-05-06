import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Form, Input, Button, message, Tabs } from 'antd'
import { UserOutlined, LockOutlined, IdcardOutlined, BookOutlined } from '@ant-design/icons'
import { login, register } from '../services/api'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('login')
  const [authError, setAuthError] = useState('')
  const navigate = useNavigate()

  const getAuthErrorMessage = (err, fallback) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail
    if (status === 401) return detail || '用户名或密码错误，请检查后重试'
    if (status === 403) return detail || '当前账号没有权限'
    if (status >= 500) return '服务器内部错误，请查看后端日志'
    if (err.code === 'ERR_NETWORK') return '无法连接后端服务，请确认后端已启动且前端 API 地址正确'
    return detail || err.message || fallback
  }

  const handleLogin = async (values) => {
    setLoading(true)
    setAuthError('')
    try {
      const res = await login(values)
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('user', JSON.stringify(res.data.user))
      message.success('登录成功')
      navigate('/')
    } catch (err) {
      const errorText = getAuthErrorMessage(err, '登录失败')
      setAuthError(errorText)
      message.error(errorText)
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (values) => {
    setLoading(true)
    setAuthError('')
    try {
      await register(values)
      message.success('注册成功，请登录')
      setActiveTab('login')
    } catch (err) {
      const errorText = getAuthErrorMessage(err, '注册失败')
      setAuthError(errorText)
      message.error(errorText)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="login-brand-icon"><BookOutlined /></div>
          <h1>类案检索系统</h1>
          <p>基于 AI 的智能法律类案检索与分析平台</p>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={(key) => { setActiveTab(key); setAuthError('') }}
          centered
          items={[
            {
              key: 'login',
              label: '登录',
              children: (
                <Form onFinish={handleLogin} size="large" autoComplete="off">
                  {authError && (
                    <Alert
                      type="error"
                      showIcon
                      message={authError}
                      style={{ marginBottom: 16 }}
                    />
                  )}
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input prefix={<UserOutlined style={{ color: '#bbb' }} />} placeholder="用户名" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                    <Input.Password prefix={<LockOutlined style={{ color: '#bbb' }} />} placeholder="密码" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" block loading={loading} className="login-submit-btn">
                      登 录
                    </Button>
                  </Form.Item>
                  <div style={{ textAlign: 'center', color: '#bbb', fontSize: 12 }}>
                    演示账号: admin / admin123 或 demo / demo123
                  </div>
                </Form>
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: (
                <Form onFinish={handleRegister} size="large" autoComplete="off">
                  {authError && (
                    <Alert
                      type="error"
                      showIcon
                      message={authError}
                      style={{ marginBottom: 16 }}
                    />
                  )}
                  <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                    <Input prefix={<UserOutlined style={{ color: '#bbb' }} />} placeholder="用户名" />
                  </Form.Item>
                  <Form.Item name="full_name">
                    <Input prefix={<IdcardOutlined style={{ color: '#bbb' }} />} placeholder="姓名（选填）" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                    <Input.Password prefix={<LockOutlined style={{ color: '#bbb' }} />} placeholder="密码" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" block loading={loading} className="login-submit-btn">
                      注 册
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </div>
    </div>
  )
}
