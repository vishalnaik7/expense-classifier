import React, { useEffect, useState, useCallback } from 'react';
import { expenseAPI } from '../utils/api';
import Layout from '../components/Layout';

const CategoriesPage = () => {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('🏷️');
  const [color, setColor] = useState('#6366F1');
  const [submitting, setSubmitting] = useState(false);

  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState('');

  const fetchCategories = useCallback(async () => {
    try {
      setLoading(true);
      const response = await expenseAPI.getCategories();
      setCategories(response.data.data || []);
    } catch (err) {
      setError('Failed to load categories');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCategories();
  }, [fetchCategories]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await expenseAPI.createCategory({ name: name.trim(), icon, color });
      setName('');
      setIcon('🏷️');
      setColor('#6366F1');
      setShowForm(false);
      fetchCategories();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create category');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRename = async (id) => {
    if (!editName.trim()) { setEditingId(null); return; }
    try {
      await expenseAPI.updateCategory(id, { name: editName.trim() });
      setEditingId(null);
      fetchCategories();
    } catch (err) {
      setError('Failed to rename category');
    }
  };

  const handleDelete = async (id, categoryName) => {
    if (!window.confirm(`Delete "${categoryName}"? Its transactions will move to "Other".`)) return;
    try {
      await expenseAPI.deleteCategory(id);
      fetchCategories();
    } catch (err) {
      setError('Failed to delete category');
    }
  };

  const sharedCategories = categories.filter((c) => !c.is_custom);
  const customCategories = categories.filter((c) => c.is_custom);

  return (
    <Layout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Categories</h1>
          <p className="text-gray-500 mt-1 text-sm">Organize how your transactions are classified</p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 text-white font-semibold py-2 px-5 rounded-full text-sm shadow-lg shadow-indigo-600/30"
        >
          {showForm ? 'Cancel' : '+ New Category'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-xl p-4 mb-4 text-sm">{error}</div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white rounded-2xl shadow-sm p-5 mb-6 flex flex-col sm:flex-row gap-3 items-start sm:items-end">
          <div className="flex-1 w-full">
            <label className="block text-xs font-semibold text-gray-500 mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Pet Care"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Icon (emoji)</label>
            <input
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              maxLength={4}
              className="w-16 border border-gray-200 rounded-lg px-3 py-2 text-sm text-center focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Color</label>
            <input
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="w-16 h-9 border border-gray-200 rounded-lg cursor-pointer"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold py-2 px-5 rounded-lg text-sm"
          >
            {submitting ? 'Creating...' : 'Create'}
          </button>
        </form>
      )}

      {loading ? (
        <p className="text-gray-400 text-sm">Loading...</p>
      ) : (
        <>
          <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wide mb-3">Default Categories</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-8">
            {sharedCategories.map((c) => (
              <div key={c.id} className="bg-white rounded-2xl shadow-sm p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0" style={{ backgroundColor: (c.color || '#CCCCCC') + '22' }}>
                  {c.icon}
                </div>
                <span className="text-sm font-medium text-gray-900 truncate">{c.name}</span>
              </div>
            ))}
          </div>

          <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wide mb-3">Your Custom Categories</h2>
          {customCategories.length === 0 ? (
            <p className="text-gray-400 text-sm">No custom categories yet. Create one above.</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {customCategories.map((c) => (
                <div key={c.id} className="bg-white rounded-2xl shadow-sm p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0" style={{ backgroundColor: (c.color || '#CCCCCC') + '22' }}>
                    {c.icon}
                  </div>
                  {editingId === c.id ? (
                    <input
                      autoFocus
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onBlur={() => handleRename(c.id)}
                      onKeyDown={(e) => e.key === 'Enter' && handleRename(c.id)}
                      className="flex-1 min-w-0 border border-gray-200 rounded-lg px-2 py-1 text-sm"
                    />
                  ) : (
                    <span className="text-sm font-medium text-gray-900 truncate flex-1 min-w-0">{c.name}</span>
                  )}
                  <div className="flex gap-1 shrink-0">
                    <button
                      onClick={() => { setEditingId(c.id); setEditName(c.name); }}
                      className="text-gray-400 hover:text-indigo-600 p-1"
                      title="Rename"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleDelete(c.id, c.name)}
                      className="text-gray-400 hover:text-red-600 p-1"
                      title="Delete"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Layout>
  );
};

export default CategoriesPage;
