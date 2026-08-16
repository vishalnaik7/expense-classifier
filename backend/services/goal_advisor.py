"""
Retrieval-augmented savings advisor for Goals.

Retrieval here is SQL/aggregation-based rather than vector search: a
user's transaction history is a few hundred structured rows, not a large
free-text corpus, so filtering and aggregating by month/category gives
more accurate, auditable context than embedding similarity search would.
The retrieval itself (querying transactions/budgets) lives in main.py,
next to the models; this module is the "augment + generate" half of the
pipeline - it turns an already-retrieved context dict into either a pure
arithmetic completion projection (always available) or an AI-written
savings plan (only when the active AI provider is configured - see
services/ai_client.py).

Privacy note: generate_insight() sends the retrieved (aggregated, already
per-user-scoped) financial context to whichever open-source model
services/ai_client.py is pointed at (Ollama locally, Groq in production -
see that module's docstring), never to a paid Anthropic/OpenAI API. It is
opt-in via ai_client.is_configured() - if the active provider isn't
ready, is_configured() returns False and callers should skip straight to
the math-only projection.
"""
import json
import math
from datetime import date, datetime
from typing import Dict, Optional

from dateutil.relativedelta import relativedelta

from services import ai_client


class GoalInsightError(Exception):
    """Raised when the AI advice generation cannot produce usable output."""
    pass


def is_configured() -> bool:
    """Whether the AI-generated advice is enabled (the active provider is ready)."""
    return ai_client.is_configured()


def _estimate(remaining_amount: float, monthly_rate: Optional[float]) -> Optional[Dict]:
    """Months (rounded up) and calendar date to close `remaining_amount` at `monthly_rate`, or None if that rate can't get there."""
    if monthly_rate is None or monthly_rate <= 0:
        return None
    months = math.ceil(remaining_amount / monthly_rate)
    return {
        'months_needed': months,
        # datetime.utcnow().date(), not date.today() - matches "today" as
        # defined everywhere else in the app (main.py's _current_month_range
        # / _build_goal_context / _months_until), so this stays consistent
        # with the rest of the pipeline even right at a UTC day boundary.
        'projected_completion_date': (datetime.utcnow().date() + relativedelta(months=months)).isoformat(),
    }


def project_completion(
    remaining_amount: float,
    avg_monthly_savings: float,
    savings_volatility: float,
    target_date_iso: Optional[str],
) -> Dict:
    """
    Pure-math projection - always available, no AI needed. Rather than a
    single number that implies false precision, this gives a
    realistic/optimistic/pessimistic range: "realistic" uses the average
    net monthly savings observed in the retrieved transaction history,
    while "optimistic"/"pessimistic" add/subtract the observed
    month-to-month volatility (population stdev of net savings), so a
    user whose savings swing wildly month to month sees that reflected
    instead of one falsely-confident date. `on_track` compares the
    realistic estimate against the goal's own target date, if it has one.
    """
    if remaining_amount <= 0:
        today_iso = datetime.utcnow().date().isoformat()
        same_estimate = {'months_needed': 0, 'projected_completion_date': today_iso}
        return {
            'realistic': same_estimate,
            'optimistic': same_estimate,
            'pessimistic': same_estimate,
            'on_track': True,
            'feasible': True,
        }

    realistic = _estimate(remaining_amount, avg_monthly_savings)
    optimistic = _estimate(remaining_amount, avg_monthly_savings + savings_volatility)
    pessimistic = _estimate(remaining_amount, avg_monthly_savings - savings_volatility)

    on_track = None
    if realistic and target_date_iso:
        on_track = date.fromisoformat(realistic['projected_completion_date']) <= date.fromisoformat(target_date_iso)

    return {
        'realistic': realistic,
        'optimistic': optimistic,
        'pessimistic': pessimistic,
        'on_track': on_track,
        'feasible': realistic is not None,
    }


_INSIGHT_SYSTEM_PROMPT = """You are a personal finance advisor helping a user reach a specific savings goal.

You are given retrieved, already-verified facts as JSON:
- their goal: target amount, current progress, optional deadline, and the monthly rate that deadline actually requires
- monthly income/spending/net-savings history (history_months_analyzed months, up to 12), and whether their savings are trending up or down (savings_trend, comparing the recent half of that history to the earlier half)
- savings_rate_percent (net savings as a % of income) and savings_volatility (how much net savings swings month to month - high volatility means less certain plans)
- top_spending_categories, each tagged essential or discretionary (spend_type) and with its own trend - a discretionary category that is trending up is the most actionable place to suggest a cut
- current-month budget_status
- other_active_goals the user is also funding, each with its own monthly_required if it has a deadline, plus combined_monthly_required_across_goals - the total the user has already committed to across ALL their goals with deadlines, including this one

Use ONLY these numbers - never invent transactions, amounts, or categories that are not present in the data.

Give practical, specific, quantified advice:
- Reference real category names and amounts. When you suggest cutting a category, state roughly how much cutting it by a given percentage would free up per month, and how many months that would shave off the timeline.
- Prefer suggesting cuts to discretionary categories that are trending up over ones that are already flat or essential.
- If combined_monthly_required_across_goals exceeds the user's avg_monthly_savings, say so explicitly - their goals are currently competing for money they don't have enough of, and they may need to reprioritize, not just cut spending.
- If the user's current average savings rate will not reach this goal by its target date, say so plainly and state what monthly savings rate would reach it in time.
- If savings_volatility is high relative to avg_monthly_savings, mention that their timeline is less certain and point to the realistic/optimistic/pessimistic range rather than a single date.
Keep the tone encouraging but honest, not vague or generic - a reader should be able to act on this today."""

_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-3 sentence plain-language summary of where the user stands on this goal, referencing their actual trend and, if relevant, competing goals"},
        "tips": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 concrete, quantified savings suggestions referencing real category names/amounts and their trend from the retrieved context (e.g. 'Cut Food & Dining, which is up 18% recently, by 20% to free up ~₹X/month and finish ~Y months sooner')",
        },
        "suggested_monthly_savings": {
            "type": ["number", "null"],
            "description": "Monthly savings amount needed to hit the goal by its target_date, or null if the goal has no target_date",
        },
        "goal_priority_note": {
            "type": ["string", "null"],
            "description": "If other_active_goals exist and combined_monthly_required_across_goals exceeds avg_monthly_savings, a short note on how to prioritize between them; otherwise null",
        },
    },
    "required": ["summary", "tips", "suggested_monthly_savings", "goal_priority_note"],
    "additionalProperties": False,
}


def _normalize_insight(data: Dict) -> Dict:
    """
    Validate/coerce the model's JSON-mode output into the exact shape the
    frontend expects. JSON mode guarantees syntactically valid JSON, not
    that the model followed the requested schema - smaller open-source
    models are noticeably less reliable at that than a schema-constrained
    Anthropic response was, so this is stricter than a simple pass-through.
    """
    if not isinstance(data, dict):
        raise GoalInsightError('AI returned an unexpected response shape')

    summary = data.get('summary')
    if not isinstance(summary, str) or not summary.strip():
        raise GoalInsightError('AI response is missing a usable summary')

    raw_tips = data.get('tips')
    tips = [str(t).strip() for t in raw_tips if str(t).strip()] if isinstance(raw_tips, list) else []
    if not tips:
        raise GoalInsightError('AI response is missing usable tips')

    suggested = data.get('suggested_monthly_savings')
    suggested = float(suggested) if isinstance(suggested, (int, float)) else None

    note = data.get('goal_priority_note')
    note = note.strip() if isinstance(note, str) and note.strip() else None

    return {
        'summary': summary.strip(),
        'tips': tips[:5],
        'suggested_monthly_savings': suggested,
        'goal_priority_note': note,
    }


def generate_insight(context: Dict) -> Dict:
    """
    The "generate" step of the RAG pipeline: turns an already-retrieved,
    already-per-user-scoped financial context (see main.py's
    _build_goal_context) into a natural-language savings plan, using
    JSON mode (response_format={"type": "json_object"}) rather than
    strict schema-constrained decoding - the one structured-output
    feature reliably supported across both Ollama and Groq - with the
    exact expected shape spelled out in the prompt and validated by
    _normalize_insight() afterward.

    Raises:
        GoalInsightError: if the AI advice feature isn't configured, the
        request fails, the model declines, or it returns unusable output.
    """
    if not is_configured():
        raise GoalInsightError(
            'AI-assisted advice is not configured. '
            + ('Set GROQ_API_KEY.' if ai_client.AI_PROVIDER == 'groq' else 'Check AI_PROVIDER.')
        )

    system = (
        f'{_INSIGHT_SYSTEM_PROMPT}\n\n'
        'Respond with ONLY a single JSON object matching exactly this JSON Schema '
        f'(no markdown fences, no extra text):\n{json.dumps(_INSIGHT_SCHEMA, indent=2)}'
    )

    try:
        client = ai_client.get_client()
        response = client.chat.completions.create(
            model=ai_client.get_model(),
            max_tokens=1024,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Retrieved financial context:\n\n{json.dumps(context, indent=2)}\n\nGenerate the savings plan."},
            ],
        )
    except ai_client.AIProviderError as e:
        raise GoalInsightError(str(e))
    except Exception as e:
        hint = ai_client.connection_hint(e)
        raise GoalInsightError(f'AI advice request failed: {e}' + (f' ({hint})' if hint else ''))

    choice = response.choices[0] if response.choices else None
    if choice is None or choice.finish_reason == 'content_filter':
        raise GoalInsightError('AI declined to generate advice')

    text = (choice.message.content or '').strip()
    if not text:
        raise GoalInsightError('AI returned no content')

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise GoalInsightError(f'AI returned malformed JSON: {e}')

    return _normalize_insight(data)
