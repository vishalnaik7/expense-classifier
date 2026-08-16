import React, { useEffect, useState, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { expenseAPI, downloadBlob } from '../utils/api';
import Layout from '../components/Layout';
import useAuthStore from '../store/authStore';

const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0 }).format(amount || 0);

const PERIODS = [
  { value: 'current_month', label: 'This Month' },
  { value: 'last_3_months', label: 'Last 3 Months' },
  { value: 'last_6_months', label: 'Last 6 Months' },
  { value: 'ytd', label: 'Year to Date' },
  { value: '', label: 'All Time' },
  { value: 'custom', label: 'Custom Range' },
];

const ReportsPage = () => {
  const logout = useAuthStore((state) => state.logout);

  const [period, setPeriod] = useState('last_6_months');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(null);

  const buildParams = useCallback(() => {
    if (period === 'custom') {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      return params;
    }
    return period ? { period } : {};
  }, [period, dateFrom, dateTo]);

  const fetchReport = useCallback(async () => {
    if (period === 'custom' && (!dateFrom || !dateTo)) return;
    try {
      setLoading(true);
      setError(null);
      const response = await expenseAPI.getAnalyticsSummary(buildParams());
      setAnalytics(response.data.data);
    } catch (err) {
      if (err.response?.status === 401) { logout(); return; }
      setError(err.response?.data?.error || 'Failed to load report');
    } finally {
      setLoading(false);
    }
  }, [buildParams, period, dateFrom, dateTo, logout]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const handleExport = async (format) => {
    setExporting(format);
    try {
      const response = format === 'csv' ? await expenseAPI.exportCSV(buildParams()) : await expenseAPI.exportPDF(buildParams());
      downloadBlob(response.data, `report.${format === 'csv' ? 'csv' : 'pdf'}`);
    } catch (err) {
      setError('Export failed');
    } finally {
      setExporting(null);
    }
  };

  return (
    <Layout>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Reports</h1>
          <p className="text-gray-500 mt-1 text-sm">Deeper breakdowns of your income and spending</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => handleExport('csv')} disabled={exporting !== null} className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 font-semibold py-2 px-4 rounded-full text-sm shadow-sm disabled:opacity-50">
            {exporting === 'csv' ? 'Exporting...' : 'Export CSV'}
          </button>
          <button onClick={() => handleExport('pdf')} disabled={exporting !== null} className="bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 font-semibold py-2 px-4 rounded-full text-sm shadow-sm disabled:opacity-50">
            {exporting === 'pdf' ? 'Exporting...' : 'Export PDF'}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-4 sm:p-5 mb-6 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-2">
          {PERIODS.map((p) => (
            <button
              key={p.value || 'all'}
              onClick={() => setPeriod(p.value)}
              className={`px-4 py-1.5 rounded-full text-xs sm:text-sm font-semibold transition ${
                period === p.value ? 'bg-indigo-600 text-white' : 'bg-gray-50 text-gray-700 hover:bg-gray-100 border border-gray-200'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        {period === 'custom' && (
          <div className="flex gap-2 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">From</label>
              <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">To</label>
              <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm" />
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-xl p-4 mb-4 text-sm">{error}</div>
      )}

      {loading || !analytics ? (
        <p className="text-gray-400 text-sm">Loading...</p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <p className="text-gray-500 text-xs font-semibold">Total Spending</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(analytics.totalSpent)}</p>
            </div>
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <p className="text-gray-500 text-xs font-semibold">Total Income</p>
              <p className="text-2xl font-bold text-emerald-600 mt-1">{formatCurrency(analytics.totalIncome)}</p>
            </div>
            <div className="bg-white rounded-2xl shadow-sm p-5">
              <p className="text-gray-500 text-xs font-semibold">Net Savings</p>
              <p className={`text-2xl font-bold mt-1 ${analytics.savings >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>{formatCurrency(analytics.savings)}</p>
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-sm p-5 mb-6">
            <h2 className="text-base font-bold text-gray-900 mb-4">Income vs Spending by Month</h2>
            {analytics.monthlyTrends.length > 0 ? (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={analytics.monthlyTrends}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value) => formatCurrency(value)} />
                    <Legend />
                    <Bar dataKey="spending" fill="#EF4444" name="Spending" radius={[6, 6, 0, 0]} />
                    <Bar dataKey="income" fill="#10B981" name="Income" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-gray-500 text-center py-16 text-sm">No data for this period</p>
            )}
          </div>

          <div className="bg-white rounded-2xl shadow-sm p-5">
            <h2 className="text-base font-bold text-gray-900 mb-4">Spending by Category</h2>
            {analytics.categoryBreakdown.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-left text-gray-500">
                      <th className="py-2 px-3 font-semibold">Category</th>
                      <th className="py-2 px-3 font-semibold text-right">Amount</th>
                      <th className="py-2 px-3 font-semibold text-right">% of Spending</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.categoryBreakdown.map((c, i) => (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="py-2.5 px-3 text-gray-900">{c.name}</td>
                        <td className="py-2.5 px-3 text-right font-semibold text-gray-900">{formatCurrency(c.value)}</td>
                        <td className="py-2.5 px-3 text-right text-gray-500">
                          {analytics.totalSpent ? ((c.value / analytics.totalSpent) * 100).toFixed(1) : '0.0'}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-gray-500 text-center py-8 text-sm">No spending data for this period</p>
            )}
          </div>
        </>
      )}
    </Layout>
  );
};

export default ReportsPage;
