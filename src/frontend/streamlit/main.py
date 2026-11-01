import streamlit as st
import uuid
import os

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from src.backend.graph.graph import build_graph
from src.backend.utils.utils import load_chat_history, initialize_local_storage
from src.frontend.utils.utils import *
from src.backend.tools.tools import get_embedded_filenames, ingest_user_scripting_docs, delete_doc_from_vectorstore
from src.frontend.streamlit.style import custom_css
from src.frontend.streamlit.auth import login_dialog_box

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "fea_copilot_logo.png")
ICON_PATH = os.path.join(ASSETS_DIR, "fea_copilot_icon.png")

def attam_arambam():

    st.set_page_config(page_title="FEA Copilot", page_icon=ICON_PATH)

    INITIAL_STATES = {
            "working_dir": "",
            "initial_stored_files_info": {},
            "current_embedded_files": [],
            "awaiting_files": False,
            "awaiting_interface_rendering": False,
            "interface_widget_data": {},
            "params_requiring_input": [],
            "thread_id": "default_user_session",
            "new_chat": True,
            "task_id": "default",
            "login_status": False
        }

    for key, default_value in INITIAL_STATES.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

    if not st.session_state["login_status"]:
        submission = login_dialog_box()
        print(f"Login submission: {submission}")
        if not submission:
            print("Login failed or cancelled. Stopping execution.")
            st.stop()
        st.session_state["login_status"] = True
        st.rerun()


    st.markdown(custom_css, unsafe_allow_html=True)
    st.logo(LOGO_PATH)


    if "embedded_files_loaded" not in st.session_state:
        st.session_state["current_embedded_files"] = get_embedded_filenames()
        st.session_state["embedded_files_loaded"] = True

    if st.session_state["new_chat"]:
        with st.spinner("Initializing storage for you"):
            st.session_state["initial_stored_files_info"] = initialize_local_storage()

            
    with st.sidebar:
        working_dir = st.text_input("Working Directory", value=st.session_state.get("working_dir", ""), key="working_dir")
        if not working_dir:
            st.warning("Please enter the working directory to continue")
            st.stop()

        working_dir_abspath = os.path.abspath(working_dir)
        isdir = os.path.isdir(os.path.abspath(working_dir))
        if not isdir:
            st.warning("This is not a real directory. Please check again")
            st.stop()
        st.write(" ")

        st.header("📁 File Upload")
        uploaded_files = st.file_uploader(
            "Upload your scripting files",
            type=["pdf"],
            accept_multiple_files=True
        )

        if uploaded_files and st.button("Embed Documents", type="primary", use_container_width=True):
            ingestion_required_files = []
            
            embedded_names = st.session_state.get("current_embedded_files", [])

            for file in uploaded_files:
                if file.name in embedded_names:
                    continue 
                else:
                    ingestion_required_files.append(file)

            if ingestion_required_files:
                with st.spinner("Embedding documents... This may take a moment"):
                    ingest_user_scripting_docs(uploaded_files=ingestion_required_files)
                st.success("Documents embedded successfully!")
            else:
                st.info("All selected files are already embedded.")

            st.session_state["current_embedded_files"] = get_embedded_filenames()

        st.write(" ")
        st.header("🗑️ Delete File")
        filename = st.selectbox("Select a file to delete", st.session_state.get("current_embedded_files", []))
        
        if st.button("Delete", type="primary", use_container_width=True):
            if filename:
                delete_doc_from_vectorstore(filename=filename)
                st.session_state["current_embedded_files"] = get_embedded_filenames()
                st.error(f"Deleted file: {filename}")

        st.write(" ")
        st.write(" ")
        if st.button("➕ New Chat", use_container_width=True):
            for key, default_value in INITIAL_STATES.items():
                if key != "working_dir":
                    st.session_state[key] = default_value
            st.session_state["thread_id"] = str(uuid.uuid4())
            st.session_state["new_chat"] = True
            st.session_state["current_embedded_files"] = get_embedded_filenames()
            st.rerun()


    def run_workflow(input):
        config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
        status_container = st.empty()

        for event in workflow.stream(input, config=config, stream_mode=["custom","updates"]):
                mode, data = event

                if mode == "custom":
                    status_container.write(data["status"])

                elif mode == "updates":
                    for node_name, node_output in data.items():  
                        #print(f"Node: {node_name}, Output: {node_output}")

                        if node_name == "__interrupt__": 
                            interrupt_obj = node_output[0]
                            if interrupt_obj.value["task"] == "file_upload":
                                st.session_state["awaiting_files"] = True
                                continue
                            elif interrupt_obj.value["task"] == "interface_widget_render":
                                st.session_state["interface_widget_data"] = interrupt_obj.value["data"]["interface_widget_data"]
                                st.session_state["params_requiring_input"] = interrupt_obj.value["data"]["params_requiring_input"]
                                st.session_state["task_id"] = interrupt_obj.value["task_id"]
                                st.session_state["awaiting_interface_rendering"] = True
                                continue
                        
                        if node_output and node_output.get("messages"):
                            with st.chat_message("assistant"):
                                st.markdown(node_output["messages"][-1].content)

        status_container.empty()

    
    workflow = build_graph()
    # display_langgraph_image(workflow)

    history = load_chat_history(workflow=workflow, thread_id=st.session_state["thread_id"])

    greeting_slot = st.empty()
    if history:
        display_chat_history(history)
    else:
        with greeting_slot.container(key="empty_state_greeting", horizontal_alignment="center", vertical_alignment="center"):
            st.markdown("Hi Shankar, what's the plan?", text_alignment="center")


    if st.session_state["awaiting_files"]:
        uploaded_files = st.file_uploader(
            "Please upload the necessary files for the ABAQUS CAE task",
            accept_multiple_files=True,
            type=["inp", "odb", "step", "stp"]
        )

        if st.button("Submit files"):
            if not uploaded_files:
                st.warning("Please select at least one file before submitting.")
            else:
                file_payload = [{"name": f.name, "content": f.read()} for f in uploaded_files]
                st.session_state["awaiting_files"] = False
                run_workflow(Command(resume=file_payload))
                st.rerun()

    elif st.session_state["awaiting_interface_rendering"]:
        user_input = {}
        updated_message = None

        try:
            for param, widget_spec in st.session_state["interface_widget_data"].items():
                if hasattr(st, widget_spec["widget_type"]):
                    st_widget = getattr(st, widget_spec["widget_type"])

                    if param in st.session_state["params_requiring_input"]:
                        widget_spec["widget_kwargs"].setdefault(
                            "key", f"{param}_{st.session_state['task_id']}"
                        )
                        user_input[param] = st_widget(**widget_spec["widget_kwargs"])

                    else:
                        st_widget(**widget_spec["widget_kwargs"])
                        clean_widget_spec = {
                            "widget_type": widget_spec["widget_type"],
                            "widget_kwargs": widget_spec["widget_kwargs"]
                        }
                        for msg in reversed(history):
                            if isinstance(msg, AIMessage):
                                if "io_widgets" not in msg.response_metadata:
                                    msg.response_metadata["io_widgets"] = []
                                
                                if clean_widget_spec not in msg.response_metadata["io_widgets"]:
                                    msg.response_metadata["io_widgets"].append(clean_widget_spec)
                                
                                updated_message = msg
                                break 
            
            interface_agent_message_data = {
                "status": "success",
                "user_input": user_input,
                "error": None
            }

            if st.session_state["params_requiring_input"]:
                if st.button("Submit"):
                    if updated_message:
                        config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
                        workflow.update_state(config, {"messages": [updated_message]})

                    action = "submit"
                    for param, value in user_input.items():
                        if not value:
                            st.error(f"Please fill out the value for {param}")
                            action = "wait"

                    if action == "submit":
                        st.session_state["awaiting_interface_rendering"] = False
                        run_workflow(Command(resume=interface_agent_message_data))
                        st.rerun()
            else:
                if updated_message:
                    config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
                    workflow.update_state(config, {"messages": [updated_message]})
                    
                st.session_state["awaiting_interface_rendering"] = False
                run_workflow(Command(resume=interface_agent_message_data))
                st.rerun()

        except Exception as e:
            error_message = f"Error rendering interface widgets: {e}"
            interface_agent_message_data = {
                "status": "error",
                "user_input": {},
                "error": error_message
            }
            st.session_state["awaiting_interface_rendering"] = False
            run_workflow(Command(resume=interface_agent_message_data))
            st.rerun()


    user_query = st.chat_input("Ask Friday", submit_mode = "disable")

    if user_query and user_query.strip():
        greeting_slot.empty()
        st.chat_message("user").write(user_query)
        
        if st.session_state["new_chat"]:
            with st.skeleton(height = 120, width = 650):
                run_workflow({
                    "messages": [HumanMessage(content=user_query)],
                    "working_directory": working_dir_abspath,
                    "stored_files_info": st.session_state["initial_stored_files_info"]
                })
            st.session_state["new_chat"] = False
        else:
            with st.skeleton(height = 120, width = 650):
                run_workflow({
                    "messages": [HumanMessage(content=user_query)],
                    "working_directory": working_dir_abspath,
                })

        if st.session_state["awaiting_files"]:
            st.rerun()
        if st.session_state["awaiting_interface_rendering"]:
            st.rerun()