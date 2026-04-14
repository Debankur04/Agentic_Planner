import os
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase_auth.errors import AuthApiError
from backend.supabase_client.auth import verify_access_token

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    
    if not auth_enabled:
        return None

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization token missing")

    token = credentials.credentials

    try:
        user = verify_access_token(token)
        return user

    except AuthApiError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")