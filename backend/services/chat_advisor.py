"""
AI Financial Advisor chatbot.

Retrieval is the same SQL-aggregation approach used for goal insights
(services/goal_advisor.py): main.py's _build_chat_context() pulls this
user's current/previous month totals, up to 12 months of per-month
income/spending/category history (monthly_history), top merchants,
budget status, goals, and recent transactions, and this module's
answer_question() grounds the model's reply in exactly that data rather
than letting it improvise numbers or answer from general knowledge about
"typical" spending.

Runs on an open-source model via services/ai_client.py (Ollama locally,
Groq in production - see that module's docstring) rather than a paid
Anthropic/OpenAI API. Unlike goal insights, chat has no non-AI fallback -
answering a free-text question is inherently a generation task - so this
feature is fully gated behind the active provider being configured
(ai_client.is_configured()), and the caller should surface a clear
"AI Assistant not configured" message rather than a degraded experience
when it isn't.
"""
import json
from typing import Dict, List, Optional

from services import ai_client

MAX_HISTORY_TURNS = 20
MAX_MESSAGE_LENGTH = 2000

# Languages the chat UI offers a selector for. "auto" (default) asks the
# model to detect and mirror whatever language/script the user writes in,
# including Hinglish-style code-switching, rather than forcing a fixed
# language. Quality varies by language: Hindi is one of Llama 3.x's
# officially-trained languages and is reliably strong; the other Indian
# regional languages below are best-effort - the model has seen some of
# each from general pretraining data, but not as a dedicated, guaranteed
# capability, so replies may occasionally slip into English or mix
# scripts for less-represented languages.
SUPPORTED_LANGUAGES = {
    'auto': 'Auto-detect',
    'en': 'English',
    'hi': 'Hindi',
    'mr': 'Marathi',
    'ta': 'Tamil',
    'te': 'Telugu',
    'bn': 'Bengali',
    'gu': 'Gujarati',
    'kn': 'Kannada',
    'ml': 'Malayalam',
    'pa': 'Punjabi',
}


class ChatAdvisorError(Exception):
    """Raised when the chat assistant can't produce a usable reply."""
    pass


def is_configured() -> bool:
    """Whether the AI Assistant is enabled (the active provider is ready)."""
    return ai_client.is_configured()


_CHAT_SYSTEM_PROMPT = """You are a helpful, precise personal finance assistant built into a user's expense tracking app.

You are given retrieved, already-verified facts about this specific user's finances as JSON:
- current_month / previous_month: income, spending, savings totals
- monthly_history: up to 12 months of {month, income, spending, net_savings, category_breakdown}, one entry per calendar month that has data
- category_breakdown_this_month, top_merchants_this_month, budget_status, goals, recent_transactions (last 15 only - NOT a full history)

Use ONLY this data - never invent transactions, amounts, merchants, or categories that are not present in it.

**Answering questions about a specific month** (e.g. "how much did I spend on X in May", "what about June"): look that month up BY NAME in monthly_history (match against the "month" field, e.g. "May 2026"). If it is not present in monthly_history, that means there is no data for it - say so plainly and stop there. Do NOT reason from a different month's numbers, from recent_transactions, or from category_breakdown_this_month to answer a question about a month those don't cover, and do not produce a confused or hedged non-answer - either state the real number from monthly_history, or clearly state you have no data for that month.

When asked for budgeting or saving advice, be specific and reference real numbers and category names from the context - not generic advice like "consider a budget app." Keep replies conversational and concise (a few sentences, or a short list for multiple points) unless the user explicitly asks for more detail. You are not a licensed financial advisor - for major financial decisions (loans, investments, taxes), say so briefly rather than at length, and stick to what the data actually shows."""


def sanitize_history(raw_history: Optional[List[Dict]]) -> List[Dict]:
    """
    Validate and clip caller-supplied conversation history before it
    reaches the model: only well-formed {role, content} turns with role
    in {user, assistant} survive, capped in count and per-turn length so
    a caller can't grow the request unboundedly.
    """
    cleaned = []
    for item in (raw_history or [])[-MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = item.get('content')
        if role not in ('user', 'assistant') or not isinstance(content, str) or not content.strip():
            continue
        cleaned.append({'role': role, 'content': content.strip()[:MAX_MESSAGE_LENGTH]})
    return cleaned


def _language_instruction(language: str) -> str:
    """
    Builds the language-behavior instruction appended to the system
    prompt. An unrecognized code (defensive - the endpoint validates
    against SUPPORTED_LANGUAGES before this is ever called) falls back to
    auto-detect rather than failing the request outright.
    """
    base_rules = (
        'Keep sentences short and grammatically simple - do not attempt long or complex sentence structures, '
        'which are where translation quality breaks down most. Write all numbers, amounts, dates, and currency '
        '(₹, INR) as plain digits exactly as given in the data - never spell out numbers in words or convert '
        'currency. Keep category names, merchant names, and English financial terms (like "budget", "EMI", '
        '"UPI") in English/Roman script even inside an otherwise non-English reply, rather than translating or '
        'transliterating them, since a forced translation of a proper noun or term is usually wrong.'
    )
    if language == 'auto' or language not in SUPPORTED_LANGUAGES:
        return (
            'Detect the language and script the user is writing in - including romanized/Hinglish-style '
            'code-switching - and reply in that same language and script. Do not default to English just '
            f'because the financial context data or category names are in English. {base_rules}'
        )
    name = SUPPORTED_LANGUAGES[language]
    return (
        f'Always reply in {name}, regardless of what language the user writes their message in, unless '
        f'they explicitly ask you to switch languages. {base_rules} If you are not confident enough in this '
        'language to produce a grammatically correct sentence, prefer a natural mix of it with English '
        '(the way a bilingual speaker would code-switch) over a fluent-sounding but grammatically wrong reply.'
    )


def answer_question(context: Dict, message: str, history: Optional[List[Dict]] = None, language: str = 'auto') -> str:
    """
    Answers one chat turn, grounded in `context`. `history` is prior
    turns in this conversation (already sanitized via sanitize_history)
    and is used for conversational continuity only - the factual
    grounding always comes from `context`, not from anything said
    earlier in the conversation, so a stale or misleading claim earlier
    in the chat can't compound. `language` is a code from
    SUPPORTED_LANGUAGES ("auto" mirrors whatever language the user writes in).

    Raises:
        ChatAdvisorError: if the assistant isn't configured, the request
        fails, or it returns unusable output.
    """
    if not is_configured():
        raise ChatAdvisorError(
            'The AI Assistant is not configured. '
            + ('Set GROQ_API_KEY.' if ai_client.AI_PROVIDER == 'groq' else 'Check AI_PROVIDER.')
        )

    system = (
        f'{_CHAT_SYSTEM_PROMPT}\n\n'
        f'Language: {_language_instruction(language)}\n\n'
        f'Retrieved financial context (JSON):\n{json.dumps(context, indent=2)}'
    )
    messages = [{'role': 'system', 'content': system}] + list(history or []) + [{'role': 'user', 'content': message}]

    try:
        client = ai_client.get_client()
        response = client.chat.completions.create(
            model=ai_client.get_model(),
            max_tokens=1536,  # regional-language scripts are often less token-efficient than English
            messages=messages,
        )
    except ai_client.AIProviderError as e:
        raise ChatAdvisorError(str(e))
    except Exception as e:
        hint = ai_client.connection_hint(e)
        raise ChatAdvisorError(f'AI Assistant request failed: {e}' + (f' ({hint})' if hint else ''))

    choice = response.choices[0] if response.choices else None
    if choice is None or choice.finish_reason == 'content_filter':
        raise ChatAdvisorError('The AI Assistant declined to answer that')

    reply = (choice.message.content or '').strip()
    if not reply:
        raise ChatAdvisorError('The AI Assistant returned no content')

    return reply
