import os
import json 
import time
import uuid

from langchain_core.messages import  HumanMessage, AIMessage, SystemMessage, ToolMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.types import interrupt
from langgraph.types import interrupt
from langgraph.config import get_stream_writer

from src.backend.config.config import SIMULATION_ARTIFACTS_DIR
from src.backend.config.logging_config import app_logger
from src.backend.script_templates.main import parse_file, run_abaqus_script
from src.backend.prompts.system_prompts import *
from src.backend.state.state import *
from src.backend.tools.tools import (
    read_parsed_file_info,
    capture_abaqus_model_screenshot,
    capture_abaqus_odb_screenshot,
    scripting_rag_tool,
    procedural_rag_tool,
    syntax_check_tool
)
from src.backend.llm.agent_llm import (
    file_relevance_checker_llm,
    fea_planner_llm,
    fea_planner_llm_with_tools,
    sme_llm,
    sme_llm_with_tools,
    senior_sme_llm,
    senior_sme_llm_with_tools,
    consultant_llm,
    consultant_llm_with_tools,
    coding_agent_llm,
    coding_agent_llm_with_tools,
    execution_agent_llm,
)


logger = app_logger


    

def extract_files_consulted(loop_messages) -> list[str]:
    entries = []
    for m in loop_messages:
        tool_calls = getattr(m, "tool_calls", None)
        if not tool_calls:
            continue
        for call in tool_calls:
            if call.get("name") != "read_parsed_file_info":
                continue
            args = call.get("args", {})
            file_path = args.get("file_path", "(unknown path)")
            entries.append(file_path)
    return entries


def strip_draft_prose(ai_tool_msg):
    content = ai_tool_msg.content
    if isinstance(content, list):
        ai_tool_msg.content = [
            block for block in content
            if not (isinstance(block, dict) and block.get("type") == "text")
        ]
    else:
        ai_tool_msg.content = ""
    return ai_tool_msg


def tool_error_message(call, exc) -> ToolMessage:
    detail = str(exc).strip()
    LIMIT = 2000
    if len(detail) > LIMIT:
        head = int(LIMIT * 0.4)
        tail = LIMIT - head
        detail = (
            f"{detail[:head]}\n\n"
            f"... [{len(detail) - LIMIT:,} characters omitted] ...\n\n"
            f"{detail[-tail:]}"
        )

    logger.warning("Tool '%s' raised: %s", call.get("name"), detail.replace("\n", " ")[:300])

    return ToolMessage(   
        content=(
            f"TOOL ERROR -- {call.get('name')} failed with the arguments you supplied.\n\n"
            f"Arguments: {call.get('args')}\n\n"
            f"{detail}\n\n"
            "These are YOUR arguments to correct -- this is not a system fault. Read the "
            "message above, fix the offending argument and call the tool again, or carry on "
            "without it if it is not essential to the task."
        ),
        tool_call_id=call["id"],
        name=call.get("name"),
    )


def format_fea_plan(fea_plan_object) -> str:
    return "\n".join(
        f"Step {s.step_number}: {s.description} [{s.status}, assigned: {s.assigned_agent}]" for s in fea_plan_object
    ) or "(no plan yet -- first turn for this task)"


def format_coding_plan(coding_plan_object) -> str:
    if not coding_plan_object:
        return "(no plan yet -- first turn for this step)"
    lines = []
    for s in coding_plan_object:
        line = f"Step {s.step_number}: {s.description} [{s.status}]"
        if s.result_summary:
            line += f" -- {s.result_summary}"
        lines.append(line)
    return "\n".join(lines)


def format_message_for_logging(loop_messages):
    message_list = []
    for msg in loop_messages:
        if isinstance(msg, ToolMessage):
            content = f"ToolMessage(name={msg.name}, args={msg.artifact}, content={msg.content})"
            message_list.append(content)
        elif isinstance(msg, AIMessage):
            content = f"AIMessage(name={msg.name}, content={msg.content})"
            message_list.append(content)
        elif isinstance(msg, HumanMessage):
            content = f"HumanMessage(content={msg.content})"
            message_list.append(content)
    return "\n".join(message_list)


def get_present_files(directory: str): 
    file_addresses = []
    for root, dirs, files in os.walk(directory):
        for filename in files:
            full_path = os.path.join(root, filename)
            absolute_path = os.path.abspath(full_path)
            file_addresses.append(absolute_path)

    return file_addresses


def detect_files_produced_and_modified(directory: str, cutoff_time: float) -> list[str]:
    """Returns a list of files modified."""
    modified_files = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime >= cutoff_time:
                    absolute_path = os.path.abspath(filepath)
                    modified_files.append(absolute_path)
            except OSError:
                continue
                
    return modified_files


def detect_updated_files(files_in_dir_before_list: list[str], files_produced_list: list[str]):
    updated_files = []
    for file in files_produced_list:
        if file in files_in_dir_before_list:
            updated_files.append(file)

    return updated_files



def delete_files(file_address_list: list[str]):
    deleted_files = []
    for filepath in file_address_list:
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
                logger.info(f"🗑️ Successfully deleted: {filepath}")
                deleted_files.append(filepath)
            else:
                logger.info(f"⚠️ Skipped (Not a file or doesn't exist): {filepath}")
                
        except PermissionError:
            logger.info(f"❌ Cannot delete (File is locked/permission denied): {filepath}")
        except OSError as e:
            logger.info(f"❌ Error deleting {filepath}: {e}")

    return deleted_files


def global_router(state:State) -> str:
        target_route = state.get("route")
        return target_route





def file_uploader_node(state: State):
    writer = get_stream_writer()
    files = interrupt({"task": "file_upload"}) or []

    writer({"status": "⏳Uploading your files..."})

    simulation_artifacts_dirs = ["user_uploaded_files", "parsed_files_info", "stored_files_info", "code_dispatch"]
    
    file_names = [] 
    file_upload_dir = os.path.join(SIMULATION_ARTIFACTS_DIR, simulation_artifacts_dirs[0]) 
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, simulation_artifacts_dirs[2], "stored_files_info.json") 


    if os.path.exists(stored_files_info_json_path):
        with open(stored_files_info_json_path, "r") as f:
            stored_files_info = json.load(f)
    else:
        stored_files_info = state.get("stored_files_info") or {
            "user_uploaded_files": {},
            "app_generated_files": {},
            "tool_generated_files": {}
        }


    for file_info in files: 
        file_name = file_info["name"]
        file_content = file_info["content"]
        file_names.append(file_name) 
    
        uploaded_file_path = os.path.join(file_upload_dir, file_name)
        with open(uploaded_file_path, "wb") as f:
            f.write(file_content) 
    
        writer({"status": f"⏳Uploaded {file_name}. Parsing the file to extract file info..."})
        parsed_file_info = parse_file(file_path=uploaded_file_path) 
    
        writer({"status": f"⏳Parsed {file_name} successfully. Context engineering the info..."})

        if "user_uploaded_files" not in stored_files_info:
            stored_files_info["user_uploaded_files"] = {}
        stored_files_info["user_uploaded_files"][file_name] = parsed_file_info


    with open(stored_files_info_json_path, "w") as f:
        json.dump(stored_files_info, f, indent=4, default=str)

    files_str = ", ".join(file_names) if file_names else "No files"
    ai_confirmation_message = f"{files_str} uploaded and parsed successfully. Let me just quickly check if the files are relevant and sufficient. Hang in there..."
    writer({"status": ai_confirmation_message})
    
    file_uploader_agent_trace = f"""
    MESSAGE FROM FILE UPLOADER
    {files_str} uploaded and parsed successfully. Im going to now pass this on to file relevancy checker agent so that it can see if the file uploaded is relevant and sufficient.
    """
    heading = "\n------------------------------File Uploader------------------------------"
    logger.info(heading + file_uploader_agent_trace)

    return {
        "messages": [HumanMessage(content=f"I'm uploading {files_str}")], 
        "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=file_uploader_agent_trace)],
        "stored_files_info": stored_files_info,  
        "last_agent": "file_uploader",
    }



def file_relevance_checker_agent(state:State):
    writer = get_stream_writer()

    messages = state["messages"]
    trimmed_history = trim_messages(
            messages, 
            max_tokens = 5000, 
            token_counter = count_tokens_approximately, 
            strategy = "last", 
            include_system = True
        )

    fea_planner_message = None 
    fea_planner_task_identified = None
    fea_planner_additinal_files_description = None
    fea_planner_response = state.get("fea_planner_response")
    stored_files_info_dict = state.get("stored_files_info") or {}

    if state.get("last_agent") == "fea_planner" and fea_planner_response:
        fea_planner_message = fea_planner_response.message_to_file_relevance_checker
        fea_planner_task_identified = fea_planner_response.task_identified 
        fea_planner_additinal_files_description = fea_planner_response.additional_files_needed_description 

    if stored_files_info_dict:
        stored_files_info = json.dumps(stored_files_info_dict, indent=4)
    else:
        stored_files_info = "(storage is empty)"


    context = f"""
    STORED_FILE_INFO: 
    {stored_files_info}
    
    If you have been called by the fea_planner, then the below three fields are populated with the relevant info(MODE B). Otherwise, they are N/A or none(MODE A). 

    TASK_IDENTIFIED: 
    {fea_planner_task_identified if fea_planner_task_identified else "none"}

    MESSAGE_FROM_FEA_PLANNER:
    {fea_planner_message if fea_planner_message else "N/A"}

    WHAT_WAS_PREVIOUSLY_NOTED_AS_STILL_NEEDED:
    {fea_planner_additinal_files_description if fea_planner_additinal_files_description else "N/A"}
    """

    system_message = SystemMessage(content = FILE_RELEVANCE_SYSTEM_PROMPT) 
    human_message = HumanMessage(content = context)

    writer({"status": "Checking relevancy of the files"})

    response = file_relevance_checker_llm.invoke([system_message] + trimmed_history + [human_message])

    file_relevance_checker_agent_trace = f"""
    \n------------------------------File Relevance Agent------------------------------
    Reasoning:
    {"\n".join(response.reasoning) if response.reasoning else 'None'}
    Evidence:
    {"\n".join(response.evidence) if response.evidence else 'None'}
    Verdict: {response.verdict}
    Relevant File Names: {', '.join(response.relevant_file_names) if response.relevant_file_names else 'None'}
    Expected File Type: {response.expected_file_type or 'None'}
    Uploaded File Type: {response.uploaded_file_type or 'None'}
    Additional Files Likely Needed: {response.additional_files_likely_needed}
    Additional Files Reasoning: {response.additional_files_reasoning or 'None'}
    Message to FEA Planner: {response.message_to_fea_planner}"""

    logger.info(file_relevance_checker_agent_trace)

    file_relevance_checker_message = f"""
    MESSAGE FROM FILE RELEVANCE CHECKER:
    verdict: {response.verdict}
    {response.message_to_fea_planner}
    """

    return {
        "file_relevance_checker_response": response,
        "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=file_relevance_checker_message, name="file_relevance_checker")],
        "last_agent": "file_relevance_checker"
    }





def fea_planner_agent(state: "State") -> dict:
    FILE_RESOLUTION_LOOP_THRESHOLD = 6

    _PHASE_ALLOWED_ACTIONS = {
    "identifying_task": {"general_chat_response", "ask_user"},
    "identifying_files": {"route_to_file_uploader", "route_to_file_relevance_checker", "ask_user"},
    "planning_and_dispatch": {
        "dispatch_interface_agent", "dispatch_subject_matter_expert",
        "dispatch_consultant", "dispatch_coding_agent", "route_to_file_uploader", "ask_user", "finalize",
        }
    }
    
    _RECIPIENT_MAP = {
        "general_chat_response": "USER",
        "ask_user": "USER",
        "route_to_file_uploader": "USER",
        "route_to_file_relevance_checker": "FILE RELEVANCE CHECKER",
        "dispatch_interface_agent": "INTERFACE AGENT",
        "dispatch_subject_matter_expert": "SUBJECT MATTER EXPERT",
        "dispatch_consultant": "CONSULTANT",
        "dispatch_coding_agent": "CODING AGENT",
        "finalize": "USER",
    }

    _ROUTE_MAP = {
        "USER": "route_to_user",
        "FILE UPLOADER": "route_to_file_uploader",
        "FILE RELEVANCE CHECKER": "route_to_file_relevance_checker",
        "INTERFACE AGENT": "route_to_interface_agent",
        "SUBJECT MATTER EXPERT": "route_to_subject_matter_expert",
        "CONSULTANT": "route_to_consultant",
        "CODING AGENT": "route_to_coding_agent",
    }
    writer = get_stream_writer()
    writer({"status": "thinking..."})

    messages = state["messages"]
    trimmed_history = trim_messages(
        messages, 
        max_tokens=10000,
        token_counter=count_tokens_approximately,
        strategy="last", 
        include_system=False,
    )

    stored_files_info_dict = state.get("stored_files_info") or {}
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, "stored_files_info/stored_files_info.json")

    fea_planner_conversations = list(state.get("fea_planner_conversations") or [])
    if fea_planner_conversations:
        if isinstance(messages[-1], HumanMessage) and state.get("fea_planner_response").next_action == "ask_user":
            fea_planner_conversations.append(HumanMessage(content = f"""MESSAGE FROM USER:\n{state.get("messages")[-1].content}"""))
    else:
        fea_planner_conversations = trimmed_history
    

    if stored_files_info_dict:
        stored_files_info = json.dumps(stored_files_info_dict, indent=4)
    else:
        stored_files_info = "(storage is empty)"

    working_directory = state.get("working_directory")
    if not working_directory:
        logger.error("fea_planner_agent: working_directory is missing from state.")
        working_directory = "(WORKING_DIRECTORY NOT PROVIDED -- DO NOT DISPATCH CODING AGENT UNTIL RESOLVED)"

    ssme_escalation = (state.get("senior_sme_escalation") or "(none)")
    ssme_continuous = (state.get("senior_sme_continuous_escalation_count") or 0)
    ssme_total = (state.get("senior_sme_total_escalation_count") or 0)
    coding_escalation = (state.get("coding_escalation") or "(none)")
    coding_continuous = (state.get("coding_continuous_escalation_count") or 0)
    coding_total = (state.get("coding_total_escalation_count") or 0)

    plan = state.get("fea_planner_plan") or []
    decoded_plan = format_fea_plan(fea_plan_object = plan)

    current_phase_in = state.get("fea_planner_phase") or "identifying_task"
    loop_count_in = (state.get("file_resolution_loop_count") or 0)

    prior_response = state.get("fea_planner_response")
    prior_task_context = "(not yet determined)"
    if prior_response and current_phase_in != "identifying_task":
        prior_task_context = (
            f"task_identified: {prior_response.task_identified}\n"
            f"files_needed: {prior_response.files_needed}\n"
            f"file_situation: {prior_response.file_situation}\n"
            f"relevant_file_names: {', '.join(prior_response.relevant_file_names) or 'none'}"
        )

    context = f"""
    CURRENT_PHASE: {current_phase_in}

    FILE_RESOLUTION_LOOP_COUNT (so far): {loop_count_in}

    PREVIOUSLY RESOLVED TASK CONTEXT (if any):
    {prior_task_context}

    STORED_FILES_INFO:
    {stored_files_info}

    WORKING_DIRECTORY:
    {working_directory}

    CURRENT PLAN (if any):
    {decoded_plan}

    SENIOR_SME_ESCALATION (if any):
    {ssme_escalation}

    CODING_ESCALATION (if any):
    {coding_escalation}

    SENIOR_SME_CONTINUOUS_ESCALATION_COUNT: {ssme_continuous}
    SENIOR_SME_TOTAL_ESCALATION_COUNT: {ssme_total}
    CODING_CONTINUOUS_ESCALATION_COUNT: {coding_continuous}
    CODING_TOTAL_ESCALATION_COUNT: {coding_total}
    """

    system_message = SystemMessage(content=FEA_PLANNER_SYSTEM_PROMPT)
    human_message = HumanMessage(content=context)
    loop_messages = [system_message] + fea_planner_conversations + [human_message] 

    FINALIZE_INSTRUCTION = "You have gathered whatever situational awareness you need. Now produce your final FEAPlannerDecision"

    for _ in range(5):
        ai_tool_msg = fea_planner_llm_with_tools.invoke(loop_messages)

        if not ai_tool_msg.tool_calls:
            break

        strip_draft_prose(ai_tool_msg)
        loop_messages.append(ai_tool_msg)
        fea_planner_conversations.append(ai_tool_msg)

        for call in ai_tool_msg.tool_calls:
            tool_fn = {
                "capture_abaqus_model_screenshot": capture_abaqus_model_screenshot, 
                "capture_abaqus_odb_screenshot": capture_abaqus_odb_screenshot,
                "procedural_rag_tool": procedural_rag_tool,
                "read_parsed_file_info": read_parsed_file_info
            }[call["name"]]

            try:
                tool_result = tool_fn.invoke(call["args"])
            except Exception as tool_exc:
                error_message = tool_error_message(call, tool_exc)
                loop_messages.append(error_message)
                fea_planner_conversations.append(error_message)
                continue

            if call["name"] == "capture_abaqus_model_screenshot" or call["name"] == "capture_abaqus_odb_screenshot":
                b64_image = tool_result["b64_image"]
                image_file_info = tool_result["image_file_info"]
                text_summary = tool_result["text"]

                tool_message = ToolMessage( 
                    content=[
                        {
                            "type": "text", 
                            "text": text_summary
                        },
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"}
                        }
                    ],
                    tool_call_id=call["id"], 
                    name=call["name"],
                    artifact=call["args"]
                )

                stored_files_info_dict["tool_generated_files"][image_file_info["file_name"]] = image_file_info
                with open(stored_files_info_json_path, "w") as f:
                    json.dump(stored_files_info_dict, f, indent=4, default=str)   
            else:
                tool_message = ToolMessage(content=str(tool_result), tool_call_id=call["id"], name=call["name"])
            loop_messages.append(tool_message)
            fea_planner_conversations.append(tool_message)


    response: FEAPlannerDecision = fea_planner_llm.invoke(loop_messages + [HumanMessage(content=FINALIZE_INSTRUCTION)])

    writer({"status": response.status_update})

    effective_next_action = response.next_action
    effective_current_phase = response.current_phase
    effective_message_to_user = response.message_to_user

    if response.next_action not in _PHASE_ALLOWED_ACTIONS.get(response.current_phase, set()):
        logger.warning(
            "FEA Planner: next_action=%s invalid for current_phase=%s -- forcing ask_user.",
            response.next_action, response.current_phase,
        )
        effective_next_action = "ask_user"
        effective_current_phase = current_phase_in
        effective_message_to_user = "I'm having trouble understanding your request. Could you clarify and be a little specific on what you'd like me to help with?"


    give_up_triggered = ssme_continuous >= 3 or ssme_total >= 7 or coding_continuous >= 3 or coding_total >= 7
    if give_up_triggered and effective_next_action != "finalize":
        logger.warning("FEA Planner: give-up threshold crossed but chose %s -- forcing finalize.", effective_next_action)
        effective_next_action = "finalize"
        effective_message_to_user = "I wasn't able to complete this one -- it might help to try rephrasing what you're looking for."


    is_unresolved = effective_current_phase in ("identifying_task", "identifying_files") and effective_next_action != "general_chat_response"
    new_loop_count = (loop_count_in + 1) if is_unresolved else 0
    if is_unresolved and new_loop_count >= FILE_RESOLUTION_LOOP_THRESHOLD and effective_next_action != "ask_user":
        logger.warning("FEA Planner: file_resolution_loop_count=%s -- forcing ask_user.", new_loop_count)
        effective_next_action = "ask_user"
        effective_message_to_user = "I'm having trouble pinning down exactly what's needed here -- could you clarify?"
        new_loop_count = 0


    recipient = _RECIPIENT_MAP[effective_next_action]
    revised_plan = format_fea_plan(fea_plan_object = response.plan)
    context_message = format_message_for_logging(loop_messages)


    if recipient == "USER":
        fea_planner_message = effective_message_to_user

    elif recipient == "INTERFACE AGENT":
        fea_planner_message = json.dumps(
            [widget_spec.model_dump() for widget_spec in response.message_to_interface_agent], indent=4
        ) if response.message_to_interface_agent else "none"

    elif recipient == "FILE RELEVANCE CHECKER":
        fea_planner_message = response.message_to_file_relevance_checker

    else:
        fea_planner_message = response.dispatch_instructions


    fea_planner_trace = f"""
        ------------------------------FEA Planner Agent------------------------------
        ==============================
        Context Recieved:
        {context_message}
        ==============================
    
        Reasoning: {response.reasoning}
        Evidence: {response.evidence}
        Current Phase (raw / effective): {response.current_phase} / {effective_current_phase}
        Next Action (raw / effective): {response.next_action} / {effective_next_action}
        Task Type: {response.task_type} | Task Identified: {response.task_identified}
        Files Needed: {response.files_needed} | File Situation: {response.file_situation}
        Loop Count: {new_loop_count}
        Plan:
        {revised_plan}
        WORKING_DIRECTORY: {working_directory}
        Message to {recipient}: {fea_planner_message}
        """
    logger.info(fea_planner_trace)


    fea_planner_conversation_message = f"""
    MESSAGE FROM FEA PLANNER(YOU) TO {recipient}:
    {fea_planner_message}
    """
    
    subagent_dispatch_message = f"""
    MESSAGE FROM FEA PLANNER:
    {fea_planner_message}
    """

    is_task_ending = effective_next_action in ("finalize", "general_chat_response")
    resets_task_state = is_task_ending
    route = _ROUTE_MAP[recipient]

    if effective_next_action == "route_to_file_uploader":
        route = "route_to_file_uploader"

    return_dict = {
        "fea_planner_conversations": (
            [] if resets_task_state
            else fea_planner_conversations + [AIMessage(content=fea_planner_conversation_message, name = "fea_planner")]
        ),
        "sme_dispatch_events_sme_only": (
                            [] if resets_task_state
                            else ((state.get("sme_dispatch_events_sme_only") or []) + [HumanMessage(content=subagent_dispatch_message)]
                                if recipient == "SUBJECT MATTER EXPERT" else (state.get("sme_dispatch_events_sme_only") or []))
        ),
        "sme_dispatch_events_senior_sme_only": (
                    [] if resets_task_state
                    else ((state.get("sme_dispatch_events_senior_sme_only") or []) + [HumanMessage(content=subagent_dispatch_message)]
                        if recipient == "SUBJECT MATTER EXPERT" else (state.get("sme_dispatch_events_senior_sme_only") or []))
        ),
        "coding_dispatch_events": (
            [] if resets_task_state
            else ((state.get("coding_dispatch_events") or []) + [HumanMessage(content=subagent_dispatch_message)]
                if recipient == "CODING AGENT" else (state.get("coding_dispatch_events") or []))
        ),
        "consultant_dispatch_events": (
            [] if resets_task_state
            else ((state.get("consultant_dispatch_events") or []) + [HumanMessage(content=subagent_dispatch_message)]
                if recipient == "CONSULTANT" else (state.get("consultant_dispatch_events") or []))
        ),
        "fea_planner_response": response,
        "fea_planner_phase": "identifying_task" if resets_task_state else effective_current_phase,
        "file_resolution_loop_count": 0 if resets_task_state else new_loop_count,
        "fea_planner_plan": None if resets_task_state else response.plan,
        "coding_escalation": None,
        "senior_sme_escalation": None,
        "senior_sme_continuous_escalation_count": 0 if resets_task_state else ssme_continuous,
        "senior_sme_total_escalation_count": 0 if resets_task_state else ssme_total,
        "coding_continuous_escalation_count": 0 if resets_task_state else coding_continuous,
        "coding_total_escalation_count": 0 if resets_task_state else coding_total,
        "submitted_code": None,
        "execution_agent_verdict": None,
        "execution_stdout": None,
        "execution_stderr": None,
        "stored_files_info": stored_files_info_dict,
        "route": route,
        "last_agent": "fea_planner"
    }

    if effective_message_to_user:
        return_dict["messages"] = [AIMessage(content=effective_message_to_user, name="fea_planner")]

    return return_dict



def sme_agent(state: "State") -> dict:
    writer = get_stream_writer()
    stored_files_info_dict = state.get("stored_files_info") or {}
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, "stored_files_info/stored_files_info.json")
    
    dispatch_messages_sme_only = list(state.get("sme_dispatch_events_sme_only") or [])

    updated_files = (state.get("updated_files_sme_signal") or [])
    if updated_files:
        notification = f"""
        MESSAGE FROM FEA PLANNER:
        The files {", ".join(updated_files)} may have been updated and changed. 
        It is advisable to use your tools again if and only if you need the latest information regarding {", ".join(updated_files)}
        """
        dispatch_messages_sme_only.append(HumanMessage(content=notification))


    ssme_rejection_count = (state.get("senior_sme_rejection_count") or 0)
    ssme_verdict = (state.get("senior_sme_verdict") or "N/A")

    if stored_files_info_dict:
        stored_files_info = json.dumps(stored_files_info_dict, indent=4)
    else:
        stored_files_info = "(storage is empty)"

    context = f"""
    STORED_FILES_INFO:
    {stored_files_info}

    SENIOR_SME_VERDICT:
    {ssme_verdict}

    SENIOR_SME_REJECTION_COUNT:
    {ssme_rejection_count}
    """

    system_message = SystemMessage(content=SME_SYSTEM_PROMPT)
    human_message = HumanMessage(content=context)
    loop_messages = [system_message] + dispatch_messages_sme_only + [human_message] 


    FINALIZE_INSTRUCTION = (
        "You have gathered whatever situational awareness you need. Now produce your final SMEDecision"
    )

    MAX_TOOL_ITERATIONS = 5
    for _ in range(MAX_TOOL_ITERATIONS):
        ai_tool_msg = sme_llm_with_tools.invoke(loop_messages)

        if not ai_tool_msg.tool_calls:
            break

        strip_draft_prose(ai_tool_msg)
        loop_messages.append(ai_tool_msg)
        dispatch_messages_sme_only.append(ai_tool_msg)

        for call in ai_tool_msg.tool_calls:
            tool_fn = {
                "capture_abaqus_model_screenshot": capture_abaqus_model_screenshot,
                "capture_abaqus_odb_screenshot": capture_abaqus_odb_screenshot,
                "read_parsed_file_info": read_parsed_file_info
            }[call["name"]]

            try:
                tool_result = tool_fn.invoke(call["args"])
            except Exception as tool_exc:
                error_message = tool_error_message(call, tool_exc)
                loop_messages.append(error_message)
                dispatch_messages_sme_only.append(error_message)
                continue

            if call["name"] == "capture_abaqus_model_screenshot" or call["name"] == "capture_abaqus_odb_screenshot":
                b64_image = tool_result["b64_image"]
                image_file_info = tool_result["image_file_info"]
                text_summary = tool_result["text"]

                tool_message = ToolMessage(
                    content=[
                        {
                            "type": "text",
                            "text": text_summary
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"}
                        }
                    ],
                    tool_call_id=call["id"],
                    name=call["name"],
                    artifact=call["args"]
                )

                stored_files_info_dict["tool_generated_files"][image_file_info["file_name"]] = image_file_info
                with open(stored_files_info_json_path, "w") as f:
                    json.dump(stored_files_info_dict, f, indent=4, default=str)
            else:
                tool_message = ToolMessage(content=str(tool_result), tool_call_id=call["id"], name=call["name"])

            loop_messages.append(tool_message)
            dispatch_messages_sme_only.append(tool_message)


    response: SMEDecision = sme_llm.invoke(loop_messages + [HumanMessage(content=FINALIZE_INSTRUCTION)])
    writer({"status": response.status_update})
    response.files_consulted = extract_files_consulted(loop_messages)


    context_message = format_message_for_logging(loop_messages)
    sme_trace = f"""
    ------------------------------SME Agent------------------------------
    ==============================
    Context Recieved:
    {context_message}
    ==============================

    status: {response.status}
    contains_quantitative_claims: {response.contains_quantitative_claims}
    status_update: "{response.status_update}"

    reasoning:
    {response.reasoning}

    evidence:
    {response.evidence}

    message_to_planner:
    {response.message_to_planner}

    files_consulted: {', '.join(response.files_consulted) if response.files_consulted else 'none'}
    """
    logger.info(sme_trace)


    if response.status == "needs_clarification":
        sme_message = f"""
        MESSAGE FROM SME TO FEA PLANNER:
        {response.message_to_planner}
        """
        route = "route_to_fea_planner"
    else:
        sme_message = f"""
        MESSAGE FROM SME TO SENIOR SME:
        I have created a draft of the response I plan to handover to the fea planner. Below is the draft:
        ---------------------
        {response.message_to_planner}
        ---------------------
        Please review and provide your feedback. If you approve, I will hand this over to the fea planner. If you have any concerns, please let me know and I will address them before proceeding.
        """
        route = "route_to_senior_sme"

    return {
        "sme_dispatch_events_senior_sme_only": (state.get("sme_dispatch_events_senior_sme_only") or []) + [AIMessage(content=sme_message, name = "sme")],
        "sme_dispatch_events_sme_only": dispatch_messages_sme_only + [AIMessage(content=sme_message, name = "sme")],
        "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=sme_message, name = "sme")],
        "sme_response": response,
        "updated_files_sme_signal": [],
        "stored_files_info": stored_files_info_dict,
        "route": route,
        "last_agent": "sme"
    }

    

def senior_sme_agent(state: "State") -> dict:
    ESCALATION_THRESHOLD = 4
    writer = get_stream_writer()

    stored_files_info_dict = state.get("stored_files_info") or {}
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, "stored_files_info/stored_files_info.json")

    dispatch_messages_senior_sme_only = list(state.get("sme_dispatch_events_senior_sme_only") or [])

    rejection_count = (state.get("senior_sme_rejection_count") or 0)
    continuous_escalation_count = (state.get("senior_sme_continuous_escalation_count") or 0)
    total_escalation_count = (state.get("senior_sme_total_escalation_count") or 0)

    
    if stored_files_info_dict:
        stored_files_info = json.dumps(stored_files_info_dict, indent=4)
    else:
        stored_files_info = "(storage is empty)"

    
    sme_response = state.get("sme_response")

    sme_decision = f"""
    ------------------------------SME Agent Outputs------------------------------
    status: {sme_response.status}
    contains_quantitative_claims: {sme_response.contains_quantitative_claims}

    reasoning:
    {sme_response.reasoning}

    evidence:
    {sme_response.evidence}

    message_to_planner:
    Refer to the message from SME above for the message to the planner. Has not been included here to avoid redundancy.

    files_consulted: {', '.join(sme_response.files_consulted) if sme_response.files_consulted else 'none'}
    -----------------------------------------------------------------------------
    """

    context = f""" 
    STORED_FILES_INFO:
    {stored_files_info}

    SME_AGENT'S_DECISION_TO_BE_REVIEWED:
    {sme_decision}

    SENIOR_SME_REJECTION_COUNT:
    {rejection_count}
    """
    

    system_message = SystemMessage(content=SENIOR_SME_SYSTEM_PROMPT)
    human_message = HumanMessage(content=context)
    loop_messages = [system_message] + dispatch_messages_senior_sme_only + [human_message] 

    FINALIZE_INSTRUCTION = (
        "You have gathered whatever situational awareness you need. Now produce your final SeniorSMEVerdict"
    )

    MAX_TOOL_ITERATIONS = 5
    for _ in range(MAX_TOOL_ITERATIONS):
        ai_tool_msg = senior_sme_llm_with_tools.invoke(loop_messages)

        if not ai_tool_msg.tool_calls:
            break

        strip_draft_prose(ai_tool_msg)
        loop_messages.append(ai_tool_msg)
        dispatch_messages_senior_sme_only.append(ai_tool_msg)

        for call in ai_tool_msg.tool_calls:
            tool_fn = {
                "capture_abaqus_model_screenshot": capture_abaqus_model_screenshot,
                "capture_abaqus_odb_screenshot": capture_abaqus_odb_screenshot,
                "read_parsed_file_info": read_parsed_file_info
            }[call["name"]]

            try:
                tool_result = tool_fn.invoke(call["args"])
            except Exception as tool_exc:
                error_message = tool_error_message(call, tool_exc)
                loop_messages.append(error_message)
                dispatch_messages_senior_sme_only.append(error_message)
                continue

            if call["name"] == "capture_abaqus_model_screenshot" or call["name"] == "capture_abaqus_odb_screenshot":
                b64_image = tool_result["b64_image"]
                image_file_info = tool_result["image_file_info"]
                text_summary = tool_result["text"]

                tool_message = ToolMessage(
                    content=[
                        {
                            "type": "text", 
                            "text": text_summary
                        },
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"}
                        }
                    ],
                    tool_call_id=call["id"], 
                    name=call["name"],
                    artifact=call["args"]
                )

                stored_files_info_dict["tool_generated_files"][image_file_info["file_name"]] = image_file_info
                with open(stored_files_info_json_path, "w") as f:
                    json.dump(stored_files_info_dict, f, indent=4, default=str)             
            else:
                tool_message = ToolMessage(content=str(tool_result), tool_call_id=call["id"], name=call["name"])

            loop_messages.append(tool_message)
            dispatch_messages_senior_sme_only.append(tool_message)


    response: SeniorSMEVerdict = senior_sme_llm.invoke(
        loop_messages + [HumanMessage(content=FINALIZE_INSTRUCTION)]
    )
    writer({"status": response.status_update})
    response.files_consulted = extract_files_consulted(loop_messages)


    context_message = format_message_for_logging(loop_messages)
    senior_sme_trace = f"""
    ------------------------------Senior SME Agent------------------------------
    ==============================
    Context Recieved:
    {context_message}
    ==============================

    verdict: {response.verdict}
    claims_independently_verified: {response.claims_independently_verified}
    status_update: "{response.status_update}"

    reasoning:
    {response.reasoning if response.reasoning else "  none"}

    evidence:
    {response.evidence if response.evidence else "  none"}

    concern:
    {response.concern if response.concern else "none"}

    message_to_sme:
    {response.message_to_sme if response.message_to_sme else "none"}

    difficulty_summary:
    {response.difficulty_summary if response.difficulty_summary else "none"}

    suggestion_for_planner:
    {response.suggestion_for_planner if response.suggestion_for_planner else "none"}

    files_consulted: {', '.join(response.files_consulted) if response.files_consulted else 'none'}
    """
    logger.info(senior_sme_trace)


    if response.verdict == "approved":
        senior_sme_message = f"""
        MESSAGE FROM SENIOR SME TO SME:
        Verdict: Approved
        {response.message_to_sme}
        """ 
        sme_message = f"""
        MESSAGE FROM SME TO FEA PLANNER:
        {sme_response.message_to_planner}
        """
        route = "route_to_fea_planner"

        return {
            "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=senior_sme_message, name = "senior_sme")] + [AIMessage(content=sme_message, name = "sme")],
            "sme_dispatch_events_senior_sme_only": dispatch_messages_senior_sme_only + [AIMessage(content=senior_sme_message, name = "senior_sme")] + [AIMessage(content=sme_message, name = "sme")],
            "sme_dispatch_events_sme_only": (state.get("sme_dispatch_events_sme_only") or []) + [AIMessage(content=senior_sme_message, name = "senior_sme")] + [AIMessage(content=sme_message, name = "sme")],
            "senior_sme_verdict": None,
            "senior_sme_escalation": None,
            "senior_sme_rejection_count": 0,
            "senior_sme_continuous_escalation_count": 0,
            "senior_sme_total_escalation_count": total_escalation_count,
            "stored_files_info": stored_files_info_dict,
            "route": route,
            "last_agent": "senior_sme"
        }

    new_rejection_count = rejection_count + 1

    if new_rejection_count >= ESCALATION_THRESHOLD:
        difficulty = response.difficulty_summary or response.concern or "Repeated verification failures on this claim."
        suggestion = response.suggestion_for_planner or "Consider asking the user directly or reconsidering the approach."
        senior_sme_message = f"""
        MESSAGE FROM SENIOR SME TO FEA PLANNER:
        Verdict: Rejected
        This is an escalation message. I'm stating the difficulty we are facing and my suggestion to solve the problem here below

        Difficulty Summary:
        {difficulty}

        Suggestion:
        {suggestion}
        """
        route = "route_to_fea_planner"

        return {
            "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=senior_sme_message, name = "senior_sme")],
            "sme_dispatch_events_senior_sme_only": dispatch_messages_senior_sme_only + [AIMessage(content=senior_sme_message, name = "senior_sme")],
            "sme_dispatch_events_sme_only": (state.get("sme_dispatch_events_sme_only") or []) + [AIMessage(content=senior_sme_message, name = "senior_sme")],
            "senior_sme_verdict": None,
            "senior_sme_escalation": senior_sme_message,
            "senior_sme_rejection_count": 0,
            "senior_sme_continuous_escalation_count": continuous_escalation_count + 1,
            "senior_sme_total_escalation_count": total_escalation_count + 1,
            "stored_files_info": stored_files_info_dict,
            "route": route,
            "last_agent": "senior_sme"
        }

    senior_sme_message = f"""
    MESSAGE FROM SENIOR SME TO SME:
    Verdict: Rejected
    {response.message_to_sme}
    concern:
    {response.concern}
    """
    route = "route_to_sme"

    return {
        "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=senior_sme_message, name = "senior_sme")],
        "sme_dispatch_events_senior_sme_only": dispatch_messages_senior_sme_only + [AIMessage(content=senior_sme_message, name = "senior_sme")],
        "sme_dispatch_events_sme_only": (state.get("sme_dispatch_events_sme_only") or []) + [AIMessage(content=senior_sme_message, name = "senior_sme")],
        "senior_sme_verdict": response.verdict,
        "senior_sme_escalation": None,
        "senior_sme_rejection_count": new_rejection_count,
        "senior_sme_continuous_escalation_count": continuous_escalation_count,
        "senior_sme_total_escalation_count": total_escalation_count,
        "stored_files_info": stored_files_info_dict,
        "route": route,
        "last_agent": "senior_sme"
    }



def consultant_agent(state: "State") -> dict:
    writer = get_stream_writer()

    dispatch_messages = list(state.get("consultant_dispatch_events") or [])
    stored_files_info_dict = state.get("stored_files_info") or {}
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, "stored_files_info/stored_files_info.json")


    updated_files = (state.get("updated_files_consultant_signal") or [])
    if updated_files:
        notification = f"""
        MESSAGE FROM FEA PLANNER:
        The files {", ".join(updated_files)} may have been updated and changed. 
        It is advisable to use your tools again if and only if you need the latest information regarding {", ".join(updated_files)}
        """
        dispatch_messages.append(HumanMessage(content=notification))


    if stored_files_info_dict:
        stored_files_info = json.dumps(stored_files_info_dict, indent=4)
    else:
        stored_files_info = "(storage is empty)"


    context = f"""
    STORED_FILES_INFO:
    {stored_files_info} 
    """

    system_message = SystemMessage(content=CONSULTANT_SYSTEM_PROMPT)
    human_message = HumanMessage(content=context)
    loop_messages = [system_message] + dispatch_messages + [human_message] 


    FINALIZE_INSTRUCTION = (
        "You have gathered whatever information you're going to gather. Now produce your final "
        "ConsultantDecision"
    )

    MAX_TOOL_ITERATIONS = 5
    for _ in range(MAX_TOOL_ITERATIONS):
        ai_tool_msg = consultant_llm_with_tools.invoke(loop_messages)

        if not ai_tool_msg.tool_calls:
            break

        strip_draft_prose(ai_tool_msg)
        loop_messages.append(ai_tool_msg)
        dispatch_messages.append(ai_tool_msg)

        for call in ai_tool_msg.tool_calls:
            tool_fn = {
                "read_parsed_file_info": read_parsed_file_info,
                "capture_abaqus_model_screenshot": capture_abaqus_model_screenshot,
                "capture_abaqus_odb_screenshot": capture_abaqus_odb_screenshot,
                "scripting_rag_tool": scripting_rag_tool,
                "procedural_rag_tool": procedural_rag_tool
            }[call["name"]]

            try:
                tool_result = tool_fn.invoke(call["args"])
            except Exception as tool_exc:
                error_message = tool_error_message(call, tool_exc)
                loop_messages.append(error_message)
                dispatch_messages.append(error_message)
                continue

            if call["name"] == "capture_abaqus_model_screenshot" or call["name"] == "capture_abaqus_odb_screenshot":
                b64_image = tool_result["b64_image"]
                image_file_info = tool_result["image_file_info"]
                text_summary = tool_result["text"]

                tool_message = ToolMessage(
                    content=[
                        {
                            "type": "text", 
                            "text": text_summary
                        },
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"}
                        }
                    ],
                    tool_call_id=call["id"], 
                    name=call["name"],
                    artifact=call["args"]
                )

                stored_files_info_dict["tool_generated_files"][image_file_info["file_name"]] = image_file_info
                with open(stored_files_info_json_path, "w") as f:
                    json.dump(stored_files_info_dict, f, indent=4, default=str)            
            else:
                tool_message = ToolMessage(content=str(tool_result), tool_call_id=call["id"], name=call["name"])

            loop_messages.append(tool_message)
            dispatch_messages.append(tool_message)


    response: ConsultantDecision = consultant_llm.invoke(
        loop_messages + [HumanMessage(content=FINALIZE_INSTRUCTION)]
    )
    writer({"status": response.status_update})
    response.files_consulted = extract_files_consulted(loop_messages)

    consultant_trace = f"""
    ------------------------------Consultant Agent------------------------------
    status_update: "{response.status_update}"

    reasoning:
    {response.reasoning}

    evidence:
    {response.evidence}

    message_to_planner:
    {response.message_to_planner}

    files_consulted: {', '.join(response.files_consulted) if response.files_consulted else 'none'}
    """
    logger.info(consultant_trace)

    consultant_message = f"""
    MESSAGE FROM CONSULTANT TO FEA PLANNER:
    {response.message_to_planner}
    """

    return {
        "consultant_dispatch_events": dispatch_messages + [AIMessage(content=consultant_message, name = "consultant")],
        "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=consultant_message, name = "consultant")],
        "consultant_response": response,
        "updated_files_consultant_signal": [],
        "stored_files_info": stored_files_info_dict,
        "last_agent": "consultant"
    }



    

def interface_agent(state:State):
    interface_data = state.get("fea_planner_response").message_to_interface_agent if state.get("fea_planner_response") else None
    interface_widget_data = {}
    params_requiring_input = []
    all_params = []
    task_id = str(uuid.uuid4())

    if interface_data:
        malformed_widgets = []

        for widget_spec in interface_data:
            param = widget_spec.name

            try:
                widget_kwargs = json.loads(widget_spec.kwargs_json)
                if not isinstance(widget_kwargs, dict):
                    raise ValueError(f"kwargs_json must decode to an object, got {type(widget_kwargs).__name__}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"interface_agent: could not parse kwargs_json for '{param}': {e}")
                malformed_widgets.append(param)
                continue

            interface_widget_data[param] = {
                "widget_type": widget_spec.type,
                "widget_kwargs": widget_kwargs
            }
            if widget_spec.direction == "input":
                params_requiring_input.append(param)
            all_params.append(param)

        if malformed_widgets:
            return {
                "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [
                    AIMessage(
                        content=(
                            "\nMESSAGE FROM INTERFACE AGENT TO FEA PLANNER:\n"
                            f"Failed to render interface widgets for parameters: {', '.join(malformed_widgets)}\n"
                            "Error: \n"
                            "kwargs_json was not a valid JSON object string. Re-send this "
                            "dispatch with kwargs_json as a JSON object encoded as a string.\n"
                        ),
                        name="interface_agent",
                    )
                ],
                "last_agent": "interface_agent",
            }

        interface_agent_message_data = interrupt({
            "task": "interface_widget_render", 
            "task_id": task_id,
            "data": {
                "interface_widget_data": interface_widget_data,
                "params_requiring_input": params_requiring_input,
            }
        })

        if params_requiring_input:
            if interface_agent_message_data.get("status") == "success":
                interface_agent_message = f"""
                MESSAGE FROM INTERFACE AGENT TO FEA PLANNER:
                Successfully rendered interface widgets for parameters: {', '.join(all_params)}
                
                Input given from the user:
                {json.dumps(interface_agent_message_data.get("user_input", {}), indent=4)}
            """
            else:
                interface_agent_message = f"""
                MESSAGE FROM INTERFACE AGENT TO FEA PLANNER:
                Failed to render interface widgets for parameters: {', '.join(all_params)}
                Error: 
                {interface_agent_message_data.get("error", "Unknown error")}
                """
                                            
        else:
            if interface_agent_message_data.get("status") == "success":
                interface_agent_message = f"""
                MESSAGE FROM INTERFACE AGENT TO FEA PLANNER:
                Successfully rendered interface widgets for parameters: {', '.join(all_params)}
                """
            else:
                interface_agent_message = f"""
                MESSAGE FROM INTERFACE AGENT TO FEA PLANNER:
                Failed to render interface widgets for parameters: {', '.join(all_params)}
                Error: 
                {interface_agent_message_data.get("error", "Unknown error")}
                """

        user_input_dict = interface_agent_message_data.get("user_input") or {}

        return {
            "messages": [
                HumanMessage(content="\n".join(f"{str(param)}: {str(value)}" for param, value in user_input_dict.items()))
            ] if params_requiring_input else [],
            "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=interface_agent_message, name="interface_agent")],
            "last_agent": "interface_agent"
        }

    else:
        logger.error("No interface data (fea_planner_response.message_to_interface_agent) found in state")
        return {
            "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content="No interface data recieved to render in the UI", name="interface_agent")],
        }




def coding_agent(state:State):
    writer = get_stream_writer()
    reset = False
    coding_conversation = list(state.get("coding_dispatch_events") or [])
    stored_files_info_dict = state.get("stored_files_info") or {}
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, "stored_files_info/stored_files_info.json")

    working_directory = state.get("working_directory")
    if not working_directory:
        logger.error("coding_agent_node: working_directory is missing from state -- this must be passed in at invocation time.")
        working_directory = "(WORKING_DIRECTORY NOT PROVIDED -- DO NOT WRITE ANY FILES)"
    
    if stored_files_info_dict:
        stored_files_info = json.dumps(stored_files_info_dict, indent=4)
    else:
        stored_files_info = "(storage is empty)"

    coding_plan = state.get("coding_agent_plan") or []
    submitted_code = state.get("submitted_code") or "N/A"

    stdout = state.get("execution_stdout") or "N/A"
    stderr = state.get("execution_stderr") or "N/A"
    execution_agent_verdict = state.get("execution_agent_verdict") or "N/A"

    context = f"""
    WORKING_DIRECTORY:
    {working_directory}

    STORED_FILES_INFO:
    {stored_files_info}

    PLAN:
    {coding_plan}

    EXECUTION AGENT VERDICT:
    {execution_agent_verdict}

    SUBMITTED_CODE:
    {submitted_code}

    EXECUTION_STDOUT:
    {stdout}

    EXECUTION_STDERR:
    {stderr}
    """
    
    system_message = SystemMessage(content=CODING_AGENT_SYSTEM_PROMPT)
    human_message = HumanMessage(content=context)
    loop_messages = [system_message] + coding_conversation + [human_message] 

    FINALIZE_INSTRUCTION = (
        "You have gathered whatever information you're going to gather. Now produce your final "
        "CodingAgentDecision"
    )

    MAX_TOOL_ITERATIONS = 10
    for _ in range(MAX_TOOL_ITERATIONS):
        ai_tool_msg = coding_agent_llm_with_tools.invoke(loop_messages)

        if not ai_tool_msg.tool_calls:
            break

        strip_draft_prose(ai_tool_msg)
        loop_messages.append(ai_tool_msg)
        coding_conversation.append(ai_tool_msg)
        for call in ai_tool_msg.tool_calls:
            tool_fn = {
                "read_parsed_file_info": read_parsed_file_info,
                "capture_abaqus_model_screenshot": capture_abaqus_model_screenshot,
                "capture_abaqus_odb_screenshot": capture_abaqus_odb_screenshot,
                "scripting_rag_tool": scripting_rag_tool,
                "syntax_check_tool": syntax_check_tool,
            }[call["name"]]

            try:
                tool_result = tool_fn.invoke(call["args"])
            except Exception as tool_exc:
                error_message = tool_error_message(call, tool_exc)
                loop_messages.append(error_message)
                coding_conversation.append(error_message)
                continue

            if call["name"] == "capture_abaqus_model_screenshot" or call["name"] == "capture_abaqus_odb_screenshot":
                b64_image = tool_result["b64_image"]
                image_file_info = tool_result["image_file_info"]
                text_summary = tool_result["text"]

                tool_message = ToolMessage(
                    content=[
                        {
                            "type": "text", 
                            "text": text_summary
                        },
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"}
                        }
                    ],
                    tool_call_id=call["id"], 
                    name=call["name"],
                    artifact=call["args"]
                )
                stored_files_info_dict["tool_generated_files"][image_file_info["file_name"]] = image_file_info
                with open(stored_files_info_json_path, "w") as f:
                    json.dump(stored_files_info_dict, f, indent=4, default=str)
            else:
                tool_message = ToolMessage(content=str(tool_result), tool_call_id=call["id"], name=call["name"], artifact = call["args"])
            loop_messages.append(tool_message)
            coding_conversation.append(tool_message)


    response: CodingAgentDecision = coding_agent_llm.invoke(
        loop_messages + [HumanMessage(content=FINALIZE_INSTRUCTION)]
    )


    if response.next_action == "report_to_planner" and execution_agent_verdict != "Approved":
        logger.warning(
            "Coding Agent claimed success with execution_agent_verdict=%r -- re-asking.",
            execution_agent_verdict,
        )
        correction = HumanMessage(content=(
            "STOP. You selected next_action = 'report_to_planner', but Execution Agent has "
            f"NOT reported a successful run for this dispatch (EXECUTION AGENT VERDICT is "
            f"'{execution_agent_verdict}'). Nothing you have written has been executed yet. "
            "'report_to_planner' is valid ONLY on the turn immediately after you have seen "
            "Execution Agent report a clean success. Re-issue your CodingAgentDecision now: "
            "if you have a script ready, choose 'ready_to_run' and put the full script in "
            "`code`. If you genuinely need something from Planner before you can proceed, "
            "choose 'ask_fea_planner'. Do not report work that has not been executed."
        ))
        response = coding_agent_llm.invoke(loop_messages + [correction])


        if response.next_action == "report_to_planner" or (
            response.next_action == "ready_to_run" and not (response.code or "").strip()
        ):
            logger.error(
                "Coding Agent would not produce a runnable decision (next_action=%r, "
                "code_present=%s) -- forcing ask_fea_planner.",
                response.next_action, bool((response.code or "").strip()),
            )
            response.next_action = "ask_fea_planner"
            response.message_to_fea_planner = (
                "I was unable to produce a runnable script for this step. Nothing has been "
                "executed and no files were produced, so this step is NOT complete. Please "
                "re-dispatch with clarified requirements, or route this to Consultant for a "
                "different approach."
            )
            response.final_success_message = ""


    writer({"status": response.status_update})
    response.files_consulted = extract_files_consulted(loop_messages)
    formatted_new_plan = format_coding_plan(response.plan)


    context_message = format_message_for_logging(loop_messages)
    logger.info(f"""
    ------------------------------Coding Agent------------------------------
    ==============================
    Context Recieved:
    {context_message}
    ==============================

    next_action: {response.next_action}
    status_update: "{response.status_update}"
    reasoning: {response.reasoning}

    plan:
    {formatted_new_plan}

    message_to_conversation: 
    {response.message_to_conversation or 'none'}

    message_to_fea_planner: 
    {response.message_to_fea_planner or 'none'}

    final_success_message: 
    {response.final_success_message or 'none'}

    files_consulted: {response.files_consulted}
    """)


    if response.next_action == "ready_to_run":
        coding_agent_message = f"""
        MESSAGE FROM CODING AGENT TO EXECUTION AGENT
        {response.message_to_conversation}
        """
        route = "route_to_execution_agent"

    elif response.next_action == "ask_fea_planner":
        coding_agent_message = f"""
        MESSAGE FROM CODING AGENT TO FEA PLANNER
        {response.message_to_fea_planner}
        """
        route = "route_to_fea_planner"

    elif response.next_action == "report_to_planner":
        coding_agent_message = f"""
        MESSAGE FROM CODING AGENT TO FEA PLANNER
        {response.final_success_message}

        Files Produced: {state.get("files_produced_by_script") or "No files produced"} 
        """
        route = "route_to_fea_planner"
        reset = True
    
    return {
        "coding_agent_response": response,
        "coding_agent_plan": [] if reset else response.plan,
        "coding_dispatch_events": [] if reset else (coding_conversation + [AIMessage(content=coding_agent_message, name="coding_agent")]),
        "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + [AIMessage(content=coding_agent_message, name="coding_agent")],
        "submitted_code":  None if reset else response.code,
        "execution_agent_verdict": None if reset else (state.get("execution_agent_verdict") or "N/A"),
        "files_produced_by_script": None if reset else state.get("files_produced_by_script"),
        "stored_files_info": stored_files_info_dict,
        "route": route,
        "last_agent": "coding_agent",
    }


def execution_agent(state:State):
    writer = get_stream_writer()
    reset = False
    working_directory = state.get("working_directory")
    code_to_run = state.get("submitted_code")
    stored_files_info = state.get("stored_files_info") or {}
    stored_files_info_json_path = os.path.join(SIMULATION_ARTIFACTS_DIR, "stored_files_info/stored_files_info.json")

    before_runtime = time.time()
    files_before_runtime = get_present_files(directory = working_directory)

    result = run_abaqus_script(rendered_code = code_to_run)
    stdout = result.stdout
    stderr = result.stderr
    success = result.returncode == 0 and ("Abaqus Error: cae exited with an error." not in stdout)

    files_produced_dict = {}
    files_produced = detect_files_produced_and_modified(directory=working_directory, cutoff_time=before_runtime)
    files_produced_basenames = [os.path.basename(file_produced) for file_produced in files_produced]
    for i in range(len(files_produced_basenames)):
        files_produced_dict[files_produced_basenames[i]] = {"file_address" : files_produced[i]}

    updated_files = detect_updated_files(files_in_dir_before_list= files_before_runtime, files_produced_list= files_produced)
    updated_files_basenames = [os.path.basename(updated_file) for updated_file in updated_files]
    
    execution_agent_file_update_message = None
    new_files_produced = list(set(files_produced) - set(updated_files))


    if updated_files:
        for file in updated_files:
            dict_key = os.path.basename(file)

            if dict_key in stored_files_info["app_generated_files"]:
                del stored_files_info["app_generated_files"][dict_key]

            parsed_file_info = parse_file(file)
            stored_files_info["app_generated_files"][dict_key] = parsed_file_info

            with open(stored_files_info_json_path, "w") as f:
                json.dump(stored_files_info, f, indent=4, default=str)

        execution_agent_file_update_message = f"""
        MESSAGE FROM EXECUTION AGENT TO FEA PLANNER AND CODING AGENT:
        The files {", ".join(updated_files_basenames)} may have been updated and changed. 
        It is advisable to use your tools again(if applicable) if and only if you need the latest information regarding {", ".join(updated_files_basenames)}
        """
        new_files_produced = list(set(files_produced) - set(updated_files))

    coding_dispatch_events = state.get("coding_dispatch_events") or []
    coding_continuous_error_count = (state.get("coding_continuous_error_count") or 0)
    coding_continuous_escalation_count = (state.get("coding_continuous_escalation_count") or 0)


    if success:
        for file in new_files_produced:
            dict_key = os.path.basename(file)

            if dict_key in stored_files_info["app_generated_files"]:
                del stored_files_info["app_generated_files"][dict_key]

            parsed_file_info = parse_file(file)
            stored_files_info["app_generated_files"][dict_key] = parsed_file_info

            with open(stored_files_info_json_path, "w") as f:
                json.dump(stored_files_info, f, indent=4, default=str)

        execution_agent_message = f"""
        MESSAGE FROM EXECUTION AGENT TO CODING AGENT
        The code ran successfully without any errors

        Files produced by the code:
        {files_produced_dict}
        """ 
        coding_continuous_error_count = 0
        coding_continuous_escalation_count = 0
        route = "route_to_coding_agent"
        verdict = "Approved"

    else:
        system_message = SystemMessage(content = EXECUTION_AGENT_SYSTEM_PROMPT)
        coding_continuous_error_count += 1
        if success == False and coding_continuous_error_count < 5:
            context = f"""
            EXECUTION_CONSECUTIVE_ERROR_COUNT: {coding_continuous_error_count}
    
            WORKING_DIRECTORY (This is where the code should produce all the files): {working_directory}

            CODE:
            {code_to_run} 

            STDOUT:
            {stdout}

            STDERR:
            {stderr}

            The error count is less than 5 so DO NOT give an escalation message to the fea planner. 
            Diagnose the error and give your guidance to the coding agent. 
            """

            response: ExecutionDiagnosis = execution_agent_llm.invoke([system_message] + [HumanMessage(content = context)])
            writer({"status": response.status_update})

            execution_agent_message = f"""
            MESSAGE FROM EXECUTION AGENT TO CODING AGENT:
            The code did NOT run successfully and resulted in an ERROR.
            Here below I am attaching my diagnosis and guidance:

            Diagnosis and Guidance:
            {response.diagnosis}

            {response.message_to_coding_agent}
            """
            route = "route_to_coding_agent"
            verdict = "Rejected"
        
        elif success == False and coding_continuous_error_count >= 5:
            context = f"""
            EXECUTION_CONSECUTIVE_ERROR_COUNT: {coding_continuous_error_count}
    
            WORKING_DIRECTORY(This is where the code should produce all the files): {working_directory}
    
            CODE:
            {code_to_run}

            STDOUT:
            {stdout}

            STDERR:
            {stderr}

            The error count is more than 5 so give an escalation message to the fea planner. 
            """

            response: ExecutionDiagnosis = execution_agent_llm.invoke([system_message] + coding_dispatch_events + [HumanMessage(content = context)])
            writer({"status": response.status_update})
            
            execution_agent_message = f"""
            MESSAGE FROM EXECUTION AGENT TO FEA PLANNER:
            Difficulty Summary:
            {response.difficulty_summary}
            
            Suggestion:
            {response.suggestion_for_planner}

            Code Last Ran:
            {code_to_run}
            
            Stdout:
            {stdout}

            Stderr:
            {stderr}
            """
            coding_continuous_error_count = 0
            coding_continuous_escalation_count += 1
            route = "route_to_fea_planner"
            verdict = "N/A"
            reset = True

        execution_agent_cleanup_message = None
        if new_files_produced:
            deleted_files = delete_files(file_address_list= new_files_produced)
            execution_agent_cleanup_message = f"""\n
            NOTE: The script failed during execution. To keep the workspace clean, all temporary or intermediate files created during the run have been removed. 
            Deleted intermediate files created during the run (no longer in storage): 
            {", ".join(deleted_files)}
            """ 

        if execution_agent_cleanup_message:
            execution_agent_message = execution_agent_message + execution_agent_cleanup_message

    return {
        "coding_dispatch_events": [] if reset else (coding_dispatch_events + ([AIMessage(content= execution_agent_file_update_message, name="execution_agent")] if execution_agent_file_update_message else []) + [AIMessage(content = execution_agent_message, name = "execution_agent")]),
        "fea_planner_conversations": (state.get("fea_planner_conversations") or []) + ([AIMessage(content= execution_agent_file_update_message, name="execution_agent")] if execution_agent_file_update_message else []) + [AIMessage(content = execution_agent_message, name = "execution_agent")],
        "execution_agent_verdict": verdict,
        "execution_stdout": None if reset else stdout,
        "execution_stderr": None if reset else stderr,
        "submitted_code": None if reset else code_to_run,
        "coding_agent_plan": [] if reset else state.get("coding_agent_plan"),
        "coding_continuous_escalation_count": coding_continuous_escalation_count,
        "coding_continuous_error_count": coding_continuous_error_count,
        "updated_files_sme_signal": updated_files_basenames if updated_files_basenames else [],
        "updated_files_consultant_signal": updated_files_basenames if updated_files_basenames else [],
        "stored_files_info": stored_files_info,
        "files_produced_by_script": files_produced_dict if verdict == "Approved" else {},
        "route": route,
        "last_agent": "execution_agent",
    }

    
            

            

        




