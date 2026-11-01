import os 
import json
import streamlit as st
from src.backend.config.logging_config import app_logger
from src.backend.config.config import ASSETS_DIR, SIMULATION_ARTIFACTS_DIR
from langgraph.graph import StateGraph



UPLOAD_DIR = os.path.join(ASSETS_DIR, "user_uploaded_docs")
os.makedirs(UPLOAD_DIR, exist_ok = True)



def add_streamlit_files_to_storage(files):
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.name)
        with open(file_path, "wb") as f:
            f.write(file.getbuffer())
    app_logger.info("Added %d files to docs directory: %s", len(files), [file.name for file in files])



def get_current_files_in_docs():
    filenames = os.listdir(os.path.join(UPLOAD_DIR))
    app_logger.info(f"Checking for files in docs directory... Files present: {filenames}")
    return filenames



def load_chat_history(workflow: StateGraph, thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = workflow.get_state(config) 
    message_history = snapshot.values.get("messages", []) or []
    return message_history



def initialize_local_storage():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    simulation_artifacts_dirs = ["user_uploaded_files", "parsed_files_info", "stored_files_info", "code_dispatch" ]
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, "stored_files_info", "stored_files_info.json") 

    for dir_name in simulation_artifacts_dirs:
        target_dir = os.path.join(SIMULATION_ARTIFACTS_DIR, dir_name) 
        os.makedirs(target_dir, exist_ok=True) 

    stored_files_info = {"user_uploaded_files": {}, "app_generated_files": {}, "tool_generated_files": {}}
    with open(stored_files_info_json_path, "w") as f:
        json.dump(stored_files_info, f, indent=4, default=str)

    return stored_files_info





