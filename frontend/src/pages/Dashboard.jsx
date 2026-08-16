import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { PieChart, Pie, Cell, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import useAuthStore from '../store/authStore';
import { expenseAPI, budgetsAPI, downloadBlob } from '../utils/api';
import Layout from '../components/Layout';
import StatCard from '../components/StatCard';

const PERIODS = [
  { value: 'current_month', label: 'This Month' },
  { value: 'last_3_months', label: 'Last 3 Months' },
  { value: 'last_6_months', label: 'Last 6 Months' },
  { value: 'ytd', label: 'Year to Date' },
  { value: '', label: 'All Time' },
];

const CATEGORY_COLORS = [
  '#6366F1', '#F59E0B', '#EC4899', '#14B8A6', '#8B5CF6',
  '#3B82F6', '#F97316', '#10B981', '#EF4444', '#94A3B8', '#CCCCCC'
];

const emptyAnalytics = {
  totalSpent: 0, totalIncome: 0, savings: 0, totalTransactions: 0, averageTransaction: 0,
  categoryBreakdown: [], monthlyTrends: [], topCategories: [], topMerchants: [],
  change: { spending: null, income: null, transactions: null },
};

const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0 }).format(amount || 0);

const Dashboard = () => {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState('current_month');
  const [exporting, setExporting] = useState(null);
  const [analytics, setAnalytics] = useState(emptyAnalytics);
  const [recentTransactions, setRecentTransactions] = useState([]);
  const [budgets, setBudgets] = useState([]);

  const fetchAll = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = period ? { period } : {};
      const [analyticsRes, txnsRes, budgetsRes] = await Promise.all([
        expenseAPI.getAnalyticsSummary(params),
        expenseAPI.getTransactions({ per_page: 5 }),
        budgetsAPI.getBudgets(),
      ]);

      setAnalytics({ ...emptyAnalytics, ...analyticsRes.data.data });
      setRecentTransactions(txnsRes.data.data || []);
      setBudgets(budgetsRes.data.data || []);
    } catch (err) {
      if (err.response?.status === 401) {
        logout();
        return;
      }
      setError(err.response?.data?.error || 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [period, logout]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleExport = async (format) => {
    setExporting(format);
    try {
      const params = period ? { period } : {};
      const response = format === 'csv' ? await expenseAPI.exportCSV(params) : await expenseAPI.exportPDF(params);
      downloadBlob(response.data, `expenses.${format === 'csv' ? 'csv' : 'pdf'}`);
    } catch (err) {
      if (err.response?.status === 401) { logout(); return; }
      setError('Export failed. Please try again.');
    } finally {
      setExporting(null);
    }
  };

  const spendingSparkline = analytics.monthlyTrends.map((m) => ({ value: m.spending }));
  const incomeSparkline = analytics.monthlyTrends.map((m) => ({ value: m.income }));
  const savingsSparkline = analytics.monthlyTrends.map((m) => ({ value: m.income - m.spending }));

  const overallBudget = budgets.reduce((acc, b) => ({
    spent: acc.spent + b.spent,
    limit: acc.limit + b.monthly_limit,
  }), { spent: 0, limit: 0 });
  const overallBudgetPercent = overallBudget.limit > 0 ? Math.round((overallBudget.spent / overallBudget.limit) * 100) : 0;

  const maxMerchantAmount = Math.max(1, ...analytics.topMerchants.map((m) => m.amount));

  if (loading && !analytics.totalTransactions) {
    return (
      <Layout>
        <div className="flex items-center justify-center py-24">
          <div className="text-center">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-indigo-600 border-t-transparent"></div>
            <p className="mt-4 text-gray-600">Loading your dashboard...</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Hello, {user?.username} 👋</h1>
          <p className="text-gray-500 mt-1 text-sm">Here's your financial overview</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="bg-white border border-gray-200 rounded-full px-4 py-2 text-sm font-medium text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {PERIODS.map((p) => (
              <option key={p.value || 'all'} value={p.value}>{p.label}</option>
            ))}
          </select>
          <button
            onClick={() => handleExport('csv')}
            disabled={exporting !== null}
            className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 font-semibold py-2 px-4 rounded-full text-sm shadow-sm disabled:opacity-50"
          >
            {exporting === 'csv' ? 'Exporting...' : 'Export CSV'}
          </button>
          <Link
            to="/upload"
            className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 text-white font-semibold py-2 px-5 rounded-full text-sm shadow-lg shadow-indigo-600/30 transition"
          >
            Upload Statement
          </Link>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-xl p-4 mb-6 flex justify-between items-center">
          <span className="text-sm">{error}</span>
          <button onClick={fetchAll} className="font-semibold underline text-sm shrink-0">Retry</button>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard
          icon="💸" iconBg="#EEF2FF" label="Total Spending"
          value={formatCurrency(analytics.totalSpent)}
          changePercent={analytics.change.spending}
          sparkline={spendingSparkline} sparklineColor="#6366F1"
        />
        <StatCard
          icon="💵" iconBg="#ECFDF5" label="Total Income"
          value={formatCurrency(analytics.totalIncome)}
          changePercent={analytics.change.income}
          sparkline={incomeSparkline} sparklineColor="#10B981"
        />
        <StatCard
          icon="🔄" iconBg="#EFF6FF" label="Total Transactions"
          value={analytics.totalTransactions}
          changePercent={analytics.change.transactions}
          sparkline={null}
        />
        <StatCard
          icon="🐷" iconBg="#FFF7ED" label="Savings"
          value={formatCurrency(analytics.savings)}
          changePercent={null}
          sparkline={savingsSparkline} sparklineColor="#F97316"
        />
      </div>

      {/* Donut + Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-2xl shadow-sm p-5">
          <h2 className="text-base font-bold text-gray-900 mb-4">Spending by Category</h2>
          {analytics.categoryBreakdown.length > 0 ? (
            <div className="flex flex-col sm:flex-row items-center gap-4">
              <div className="w-full sm:w-1/2 h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={analytics.categoryBreakdown}
                      cx="50%" cy="50%"
                      innerRadius={55} outerRadius={85}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {analytics.categoryBreakdown.map((entry, index) => (
                        <Cell key={index} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} stroke="none" />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => formatCurrency(value)} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="w-full sm:w-1/2 space-y-2 max-h-56 overflow-y-auto">
                {analytics.categoryBreakdown.map((item, index) => (
                  <div key={index} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: CATEGORY_COLORS[index % CATEGORY_COLORS.length] }} />
                      <span className="text-gray-600 truncate">{item.name}</span>
                    </div>
                    <div className="text-right shrink-0 ml-2">
                      <span className="text-gray-900 font-semibold">{formatCurrency(item.value)}</span>
                      <span className="text-gray-400 ml-1.5">
                        {analytics.totalSpent ? ((item.value / analytics.totalSpent) * 100).toFixed(1) : '0.0'}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-center py-16 text-sm">No spending data for this period</p>
          )}
          <Link to="/categories" className="block text-center mt-4 text-sm font-semibold text-indigo-600 hover:text-indigo-800">
            View all categories
          </Link>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-5">
          <h2 className="text-base font-bold text-gray-900 mb-4">Spending Trend</h2>
          {analytics.monthlyTrends.length > 0 ? (
            <div className="h-56 sm:h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={analytics.monthlyTrends}>
                  <defs>
                    <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366F1" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#6366F1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(value) => formatCurrency(value)} />
                  <Area type="monotone" dataKey="spending" stroke="#6366F1" strokeWidth={2.5} fill="url(#spendGradient)" name="Spending" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-gray-500 text-center py-16 text-sm">No trend data for this period</p>
          )}
        </div>
      </div>

      {/* Recent Transactions / Top Merchants / Budget Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-gray-900">Recent Transactions</h2>
            <Link to="/transactions" className="text-xs font-semibold text-indigo-600 hover:text-indigo-800">View all</Link>
          </div>
          {recentTransactions.length > 0 ? (
            <div className="space-y-3">
              {recentTransactions.map((t) => (
                <div key={t.id} className="flex items-center gap-3">
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-sm shrink-0"
                    style={{ backgroundColor: (t.category?.color || '#CCCCCC') + '22' }}
                  >
                    {t.category?.icon || '💳'}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 truncate">{t.description}</p>
                    <p className="text-xs text-gray-400 truncate">{t.category?.name || 'Other'}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className={`text-sm font-semibold ${t.type === 'credit' ? 'text-emerald-600' : 'text-gray-900'}`}>
                      {t.type === 'credit' ? '+' : '-'}{formatCurrency(t.amount)}
                    </p>
                    <p className="text-xs text-gray-400">{new Date(t.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-center py-8 text-sm">No transactions yet</p>
          )}
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-gray-900">Top Merchants</h2>
          </div>
          {analytics.topMerchants.length > 0 ? (
            <div className="space-y-3">
              {analytics.topMerchants.map((m, index) => (
                <div key={index} className="flex items-center gap-3">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white shrink-0"
                    style={{ backgroundColor: CATEGORY_COLORS[index % CATEGORY_COLORS.length] }}
                  >
                    {m.name.charAt(0)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 truncate mb-1">{m.name}</p>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className="h-1.5 rounded-full"
                        style={{ width: `${(m.amount / maxMerchantAmount) * 100}%`, backgroundColor: CATEGORY_COLORS[index % CATEGORY_COLORS.length] }}
                      />
                    </div>
                  </div>
                  <p className="text-xs font-semibold text-gray-700 shrink-0">{formatCurrency(m.amount)}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-center py-8 text-sm">No merchant data yet</p>
          )}
          <p className="text-xs text-gray-400 mt-4">Merchant names are approximated from statement text.</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-bold text-gray-900">Budget Summary</h2>
            <Link to="/budgets" className="text-xs font-semibold text-indigo-600 hover:text-indigo-800">View all</Link>
          </div>
          {budgets.length > 0 ? (
            <>
              <div className="mb-4">
                <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                  <span>Overall Budget Progress</span>
                  <span className="font-semibold text-gray-700">{overallBudgetPercent}%</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${overallBudgetPercent >= 100 ? 'bg-red-500' : overallBudgetPercent >= 80 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                    style={{ width: `${Math.min(overallBudgetPercent, 100)}%` }}
                  />
                </div>
              </div>
              <div className="space-y-3">
                {budgets.slice(0, 4).map((b) => (
                  <div key={b.id}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-700 font-medium truncate flex items-center gap-1.5">
                        <span>{b.category?.icon}</span> {b.category?.name}
                      </span>
                      <span className="text-gray-500 shrink-0">
                        {formatCurrency(b.spent)} / {formatCurrency(b.monthly_limit)}
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${b.percent_used >= 100 ? 'bg-red-500' : b.percent_used >= 80 ? 'bg-amber-500' : 'bg-indigo-500'}`}
                        style={{ width: `${Math.min(b.percent_used, 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-500 text-sm mb-3">No budgets set yet</p>
              <Link to="/budgets" className="text-sm font-semibold text-indigo-600 hover:text-indigo-800">
                Set your first budget &rarr;
              </Link>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};

export default Dashboard;
