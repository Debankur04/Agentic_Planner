import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from llmops.model_router import ModelRouter
from agent_file.utils.config_loader import load_config

load_dotenv()
config = load_config()
router = ModelRouter(config= config)



def load_llm():
    return router


def load_summarizier_llm():
    groq_api_key = os.getenv('GROQ_API_KEY')
    summary_llm = ChatGroq(model="llama-3.1-8b-instant", api_key=groq_api_key)
    return summary_llm

def load_fallback_to_json_llm():
    groq_api_key = os.getenv('GROQ_API_KEY')
    fallback_to_json_llm = ChatGroq(model="llama-3.1-8b-instant", api_key=groq_api_key)
    return fallback_to_json_llm