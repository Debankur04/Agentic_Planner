from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime


def prompt_creation(system_prompt, preference, history, input_question,memory=''):
    current_date = datetime.now().strftime("%Y-%m-%d")
    tail_prompt = f"""
Current Date: {current_date}

IMPORTANT:
- Always generate travel dates in the future relative to the current date.
- Never use past dates.
User Preferences: {preference}
Memory: {memory}
Chat History: {history}
User Question: {input_question}
"""

    return [
        system_prompt,
        HumanMessage(content=tail_prompt)
    ]

def summarize_history(history: str, user_message) -> str:
    prompt = f"""
Summarize and UPDATE the user's travel memory.

You will be given:
1. Existing memory (previous summary)
2. New conversation

Your job is to:
- PRESERVE important past information
- UPDATE with new preferences or changes
- MERGE intelligently (do NOT overwrite blindly)

---

## Extract and maintain:

- Budget (range or type)
- Travel Style (peaceful / adventurous / cultural)
- Preferred Destinations (beach / mountains / city / etc.)
- Travel Group (solo / couple / family / kids)
- Likes (e.g., beaches, less crowded places)
- Dislikes (e.g., crowded places, expensive trips)

---

## Rules:

- Keep it SHORT (max 5–6 lines)
- Use bullet points
- Do NOT repeat information
- If new info contradicts old → update it
- If no new info → retain previous memory

---
STRICT RULES:
1. Call tools ONLY when necessary.
2. NEVER call the same tool repeatedly with the same arguments.
3. If a tool fails, DO NOT retry endlessly — continue with available data.
4. Once enough information is gathered, STOP calling tools.
5. ALWAYS provide a FINAL ANSWER in natural language.

## Format (STRICT):

User Profile:
- Budget: ...
- Style: ...
- Preferred Places: ...
- Group: ...
- Likes: ...
- Dislikes: ...

---

## Existing Memory:
{history}

## New Conversation:
{user_message}"""
    
    return prompt
    