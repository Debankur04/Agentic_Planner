# Decisions That I will be taking on this project

## Database:-

- SQL (Supabase Database)

Users 

preferences {
    id (UUID, Primary Key),
    user_id (UUID, Foreign Key),
    dietary_preference (TEXT or JSONB),
    preference_id (UUID, reference to MongoDB),
    created_at (TIMESTAMP),
    updated_at (TIMESTAMP)
}

conversations {
    id (UUID, Primary Key),
    user_id (UUID),
    title (TEXT),
    created_at (TIMESTAMP)
}

messages {
    id (UUID, Primary Key),
    conversation_id (UUID, Foreign Key),
    role (TEXT) -- user / assistant / system
    content (TEXT or JSONB),
    created_at (TIMESTAMP)
}


- No SQL (MongoDB Database)
{
  "preference_id": "uuid",
  "user_id": "uuid",
  "memory_block": "User prefers vegetarian meals, avoids spicy food, tends to choose budget-friendly travel options, and likes short weekend trips.",
  "last_updated": "2026-03-23T10:00:00Z",
  "version": 3
}
