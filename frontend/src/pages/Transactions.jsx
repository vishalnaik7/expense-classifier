import React, { useEffect, useState, useCallback } from 'react';
import { expenseAPI } from '../utils/api';
import Layout from '../components/Layout';
import useAuthStore from '../store/authStore';

const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(amount || 0);

const PAGE_SIZE = 20;

const TransactionsPage = () => {
  const logout = useAuthStore((state) => state.logout);

  const [transactions, setTransactions] = useState([]);
  const [categories, setCategories] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, pages: 1, total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, categoryFilter, typeFilter]);

  const fetchTransactions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params = { page, per_page: PAGE_SIZE };
      if (debouncedSearch) params.search = debouncedSearch;
      if (categoryFilter) params.category = categoryFilter;
      if (typeFilter) params.type = typeFilter;

      const response = await expenseAPI.getTransactions(params);
      setTransactions(response.data.data || []);
      setPagination(response.data.pagination || { page: 1, pages: 1, total: 0 });
    } catch (err) {
      if (err.response?.status === 401) { logout(); return; }
      setError(err.response?.data?.error || 'Failed to load transactions');
    } finally {
      setLoading(false);
    }
  }, [page, debouncedSearch, categoryFilter, typeFilter, logout]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  useEffect(() => {
    expenseAPI.getCategories().then((res) => setCategories(res.data.data || [])).catch(() => {});
  }, []);

  const handleCategoryChange = async (transactionId, newCategoryId) => {
    try {
      await expenseAPI.updateTransaction(transactionId, { category_id: newCategoryId });
      setEditingId(null);
      fetchTransactions();
    } catch (err) {
      setError('Failed to update category');
    }
  };

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Transactions</h1>
        <p className="text-gray-500 mt-1 text-sm">{pagination.total} total records</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm p-4 sm:p-5 mb-4 flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by description..."
          className="flex-1 border border-gray-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="border border-gray-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All Categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="border border-gray-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All Types</option>
          <option value="debit">Debit</option>
          <option value="credit">Credit</option>
        </select>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-xl p-4 mb-4 text-sm">{error}</div>
      )}

      <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-gray-500">
                <th className="py-3 px-4 font-semibold">Date</th>
                <th className="py-3 px-4 font-semibold">Description</th>
                <th className="py-3 px-4 font-semibold">Category</th>
                <th className="py-3 px-4 font-semibold text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="py-8 text-center text-gray-400">Loading...</td></tr>
              ) : transactions.length === 0 ? (
                <tr><td colSpan={4} className="py-8 text-center text-gray-400">No transactions found</td></tr>
              ) : (
                transactions.map((t) => (
                  <tr key={t.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-3 px-4 text-gray-600 whitespace-nowrap">
                      {new Date(t.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                    </td>
                    <td className="py-3 px-4 text-gray-900 max-w-xs truncate" title={t.description}>{t.description}</td>
                    <td className="py-3 px-4">
                      {editingId === t.id ? (
                        <select
                          autoFocus
                          defaultValue={t.category?.id || ''}
                          onChange={(e) => handleCategoryChange(t.id, e.target.value)}
                          onBlur={() => setEditingId(null)}
                          className="border border-gray-200 rounded-lg px-2 py-1 text-xs"
                        >
                          {categories.map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                          ))}
                        </select>
                      ) : (
                        <button
                          onClick={() => setEditingId(t.id)}
                          className="px-2 py-0.5 rounded-full text-xs font-semibold hover:opacity-80"
                          style={{ backgroundColor: (t.category?.color || '#CCCCCC') + '22', color: t.category?.color || '#666' }}
                        >
                          {t.category?.icon} {t.category?.name || 'Other'}
                        </button>
                      )}
                    </td>
                    <td className={`py-3 px-4 text-right font-semibold whitespace-nowrap ${t.type === 'credit' ? 'text-emerald-600' : 'text-gray-900'}`}>
                      {t.type === 'credit' ? '+' : '-'}{formatCurrency(t.amount)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {pagination.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="text-sm font-medium text-gray-600 disabled:text-gray-300 hover:text-indigo-600"
            >
              &larr; Previous
            </button>
            <span className="text-xs text-gray-400">Page {pagination.page} of {pagination.pages}</span>
            <button
              onClick={() => setPage((p) => Math.min(pagination.pages, p + 1))}
              disabled={page >= pagination.pages}
              className="text-sm font-medium text-gray-600 disabled:text-gray-300 hover:text-indigo-600"
            >
              Next &rarr;
            </button>
          </div>
        )}
      </div>
    </Layout>
  );
};

export default TransactionsPage;
