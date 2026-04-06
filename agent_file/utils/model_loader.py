import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

def load_llm():
    """Load and return the Groq LLM."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=groq_api_key)
    return llm


def load_summarizier_llm():
    groq_api_key = os.getenv('GROQ_API_KEY')
    summary_llm = ChatGroq(model="llama-3.1-8b-instant", api_key=groq_api_key)
    return summary_llm