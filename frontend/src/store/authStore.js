import create from 'zustand';
import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

// Create axios instance
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json'
  }
});

const useAuthStore = create((set, get) => ({
  // State
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  loading: true,
  error: null,

  // Actions
  initializeAuth: () => {
    // Load from localStorage
    const savedToken = localStorage.getItem('access_token');
    const savedUser = localStorage.getItem('user');
    
    if (savedToken && savedUser) {
      set({
        accessToken: savedToken,
        user: JSON.parse(savedUser),
        isAuthenticated: true,
        loading: false
      });
      
      // Set auth header
      api.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`;
    } else {
      set({ loading: false });
    }
  },

  setupInterceptors: () => {
    // Response interceptor for token refresh
    api.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          // Token expired, logout
          get().logout();
        }
        return Promise.reject(error);
      }
    );
  },

  login: async (email, password) => {
    try {
      set({ error: null });
      
      const response = await api.post('/auth/login', {
        email,
        password
      });
      
      const { data } = response.data;
      
      // Save tokens and user
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      
      // Set auth header
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
      
      set({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: data.user,
        isAuthenticated: true
      });
      
      return { success: true };
    } catch (error) {
      const errorMsg = error.response?.data?.error || 'Login failed';
      set({ error: errorMsg });
      return { success: false, error: errorMsg };
    }
  },

  signup: async (username, email, password) => {
    try {
      set({ error: null });
      
      const response = await api.post('/auth/signup', {
        username,
        email,
        password
      });
      
      const { data } = response.data;
      
      // Save tokens and user
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      
      // Set auth header
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
      
      set({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: data.user,
        isAuthenticated: true
      });
      
      return { success: true };
    } catch (error) {
      const errorMsg = error.response?.data?.error || 'Signup failed';
      set({ error: errorMsg });
      return { success: false, error: errorMsg };
    }
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    
    delete api.defaults.headers.common['Authorization'];
    
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      error: null
    });
  },

  getCurrentUser: async () => {
    try {
      const response = await api.get('/auth/me');
      return response.data.data;
    } catch (error) {
      return null;
    }
  }
}));

export default useAuthStore;