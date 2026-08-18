import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { budgetsAPI, expenseAPI, goalsAPI } from '../utils/api';
import Layout from '../components/Layout';

const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0 }).format(amount || 0);

const BudgetsPage = () => {
  const [budgets, setBudgets] = useState([]);
  const [categories, setCategories] = useState([]);
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [showForm, setShowForm] = useState(false);
  const [categoryId, setCategoryId] = useState('');
  const [limit, setLimit] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [sweepingBudgetId, setSweepingBudgetId] = useState(null);
  const [sweepGoalId, setSweepGoalId] = useState('');
  const [sweepAmount, setSweepAmount] = useState('');
  const [sweeping, setSweeping] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      setLoading(true);
      const [budgetsRes, categoriesRes, goalsRes] = await Promise.all([
        budgetsAPI.getBudgets(),
        expenseAPI.getCategories(),
        goalsAPI.getGoals(),
      ]);
      setBudgets(budgetsRes.data.data || []);
      setCategories(categoriesRes.data.data || []);
      setGoals(goalsRes.data.data || []);
    } catch (err) {
      setError('Failed to load budgets');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const budgetedCategoryIds = new Set(budgets.map((b) => b.category?.id));
  const availableCategories = categories.filter((c) => !budgetedCategoryIds.has(c.id));

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!categoryId || !limit) return;
    setSubmitting(true);
    setError(null);
    try {
      await budgetsAPI.setBudget(categoryId, parseFloat(limit));
      setCategoryId('');
      setLimit('');
      setShowForm(false);
      fetchAll();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to set budget');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdate = async (id, newLimit) => {
    if (!newLimit || parseFloat(newLimit) <= 0) return;
    try {
      await budgetsAPI.updateBudget(id, parseFloat(newLimit));
      fetchAll();
    } catch (err) {
      setError('Failed to update budget');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Remove this budget?')) return;
    try {
      await budgetsAPI.deleteBudget(id);
      fetchAll();
    } catch (err) {
      setError('Failed to delete budget');
    }
  };

  const openSweepForm = (budget) => {
    setSweepingBudgetId(budget.id);
    setSweepGoalId(goals[0]?.id || '');
    setSweepAmount(String(budget.available_to_sweep));
    setError(null);
  };

  const closeSweepForm = () => {
    setSweepingBudgetId(null);
    setSweepGoalId('');
    setSweepAmount('');
  };

  const handleSweep = async (e, budgetId) => {
    e.preventDefault();
    if (!sweepGoalId || !sweepAmount) return;
    setSweeping(true);
    setError(null);
    try {
      await budgetsAPI.sweepToGoal(budgetId, sweepGoalId, parseFloat(sweepAmount));
      closeSweepForm();
      fetchAll();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to move money into that goal');
    } finally {
      setSweeping(false);
    }
  };

  const overall = budgets.reduce((acc, b) => ({ spent: acc.spent + b.spent, limit: acc.limit + b.monthly_limit }), { spent: 0, limit: 0 });
  const overallPercent = overall.limit > 0 ? Math.round((overall.spent / overall.limit) * 100) : 0;

  return (
    <Layout>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Budgets</h1>
          <p className="text-gray-500 mt-1 text-sm">Monthly spending limits by category</p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          disabled={availableCategories.length === 0}
          className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 disabled:opacity-40 text-white font-semibold py-2 px-5 rounded-full text-sm shadow-lg shadow-indigo-600/30"
        >
          {showForm ? 'Cancel' : '+ Set Budget'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-xl p-4 mb-4 text-sm">{error}</div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white rounded-2xl shadow-sm p-5 mb-6 flex flex-col sm:flex-row gap-3 items-start sm:items-end">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-gray-500 mb-1">Category</label>
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            >
              <option value="">Select a category</option>
              {availableCategories.map((c) => (
                <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Monthly Limit (₹)</label>
            <input
              type="number" min="1" step="0.01"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              placeholder="5000"
              className="w-40 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold py-2 px-5 rounded-lg text-sm"
          >
            {submitting ? 'Saving...' : 'Save Budget'}
          </button>
        </form>
      )}

      {!loading && budgets.length > 0 && (
        <div className="bg-white rounded-2xl shadow-sm p-5 mb-6">
          <div className="flex justify-between text-sm text-gray-600 mb-2">
            <span className="font-semibold">Overall Budget Progress</span>
            <span className="font-bold text-gray-900">{overallPercent}%</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-3">
            <div
              className={`h-3 rounded-full transition-all ${overallPercent >= 100 ? 'bg-red-500' : overallPercent >= 80 ? 'bg-amber-500' : 'bg-emerald-500'}`}
              style={{ width: `${Math.min(overallPercent, 100)}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-2">{formatCurrency(overall.spent)} spent of {formatCurrency(overall.limit)} budgeted this month</p>
        </div>
      )}

      {loading ? (
        <p className="text-gray-400 text-sm">Loading...</p>
      ) : budgets.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm p-10 text-center">
          <p className="text-gray-500 text-sm mb-3">No budgets set yet. Set a monthly limit for a category to start tracking.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {budgets.map((b) => (
            <div key={b.id} className="bg-white rounded-2xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center text-base" style={{ backgroundColor: (b.category?.color || '#CCCCCC') + '22' }}>
                    {b.category?.icon}
                  </div>
                  <span className="font-semibold text-gray-900 text-sm">{b.category?.name}</span>
                </div>
                <button onClick={() => handleDelete(b.id)} className="text-gray-400 hover:text-red-600 text-xs font-semibold">
                  Remove
                </button>
              </div>
              <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                <span>{formatCurrency(b.spent)} spent</span>
                <span>{b.percent_used}%</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2 mb-3">
                <div
                  className={`h-2 rounded-full ${b.percent_used >= 100 ? 'bg-red-500' : b.percent_used >= 80 ? 'bg-amber-500' : 'bg-indigo-500'}`}
                  style={{ width: `${Math.min(b.percent_used, 100)}%` }}
                />
              </div>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs text-gray-400">Limit:</span>
                <input
                  type="number" min="1" step="0.01"
                  defaultValue={b.monthly_limit}
                  onBlur={(e) => e.target.value !== String(b.monthly_limit) && handleUpdate(b.id, e.target.value)}
                  className="w-24 border border-gray-200 rounded-lg px-2 py-1 text-xs"
                />
              </div>

              {b.alert_message && (
                <p className={`text-xs rounded-lg px-3 py-2 mb-3 ${b.alert_level === 'over' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>
                  {b.alert_level === 'over' ? '⚠️ ' : '⏳ '}{b.alert_message}
                </p>
              )}

              {b.available_to_sweep > 0 && goals.length > 0 && (
                sweepingBudgetId === b.id ? (
                  <form onSubmit={(e) => handleSweep(e, b.id)} className="bg-indigo-50 rounded-lg p-3 space-y-2">
                    <p className="text-xs text-indigo-700 font-medium">Move unspent money into a goal</p>
                    <select
                      value={sweepGoalId}
                      onChange={(e) => setSweepGoalId(e.target.value)}
                      className="w-full border border-indigo-200 rounded-lg px-2 py-1.5 text-xs bg-white"
                      required
                    >
                      {goals.map((g) => (
                        <option key={g.id} value={g.id}>{g.icon} {g.name}</option>
                      ))}
                    </select>
                    <div className="flex items-center gap-2">
                      <input
                        type="number" min="0.01" max={b.available_to_sweep} step="0.01"
                        value={sweepAmount}
                        onChange={(e) => setSweepAmount(e.target.value)}
                        className="flex-1 border border-indigo-200 rounded-lg px-2 py-1.5 text-xs bg-white"
                        required
                      />
                      <button type="submit" disabled={sweeping} className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold py-1.5 px-3 rounded-lg text-xs shrink-0">
                        {sweeping ? 'Moving...' : 'Move'}
                      </button>
                      <button type="button" onClick={closeSweepForm} className="text-gray-400 hover:text-gray-600 text-xs font-semibold shrink-0">
                        Cancel
                      </button>
                    </div>
                    <p className="text-xs text-indigo-400">Up to {formatCurrency(b.available_to_sweep)} unspent this month</p>
                  </form>
                ) : (
                  <button
                    onClick={() => openSweepForm(b)}
                    className="w-full text-xs font-semibold text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 rounded-lg py-2 transition"
                  >
                    ✨ {formatCurrency(b.available_to_sweep)} unspent — move to a goal
                  </button>
                )
              )}
              {b.available_to_sweep > 0 && goals.length === 0 && (
                <p className="text-xs text-gray-400 text-center bg-gray-50 rounded-lg py-2">
                  {formatCurrency(b.available_to_sweep)} unspent this month.{' '}
                  <Link to="/goals" className="text-indigo-600 font-semibold hover:text-indigo-800">Set a savings goal</Link> to move it there.
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </Layout>
  );
};

export default BudgetsPage;
