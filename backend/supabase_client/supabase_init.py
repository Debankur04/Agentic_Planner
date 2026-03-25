import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
ANON_KEY = os.getenv("ANON_KEY")
SERVICE_ROLE_KEY = os.getenv("SERVICE_ROLE_KEY")



# User-level client (RLS enforced)
supabase_public: Client = create_client(SUPABASE_URL, ANON_KEY)

# Backend-level client (RLS bypassed)
supabase_admin: Client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)