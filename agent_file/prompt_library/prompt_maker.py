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

def fallback_json(raw_output: str):
    prompt = f"""
You are a response cleaner.

Your job is to convert the given raw LLM output into a CLEAN, USER-FACING TEXT RESPONSE.

---

## RULES:

1. OUTPUT ONLY plain text (NO JSON, NO markdown code blocks)
2. Do NOT wrap in quotes
3. Do NOT include keys like "reply"
4. Minimum 50 words
5. Fix grammar, remove broken formatting
6. Make it clear and helpful

---

## INPUT:
{raw_output}

---

## OUTPUT:
"""
    return prompt