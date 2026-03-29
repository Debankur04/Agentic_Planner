from langchain_core.messages import SystemMessage, HumanMessage

def prompt_creation(system_prompt, preference, history, input_question):

    tail_prompt = f"""
User Preferences: {preference}
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
    