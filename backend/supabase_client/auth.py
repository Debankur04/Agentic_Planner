from backend.supabase_client.supabase_init import supabase_public
from fastapi import HTTPException
from supabase_auth.errors import AuthApiError

def signup(email: str, password: str):
    response = supabase_public.auth.sign_up(
        {
            "email": email,
            "password": password,
        }
    )

    return {
  "message": "Check your email to verify your account"
}

def signin(email: str, password: str):
    try:
        response = supabase_public.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user_id": response.user.id 
        }
    except AuthApiError:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

def refresh_session(refresh_token: str):
    response = supabase_public.auth.refresh_session(refresh_token)
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "user_id": response.user.id
    }

def verify_access_token(token: str):
    response = supabase_public.auth.get_user(token)
    return response.user


def signout():
    return supabase_public.auth.sign_out()