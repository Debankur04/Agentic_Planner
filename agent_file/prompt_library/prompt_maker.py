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
You are a strict JSON formatter.

Your job is to convert the given raw LLM output into VALID JSON.

---

## REQUIRED OUTPUT FORMAT (STRICT JSON ONLY):

{{
  "reply": "string (cleaned, user-facing response, at least 50 words)",
  "preference": "short summary of extracted user preferences",
  "confidence": float (0 to 1)
}}

---

## RULES:

1. OUTPUT ONLY JSON (no explanation, no markdown, no text before/after)
2. Ensure valid JSON (double quotes, no trailing commas)
3. "reply":
   - Clean and rewrite the raw output into a helpful response
   - Must be at least 50 words
   - Remove broken formatting or partial sentences
4. "preference":
   - Extract any user preferences if present
   - If none → return "None"
5. "confidence":
   - 0.9 if response is clear and complete
   - 0.6 if partially usable
   - 0.3 if very uncertain or messy

---

## INPUT RAW OUTPUT:
{raw_output}

---

## OUTPUT:
"""
    return prompt