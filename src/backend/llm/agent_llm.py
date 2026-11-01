from src.backend.state.state import (
    FileRelevanceVerdict,
    FEAPlannerDecision,
    SMEDecision,
    SeniorSMEVerdict,
    ConsultantDecision,
    CodingAgentDecision,
    ExecutionDiagnosis
)
from src.backend.tools.tools import (
    read_parsed_file_info,
    capture_abaqus_model_screenshot,
    capture_abaqus_odb_screenshot,
    scripting_rag_tool,
    procedural_rag_tool,
    syntax_check_tool,
)
from src.backend.llm.llm import *
# from src.backend.llm.azure_llm import *
# from src.backend.llm.azure_llm_reasoning import *



file_relevance_checker_llm = get_file_relevance_checker_llm().with_structured_output(FileRelevanceVerdict)


fea_planner_base = get_fea_planner_llm()
fea_planner_llm = fea_planner_base.with_structured_output(FEAPlannerDecision)
fea_planner_llm_with_tools = fea_planner_base.bind_tools([
    read_parsed_file_info, 
    procedural_rag_tool, 
    capture_abaqus_model_screenshot, 
    capture_abaqus_odb_screenshot
])


sme_base = get_sme_llm()
sme_llm = sme_base.with_structured_output(SMEDecision)
sme_llm_with_tools = sme_base.bind_tools([
    read_parsed_file_info, 
    capture_abaqus_model_screenshot, 
    capture_abaqus_odb_screenshot
])


senior_sme_base = get_senior_sme_llm()
senior_sme_llm = senior_sme_base.with_structured_output(SeniorSMEVerdict)
senior_sme_llm_with_tools = senior_sme_base.bind_tools([
    read_parsed_file_info, 
    capture_abaqus_model_screenshot, 
    capture_abaqus_odb_screenshot
])


consultant_base = get_consultant_llm()
consultant_llm = consultant_base.with_structured_output(ConsultantDecision)
consultant_llm_with_tools = consultant_base.bind_tools([
    read_parsed_file_info, 
    scripting_rag_tool, 
    procedural_rag_tool, 
    capture_abaqus_model_screenshot, 
    capture_abaqus_odb_screenshot
])


coding_agent_base = get_coding_agent_llm()
coding_agent_llm = coding_agent_base.with_structured_output(CodingAgentDecision)
coding_agent_llm_with_tools = coding_agent_base.bind_tools([
    read_parsed_file_info, 
    scripting_rag_tool, 
    syntax_check_tool, 
    capture_abaqus_model_screenshot, 
    capture_abaqus_odb_screenshot
])


execution_agent_llm = get_execution_agent_llm().with_structured_output(ExecutionDiagnosis)