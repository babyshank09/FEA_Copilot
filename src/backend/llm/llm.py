import os
import streamlit as st 
from langchain_openai import ChatOpenAI 
from dotenv import load_dotenv  

load_dotenv() 

openai_api_key = os.environ.get("OPENAI_API_KEY")


@st.cache_resource
def get_parsing_llm():
    return ChatOpenAI(
        model_name="gpt-4o-mini",
        temperature=0,
        api_key= openai_api_key,
    )

@st.cache_resource
def get_fea_planner_llm():
    return ChatOpenAI(
        model="gpt-5.6-terra",
        reasoning_effort="medium",
        api_key=openai_api_key,
        use_responses_api=True,
    )

@st.cache_resource
def get_coding_agent_llm():
    return ChatOpenAI(
        model="gpt-5.6-terra",
        reasoning_effort="medium",
        api_key=openai_api_key,
        use_responses_api=True,
    )

@st.cache_resource
def get_senior_sme_llm():
    return ChatOpenAI(
        model="gpt-5.6-terra",
        reasoning_effort="medium",
        api_key=openai_api_key,
        use_responses_api=True,
    )

@st.cache_resource
def get_sme_llm():
    return ChatOpenAI(
        model="gpt-5.6-terra",
        reasoning_effort="medium",
        api_key=openai_api_key,
        use_responses_api=True,
    )

@st.cache_resource
def get_consultant_llm():
    return ChatOpenAI(
        model="gpt-5.6-terra",
        reasoning_effort="medium",
        api_key=openai_api_key,
        use_responses_api=True,
    )

@st.cache_resource
def get_execution_agent_llm():
    return ChatOpenAI(
        model="gpt-5.6-luna",
        api_key=openai_api_key,
    )

@st.cache_resource
def get_file_relevance_checker_llm():
    return ChatOpenAI(
        model="gpt-5.6-luna",
        api_key=openai_api_key,
    )

@st.cache_resource
def get_rag_query_llm():
    return ChatOpenAI(
        model="gpt-5-nano",  
        api_key=openai_api_key,
    )


# if __name__ == "__main__":
#     response = get_parsing_llm().invoke("hi how are you") 
#     response2 = get_fea_planner_llm().invoke("what is rag") 
#     response3 = get_execution_agent_llm.invoke("what is the time to first ttoken for gpt 5.6 sol")
#     response4 = get_rag_query_llm().invoke("what is the time to first ttoken for gpt 5.6 terra ")

#     print(response.content)
#     print(response2.content)
#     print(response3.content)
#     print(response4.content)








