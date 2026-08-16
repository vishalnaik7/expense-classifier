import React, { useEffect, useState, useCallback } from 'react';
import { goalsAPI } from '../utils/api';
import Layout from '../components/Layout';

const formatCurrency = (amount) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0 }).format(amount || 0);

const GOAL_ICONS = ['🎯', '🏖️', '🏠', '🚗', '💍', '🎓', '💻', '✈️'];

const GoalsPage = () => {
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [target, setTarget] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [icon, setIcon] = useState('🎯');
  const [submitting, setSubmitting] = useState(false);

  const [contributingId, setContributingId] = useState(null);
  const [contributionAmount, setContributionAmount] = useState('');

  const [openInsightsId, setOpenInsightsId] = useState(null);
  const [insights, setInsights] = useState({}); // goalId -> { loading, data, error }

  const fetchGoals = useCallback(async () => {
    try {
      setLoading(true);
      const response = await goalsAPI.getGoals();
      setGoals(response.data.data || []);
    } catch (err) {
      setError('Failed to load goals');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGoals();
  }, [fetchGoals]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim() || !target) return;
    setSubmitting(true);
    setError(null);
    try {
      await goalsAPI.createGoal({
        name: name.trim(),
        target_amount: parseFloat(target),
        target_date: targetDate || null,
        icon,
      });
      setName(''); setTarget(''); setTargetDate(''); setIcon('🎯');
      setShowForm(false);
      fetchGoals();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create goal');
    } finally {
      setSubmitting(false);
    }
  };

  const handleContribute = async (id) => {
    const amount = parseFloat(contributionAmount);
    if (!amount || amount <= 0) { setContributingId(null); return; }
    try {
      await goalsAPI.contribute(id, amount);
      setContributingId(null);
      setContributionAmount('');
      fetchGoals();
    } catch (err) {
      setError('Failed to add contribution');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this goal?')) return;
    try {
      await goalsAPI.deleteGoal(id);
      fetchGoals();
    } catch (err) {
      setError('Failed to delete goal');
    }
  };

  const toggleInsights = async (id) => {
    if (openInsightsId === id) {
      setOpenInsightsId(null);
      return;
    }
    setOpenInsightsId(id);
    if (insights[id]?.data) return; // already fetched, just re-open
    setInsights((prev) => ({ ...prev, [id]: { loading: true } }));
    try {
      const response = await goalsAPI.getInsights(id);
      setInsights((prev) => ({ ...prev, [id]: { loading: false, data: response.data.data } }));
    } catch (err) {
      setInsights((prev) => ({ ...prev, [id]: { loading: false, error: 'Could not load insights for this goal' } }));
    }
  };

  return (
    <Layout>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Goals</h1>
          <p className="text-gray-500 mt-1 text-sm">Save toward what matters to you</p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:opacity-90 text-white font-semibold py-2 px-5 rounded-full text-sm shadow-lg shadow-indigo-600/30"
        >
          {showForm ? 'Cancel' : '+ New Goal'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 rounded-xl p-4 mb-4 text-sm">{error}</div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white rounded-2xl shadow-sm p-5 mb-6 space-y-3">
          <div className="flex flex-wrap gap-2">
            {GOAL_ICONS.map((i) => (
              <button
                key={i}
                type="button"
                onClick={() => setIcon(i)}
                className={`w-10 h-10 rounded-xl text-lg flex items-center justify-center border-2 ${icon === i ? 'border-indigo-500 bg-indigo-50' : 'border-transparent bg-gray-50'}`}
              >
                {i}
              </button>
            ))}
          </div>
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-end">
            <div className="flex-1 w-full">
              <label className="block text-xs font-semibold text-gray-500 mb-1">Goal name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Emergency Fund"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">Target Amount (₹)</label>
              <input
                type="number" min="1" step="0.01"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="100000"
                className="w-36 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">Target Date (optional)</label>
              <input
                type="date"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
                className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold py-2 px-5 rounded-lg text-sm"
            >
              {submitting ? 'Creating...' : 'Create Goal'}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-gray-400 text-sm">Loading...</p>
      ) : goals.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm p-10 text-center">
          <p className="text-gray-500 text-sm">No goals yet. Create one to start tracking your savings progress.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {goals.map((g) => (
            <div key={g.id} className="bg-white rounded-2xl shadow-sm p-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="text-2xl shrink-0">{g.icon}</span>
                  <div className="min-w-0">
                    <p className="font-semibold text-gray-900 text-sm truncate">{g.name}</p>
                    {g.target_date && (
                      <p className="text-xs text-gray-400">by {new Date(g.target_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</p>
                    )}
                  </div>
                </div>
                {g.is_complete && (
                  <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full shrink-0">Complete 🎉</span>
                )}
              </div>

              <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                <span>{formatCurrency(g.current_amount)} of {formatCurrency(g.target_amount)}</span>
                <span className="font-semibold">{g.percent_complete}%</span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2 mb-4">
                <div
                  className={`h-2 rounded-full ${g.is_complete ? 'bg-emerald-500' : 'bg-indigo-500'}`}
                  style={{ width: `${g.percent_complete}%` }}
                />
              </div>

              {contributingId === g.id ? (
                <div className="flex gap-2">
                  <input
                    autoFocus
                    type="number" min="1" step="0.01"
                    value={contributionAmount}
                    onChange={(e) => setContributionAmount(e.target.value)}
                    placeholder="Amount"
                    className="flex-1 min-w-0 border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
                  />
                  <button onClick={() => handleContribute(g.id)} className="bg-indigo-600 text-white text-xs font-semibold px-3 rounded-lg">Add</button>
                  <button onClick={() => setContributingId(null)} className="text-gray-400 text-xs px-2">Cancel</button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => setContributingId(g.id)}
                    className="flex-1 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 text-xs font-semibold py-1.5 rounded-lg"
                  >
                    Add Contribution
                  </button>
                  <button
                    onClick={() => toggleInsights(g.id)}
                    className="bg-amber-50 text-amber-600 hover:bg-amber-100 text-xs font-semibold px-3 rounded-lg"
                  >
                    💡 Insights
                  </button>
                  <button
                    onClick={() => handleDelete(g.id)}
                    className="text-gray-400 hover:text-red-600 text-xs font-semibold px-2"
                  >
                    Delete
                  </button>
                </div>
              )}

              {openInsightsId === g.id && (
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <GoalInsightsPanel state={insights[g.id]} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Layout>
  );
};

/** Shows the retrieval-augmented savings insight for one goal: a math-based completion
 * projection (always available) plus AI-generated tips (only when the backend's
 * ANTHROPIC_API_KEY is configured). */
const GoalInsightsPanel = ({ state }) => {
  if (!state || state.loading) {
    return <p className="text-xs text-gray-400">Analyzing your spending...</p>;
  }
  if (state.error) {
    return <p className="text-xs text-red-500">{state.error}</p>;
  }

  const { projection, context, ai_advice: aiAdvice, ai_available: aiAvailable } = state.data;
  const fmtDate = (iso) => iso && new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  const trendLabel = { improving: '📈 improving', declining: '📉 declining', flat: '➡️ flat' };
  const spendTrendLabel = { up: '↑ rising', down: '↓ falling', flat: '→ steady' };

  return (
    <div className="space-y-3">
      <div className={`rounded-xl p-3 text-xs ${projection.feasible ? 'bg-indigo-50' : 'bg-red-50'}`}>
        {projection.realistic?.months_needed === 0 ? (
          <p className="font-semibold text-emerald-700">Goal already reached 🎉</p>
        ) : projection.feasible ? (
          <>
            <p className="font-semibold text-gray-800">
              At your average savings rate of {formatCurrency(context.avg_monthly_savings)}/month
              {context.savings_rate_percent != null && <> ({context.savings_rate_percent}% of income)</>}, you'll
              reach this goal in ~{projection.realistic.months_needed} month{projection.realistic.months_needed === 1 ? '' : 's'}
              {' '}(around {fmtDate(projection.realistic.projected_completion_date)}).
            </p>
            {(projection.optimistic || projection.pessimistic) && (
              <p className="text-gray-500 mt-1">
                Range based on how much your savings actually swing month to month:{' '}
                {projection.optimistic && <>best case {fmtDate(projection.optimistic.projected_completion_date)}</>}
                {projection.optimistic && projection.pessimistic && ' – '}
                {projection.pessimistic
                  ? <>worst case {fmtDate(projection.pessimistic.projected_completion_date)}</>
                  : (projection.optimistic && <> (worst case: not on pace at all some months)</>)}
              </p>
            )}
            {projection.on_track === false && (
              <p className="text-red-600 mt-1">That's later than your target date — you'll need to save faster to make it in time.</p>
            )}
            {projection.on_track === true && (
              <p className="text-emerald-600 mt-1">You're on track to hit your target date.</p>
            )}
          </>
        ) : (
          <p className="text-red-600 font-semibold">
            Based on your recent history, you're spending more than you earn on average, so this goal isn't on track
            yet. Reducing spending in your top categories below would get it moving.
          </p>
        )}
      </div>

      {context.savings_trend && (
        <p className="text-xs text-gray-600">
          Your savings are {trendLabel[context.savings_trend.direction]} recently — averaging{' '}
          {formatCurrency(context.savings_trend.recent_avg_monthly_savings)}/month lately vs{' '}
          {formatCurrency(context.savings_trend.earlier_avg_monthly_savings)}/month earlier
          {' '}(based on {context.history_months_analyzed} month{context.history_months_analyzed === 1 ? '' : 's'} of history).
        </p>
      )}

      {context.other_active_goals.length > 0 && (
        <div className={`rounded-xl p-3 text-xs ${context.combined_monthly_required_across_goals > context.avg_monthly_savings ? 'bg-red-50' : 'bg-gray-50'}`}>
          <p className="font-semibold text-gray-700 mb-1">
            You're also funding {context.other_active_goals.length} other goal{context.other_active_goals.length === 1 ? '' : 's'}
          </p>
          {context.other_active_goals.map((g) => (
            <div key={g.name} className="flex justify-between text-gray-600">
              <span>{g.name}</span>
              <span>{g.monthly_required ? `${formatCurrency(g.monthly_required)}/mo` : formatCurrency(g.remaining)}</span>
            </div>
          ))}
          {context.combined_monthly_required_across_goals != null && (
            <p className={`mt-1 font-medium ${context.combined_monthly_required_across_goals > context.avg_monthly_savings ? 'text-red-600' : 'text-gray-700'}`}>
              All deadline-based goals combined need {formatCurrency(context.combined_monthly_required_across_goals)}/month
              {context.combined_monthly_required_across_goals > context.avg_monthly_savings
                ? ` — more than your average ${formatCurrency(context.avg_monthly_savings)}/month savings. Something will need to give.`
                : `, which fits within your average savings.`}
            </p>
          )}
        </div>
      )}

      {context.top_spending_categories.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">
            Top spending ({context.history_months_analyzed} month{context.history_months_analyzed === 1 ? '' : 's'})
          </p>
          <div className="space-y-1">
            {context.top_spending_categories.map((c) => (
              <div key={c.name} className="flex justify-between items-center text-xs text-gray-600">
                <span className="flex items-center gap-1.5">
                  {c.name}
                  <span className={`text-[10px] px-1.5 rounded-full ${c.spend_type === 'discretionary' ? 'bg-amber-100 text-amber-700' : c.spend_type === 'essential' ? 'bg-gray-100 text-gray-500' : ''}`}>
                    {c.spend_type === 'discretionary' ? 'cuttable' : c.spend_type === 'essential' ? 'fixed' : ''}
                  </span>
                  {c.trend && <span className="text-[10px] text-gray-400">{spendTrendLabel[c.trend]}</span>}
                </span>
                <span className="font-medium">{formatCurrency(c.amount)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {aiAdvice ? (
        <div className="bg-amber-50 rounded-xl p-3">
          <p className="text-xs text-gray-800 mb-2">{aiAdvice.summary}</p>
          <ul className="space-y-1">
            {aiAdvice.tips.map((tip, i) => (
              <li key={i} className="text-xs text-gray-600 flex gap-1.5">
                <span className="text-amber-500">•</span>
                <span>{tip}</span>
              </li>
            ))}
          </ul>
          {aiAdvice.goal_priority_note && (
            <p className="text-xs text-red-600 mt-2 font-medium">{aiAdvice.goal_priority_note}</p>
          )}
        </div>
      ) : !aiAvailable ? (
        <p className="text-[11px] text-gray-400">AI-personalized tips are off (no ANTHROPIC_API_KEY configured on the backend). Showing the math-based projection only.</p>
      ) : null}
    </div>
  );
};

export default GoalsPage;
