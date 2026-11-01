import streamlit as st
import os
from langgraph.graph import StateGraph
from IPython.display import Image
from langchain_core.messages import HumanMessage, AIMessage
from src.backend.config.config import BACKEND_DIR


#-------------------------------- Streamlit Utility Functions --------------------------------#

def display_chat_history(messages):
    for msg in messages:
        if isinstance(msg, HumanMessage):
            with st.chat_message("user"):
                st.markdown(msg.content)

        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                st.markdown(msg.content)
                if msg.response_metadata and ("io_widgets" in msg.response_metadata):
                    for widget_spec in msg.response_metadata["io_widgets"]:
                        st_widget = getattr(st, widget_spec["widget_type"])
                        st_widget(**widget_spec["widget_kwargs"])



@st.cache_data
def save_graph_image(_graph, file_path: str) -> bool:
    try:
        _graph.get_graph().draw_mermaid_png(output_file_path=file_path)
        return True
    except Exception as e:
        print(f"Error saving graph image: {e}")
        return False



def display_langgraph_image(graph):
    output_file_path = os.path.join(BACKEND_DIR, "debugging/app_graph_workflow.png")
    
    if not os.path.exists(output_file_path):
        save_graph_image(graph, output_file_path)
        
    if os.path.exists(output_file_path):
        with st.expander("📊 View LangGraph Workflow"):
            st.image(output_file_path, caption="LangGraph Workflow Visualization")
    else:
        st.error("Could not generate graph image workflow visualization.")


#------------------------------- End of Streamlit Utility Functions --------------------------------#