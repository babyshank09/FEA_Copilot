import streamlit as st
from typing import Literal
from functools import lru_cache
from langchain_openai import AzureChatOpenAI
from src.backend.config.llm_config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_ENDPOINT
)


ModelDeploymentName = Literal["gpt-5-nano", "gpt-5.6-luna", "gpt-5.6-terra"]


@lru_cache(maxsize = 5)
def get_llm(deployment_name: ModelDeploymentName):
    return AzureChatOpenAI(
        azure_endpoint= AZURE_OPENAI_ENDPOINT,
        azure_deployment=deployment_name, 
        api_key= AZURE_OPENAI_API_KEY,
        api_version= AZURE_OPENAI_API_VERSION,
    )


@st.cache_resource
def get_parsing_llm():
    return get_llm("gpt-5.6-luna")

@st.cache_resource
def get_fea_planner_llm():
    return get_llm("gpt-5.6-terra")

@st.cache_resource
def get_coding_agent_llm():
    return get_llm("gpt-5.6-terra")

@st.cache_resource
def get_senior_sme_llm():
    return get_llm("gpt-5.6-terra")

@st.cache_resource
def get_sme_llm():
    return get_llm("gpt-5.6-terra")

@st.cache_resource
def get_consultant_llm():
    return get_llm("gpt-5.6-terra")

@st.cache_resource
def get_execution_agent_llm():
    return get_llm("gpt-5.6-luna")

@st.cache_resource
def get_file_relevance_checker_llm():
    return get_llm("gpt-5.6-luna")

@st.cache_resource
def get_rag_query_llm():
    return get_llm("gpt-5-nano")






# if __name__ == "__main__":
#     llm_41 = get_llm("gpt-5.6-terra")
#     llm_41_mini = get_llm("gpt-5.6-luna")
#     llm_4o = get_llm("gpt-5-nano")

#     res = llm_41.invoke("Hi there. ")
#     res2 = llm_41_mini.invoke("who is the cm of tamil nadu ")
#     res3 = llm_4o.invoke("how are you ")

#     print(res.content)
#     print(res2.content)
#     print(res3.content)

#     print("Deployment Name:", llm_41.model_dump())
#     print("Model Name:", llm_41.model_name)