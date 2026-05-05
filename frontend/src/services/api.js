import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api',
  timeout: 30000,
});

// 请求拦截：自动携带token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截：处理401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// Auth
export const login = (data) => api.post('/auth/login', data);
export const register = (data) => api.post('/auth/register', data);
export const getMe = () => api.get('/auth/me');

// Cases
export const getCases = (params) => api.get('/cases', { params });
export const getCaseCount = () => api.get('/cases/count');
export const getCase = (id) => api.get(`/cases/${id}`);
export const createCase = (data) => api.post('/cases', data);
export const updateCase = (id, data) => api.put(`/cases/${id}`, data);
export const deleteCase = (id) => api.delete(`/cases/${id}`);

// Search
export const searchSimilar = (data) => api.post('/search/similar', data);
export const generateReport = (data) => api.post('/search/report', data);
export const getSearchHistory = () => api.get('/search/history');

export default api;
