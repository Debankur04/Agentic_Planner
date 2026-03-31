from backend.supabase_client.supabase_init import supabase_public


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
    response =  supabase_public.auth.sign_in_with_password(
        {
            "email": email,
            "password": password,
        }
    )
    return {
    "access_token": response.session.access_token,
    "user_id": response.user.id 
    }


def signout():
    return supabase_public.auth.sign_out()