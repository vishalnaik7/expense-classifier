import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach the access token issued at login/signup to every request
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// A 401 here means the access token is missing, expired, or revoked -
// send the user straight to the login page instead of leaving them on a
// page that keeps failing every request with an error message. This
// clears storage directly (rather than going through the auth store) so
// there's no circular import between this module and authStore.js, and
// uses a full page load so no stale in-memory state survives into the
// next login.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  signup: (userData) => apiClient.post('/auth/signup', userData),
  login: (email, password) => apiClient.post('/auth/login', { email, password }),
  getCurrentUser: () => apiClient.get('/auth/me'),
};

export const expenseAPI = {
  uploadCSV: (file, onUploadProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/uploads', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress,
    });
  },
  getUploads: () => apiClient.get('/uploads'),
  getTransactions: (params) => apiClient.get('/transactions', { params }),
  updateTransaction: (id, data) => apiClient.put(`/transactions/${id}`, data),
  getCategories: () => apiClient.get('/categories'),
  createCategory: (data) => apiClient.post('/categories', data),
  updateCategory: (id, data) => apiClient.put(`/categories/${id}`, data),
  deleteCategory: (id) => apiClient.delete(`/categories/${id}`),
  getAnalyticsSummary: (params) => apiClient.get('/analytics/summary', { params }),
  exportCSV: (params) => apiClient.get('/export/csv', { params, responseType: 'blob' }),
  exportPDF: (params) => apiClient.get('/export/pdf', { params, responseType: 'blob' }),
};

export const budgetsAPI = {
  getBudgets: () => apiClient.get('/budgets'),
  setBudget: (categoryId, monthlyLimit) => apiClient.post('/budgets', { category_id: categoryId, monthly_limit: monthlyLimit }),
  updateBudget: (id, monthlyLimit) => apiClient.put(`/budgets/${id}`, { monthly_limit: monthlyLimit }),
  deleteBudget: (id) => apiClient.delete(`/budgets/${id}`),
  sweepToGoal: (id, goalId, amount) => apiClient.post(`/budgets/${id}/sweep`, { goal_id: goalId, amount }),
};

export const goalsAPI = {
  getGoals: () => apiClient.get('/goals'),
  createGoal: (data) => apiClient.post('/goals', data),
  updateGoal: (id, data) => apiClient.put(`/goals/${id}`, data),
  contribute: (id, amount) => apiClient.post(`/goals/${id}/contribute`, { amount }),
  deleteGoal: (id) => apiClient.delete(`/goals/${id}`),
  getInsights: (id) => apiClient.get(`/goals/${id}/insights`),
};

export const chatAPI = {
  sendMessage: (message, history, language) => apiClient.post('/chat', { message, history, language }),
  getLanguages: () => apiClient.get('/chat/languages'),
};

export const healthCheck = () => apiClient.get('/health');

/** Trigger a browser download for a blob response returned by the export endpoints. */
export const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

export default apiClient;
