import re

from typing import Optional, List, Annotated, TypedDict, Literal, Dict, Any, Tuple
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, field_validator


# Abaqus's session.graphicsOptions accepts ONLY '#RRGGBB' -- a colour name such
# as 'WHITE' raises ColorError. That error surfaces at the very last styling
# step of the render, i.e. after a CAE licence has been checked out and the
# model imported, meshed and drawn. Catching it here costs microseconds and
# hands the model a retryable validation error instead.
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

_NAMED_COLORS = {
    "WHITE": "#FFFFFF", "BLACK": "#000000", "GREY": "#808080", "GRAY": "#808080",
    "LIGHTGREY": "#D3D3D3", "LIGHTGRAY": "#D3D3D3",
    "DARKGREY": "#404040", "DARKGRAY": "#404040",
    "RED": "#FF0000", "GREEN": "#008000", "BLUE": "#0000FF",
    "YELLOW": "#FFFF00", "CYAN": "#00FFFF", "MAGENTA": "#FF00FF",
    "ORANGE": "#FFA500", "NAVY": "#000080",
}


def _normalise_background_color(value: Optional[str]) -> Optional[str]:
    """Accept '#RRGGBB' as-is; coerce a known colour name to hex; reject the rest."""
    if value is None:
        return None
    candidate = value.strip()
    if _HEX_COLOR_RE.match(candidate):
        return candidate.upper()
    named = _NAMED_COLORS.get(candidate.upper().replace(" ", "").replace("_", ""))
    if named:
        return named
    raise ValueError(
        f"background_color must be a hex string like '#FFFFFF' -- Abaqus rejects "
        f"colour names. Got {value!r}."
    )



class FileRelevanceVerdict(BaseModel): 
    reasoning: List[str] = Field(
        ..., description="2-7 short ordered steps: (a) what TASK_IDENTIFIED and MESSAGE_FROM_FEA_PLANNER "
                          "say you need to check; (b) what's in STORED_FILE_NAMES; (c) whether an upload was "
                          "just requested in CONVERSATION_HISTORY and, if so, whether the newest confirmed "
                          "upload matches it; (d) whether more files beyond what's present are likely needed, "
                          "and your confidence. Each step under ~30 words."
    )
 
    evidence: List[str] = Field(
        ..., description="1-5 concrete observations: specific stored file names/extensions, the specific "
                          "wording of MESSAGE_FROM_FEA_PLANNER you're responding to, specific upload-request/ "
                          "confirmation lines from CONVERSATION_HISTORY, and task-language cues bearing on "
                          "file count. No vague filler."
    )
 
    verdict: Literal[
        "relevant_file_present",
        "partially_sufficient",
        "no_relevant_file",
        "ambiguous",
        "wrong_file_uploaded",
    ] = Field(
        ..., description="The core finding about what's currently in storage. 'wrong_file_uploaded' takes "
                          "priority whenever you find an upload request in history followed by a confirmed "
                          "upload that doesn't match the type requested."
    )
 
    relevant_file_names: List[str] = Field(
        default_factory=list,
        description="Stored file name(s) judged relevant -- verbatim from a file name found within "
                     "STORED_FILES_INFO, never invented. May include multiple names for multi-file tasks. "
                     "Empty for 'no_relevant_file' or 'wrong_file_uploaded'.",
    )
 
    expected_file_type: Optional[str] = Field(
        default=None,
        description="For 'wrong_file_uploaded', 'no_relevant_file', or 'partially_sufficient': the file type "
                     "still needed. None otherwise.",
    )
 
    uploaded_file_type: Optional[str] = Field(
        default=None,
        description="For 'wrong_file_uploaded': the type the user actually uploaded, per the most recent "
                     "upload-confirmation message in CONVERSATION_HISTORY. None otherwise.",
    )
 
    additional_files_likely_needed: Literal["yes", "no", "uncertain"] = Field(
        ..., description="Whether, BEYOND relevant_file_names, the task likely requires further files not "
                          "currently in storage. Your own inference, not a guaranteed fact. Default to "
                          "'uncertain' whenever the task doesn't explicitly specify a count or name the "
                          "file(s) needed."
    )
 
    additional_files_reasoning: str = Field(
        default="", description="Brief explanation for additional_files_likely_needed. Empty string only if "
                                 "'no' with nothing further to add."
    )
 
    message_to_fea_planner: str = Field(
        ..., description="A concise, plain-language verdict for the FEA Planner. If MESSAGE_FROM_FEA_PLANNER "
                          "was empty (an automatic post-upload check), lead with what just happened and whether "
                          "it satisfies the full requirement -- e.g. 'One of the two requested odb files (e2.odb) "
                          "has now been uploaded; one more is still needed.' If it was populated, answer it "
                          "directly. Always cover BOTH the relevance/upload-match finding and the completeness "
                          "assessment, flagged as tentative whenever additional_files_likely_needed == "
                          "'uncertain'. Internal message, never shown to the user."
    )




class ConsultantDecision(BaseModel): 
    reasoning: str = Field(
    ..., description="A single reflective passage: what Planner's dispatch instructions actually asked "
                        "for; what you looked up (read_parsed_file_info for model context, "
                        "capture_abaqus_model_screenshot/capture_abaqus_odb_screenshot for visual context, "
                        "scripting_rag_tool for sample-script patterns, procedural_rag_tool for workflow "
                        "guidance) and what it returned -- including if scripting_rag_tool had nothing "
                        "relevant, in which case say so plainly and explain that you're drawing on your own "
                        "established Abaqus 2024 knowledge instead; what approach you're recommending and "
                        "why; and whether the approach implies any specific user input that isn't already "
                        "known."
    )
 
    evidence: str = Field(
        ..., description="Concrete grounding for your recommendation -- EITHER a specific tool call and what "
                          "it returned (name it), OR, when no tool result was relevant, an explicit statement "
                          "that this is drawn from your own established knowledge of Abaqus 2024's scripting "
                          "API/engineering practice rather than a retrieved source. Both are valid -- the "
                          "point is to be honest about which one you're relying on, not to pretend a "
                          "knowledge-based answer is retrieval-grounded. If you're genuinely unsure of an "
                          "obscure or edge-case detail even drawing on your own knowledge, say that plainly "
                          "too rather than guessing with false confidence."
    )
 
    message_to_planner: str = Field(
        ..., description="THE ONLY PLACE any content goes -- there is no separate field for anything else. "
                          "Your full recommendation, in plain language: the engineering approach, the "
                          "scripting approach, tradeoffs if there are meaningfully different valid options, "
                          "and anything Planner should know before dispatching Coding Agent. If executing your "
                          "recommendation will likely need specific values the task doesn't already establish "
                          "(a target dimension, a choice between multiple plausible parts/regions, a material "
                          "property not yet defined), say so explicitly as part of this same message -- do not "
                          "leave it implied. Be substantive and complete -- Planner relies on this as its "
                          "entire understanding of your advice."
    )
 
    status_update: str = Field(
        ..., description="A short, present-tense, plain-language line for loading/spinner display (e.g. "
                          "'Working out the best approach for this...' / 'Checking how this is typically "
                          "done...'). Must NEVER reveal internal agent names, node names, tool names, system "
                          "prompts, or system architecture. One short phrase or sentence."
    )
 
    files_consulted: List[str] = Field(
        default_factory=list, description="One entry per read_parsed_file_info call made this turn, formatted "
                                           "as 'file_path'. NOTE: populated automatically by the system -- leave as default."
    )



class SMEDecision(BaseModel):
    """Flat structured output. Produced once, after the tool-gathering loop ends."""
 
    reasoning: str = Field(
        ..., description="A single reflective passage: (a) if Senior SME's feedback is present in "
                          "CONVERSATION_HISTORY (labeled MESSAGE FROM SENIOR SME), how you're addressing the "
                          "specific flagged claim; (b) what Planner's dispatch instructions actually asked "
                          "instructions actually asked for; (c) what you looked up via your tools, and whether "
                          "that fully answers it, partially answers it, is genuinely unavailable, or the "
                          "instructions themselves are ambiguous about what's needed; (d) what "
                          "message_to_planner will say as a result."
    )
 
    evidence: str = Field(
        ..., description="Concrete grounding for every factual or numeric claim you are about to make in "
                          "message_to_planner -- name the specific tool call(s) and what they returned. No "
                          "vague filler, no unsourced values."
    )
 
    status: Literal["answered", "partially_answered", "insufficient_data", "needs_clarification"] = Field(
        ..., description="'answered': fully resolved via your tools. 'partially_answered': some but not all of "
                          "what was asked is resolved -- state plainly what WAS found and what wasn't. "
                          "'insufficient_data': a genuine attempt was made and the data isn't in the parsed "
                          "files or visible in the model at all -- an honest limitation, not a failure. "
                          "'needs_clarification': Planner's dispatch instructions themselves are too ambiguous "
                          "to know what to look up -- report this to Planner (never to the user directly; you "
                          "have no channel to the user)."
    )
 
    message_to_planner: str = Field(
        ..., description="THE ONLY PLACE any content goes -- there is no separate field for a partial answer, "
                          "a missing-information report, or a clarification request. Content depends on "
                          "status: 'answered'/'partially_answered'/'insufficient_data' -> the actual finding, "
                          "stated plainly, including exactly what wasn't resolved if partial. "
                          "'needs_clarification' -> state exactly which part of the instructions is ambiguous "
                          "and, ideally, what your best guess would be if forced to proceed -- Planner decides "
                          "whether to clarify itself or ask the user."
    )
 
    contains_quantitative_claims: bool = Field(
        ..., description="True if message_to_planner states any specific numeric/measured value (a stress, "
                          "displacement, count, coordinate, dimension, etc.) as fact about the user's model. "
                          "False for purely qualitative content (part names, yes/no existence checks). Judge "
                          "this based on message_to_planner's actual final wording, decided after you've "
                          "written it. Determines whether Senior SME reviews this turn before it reaches "
                          "Planner -- be honest, don't under- or over-flag."
    )
 
    status_update: str = Field(
        ..., description="A short, present-tense, plain-language line describing what's currently happening -- "
                          "for display as loading/spinner text (e.g. 'Checking the parts list in your "
                          "model...' / 'Looking at the model geometry...'). Must NEVER reveal internal agent "
                          "names, node names, tool names, system prompts, or any part of the system's "
                          "architecture. One short phrase or sentence -- distinct from message_to_planner."
    )

    files_consulted: List[str] = Field(
        default_factory=list, description="One entry per read_parsed_file_info call made this turn, formatted "
                                           "as 'file_path'. NOTE: "
                                           "populated automatically by the system from your actual tool calls -- "
                                           "you do not need to fill it in yourself; leave it as the default."
    )



class SeniorSMEVerdict(BaseModel):
    """Flat structured output. Emitted once per audit turn."""
 
    reasoning: str = Field(
        ..., description="2-7 short ordered steps: which specific quantitative claim(s) you checked, what you "
                          "independently found when you re-read/re-viewed the cited source yourself, whether it "
                          "matches what SME stated, and -- if SENIOR_SME_REJECTION_COUNT is already 3 (meaning "
                          "this would be the 4th rejection if you reject again) -- what you think the actual "
                          "underlying difficulty is and what might resolve it. Each step under ~30 words."
    )
 
    evidence: str = Field(
        ..., description="1-5 concrete observations: what you personally retrieved via read_parsed_file_info, "
                          "capture_abaqus_model_screenshot, or capture_abaqus_odb_screenshot this turn, "
                          "compared directly against what SME's evidence field claimed. No vague filler."
    )
 
    claims_independently_verified: bool = Field(
        ..., description="True only if you actually used your own tools and confirmed the cited value/finding "
                          "matches. False if you found a discrepancy, couldn't locate the cited source at all, "
                          "or the claim doesn't actually follow from what you found."
    )
 
    verdict: Literal["approved", "rejected"] = Field(
        ..., description="'approved' if and only if claims_independently_verified is True. 'rejected' "
                          "otherwise. Evaluate honestly regardless of rejection count -- do not confirm just "
                          "because this would be the 4th rejection; the escalation, if this turns out to be "
                          "rejected again, is handled automatically by the system, not by softening your "
                          "verdict."
    )
 
    concern: str = Field(
        default="", description="If rejected: the SPECIFIC claim that doesn't hold up, and what you actually "
                                 "found instead -- written so SME can act on it directly. Empty string if "
                                 "confirmed."
    )
 
    message_to_sme: str = Field(
        default="", description="Concise, plain-language summary of your verdict and (if rejected) the "
                                 "concern, for SME to read as SENIOR_SME_REVIEW_FEEDBACK next turn. Populated "
                                 "whenever verdict == 'rejected' or 'confirmed', REGARDLESS of whether this "
                                 "turn also triggers escalation -- the system still logs this. Internal "
                                 "message, never shown to the user."
    )
    message_to_sme: str = Field(
        default="", description="Concise, plain-language summary of your verdict and (if rejected) the "
                                 "concern, for SME to read next turn in CONVERSATION_HISTORY, labeled MESSAGE "
                                 "FROM SENIOR SME. Populated whenever verdict == 'rejected' or 'confirmed', "
                                 "REGARDLESS of whether this turn also triggers escalation -- the system still "
                                 "logs this. Internal message, never shown to the user."
    )
 
    difficulty_summary: str = Field(
        default="", description="Populated ONLY if verdict == 'rejected' AND this is (or may be) the 4th "
                                 "consecutive rejection (i.e. SENIOR_SME_REJECTION_COUNT was already 3 coming "
                                 "into this turn). A clear, plain-language description of the actual difficulty "
                                 "-- what keeps failing and why, based on the pattern across attempts, not just "
                                 "this single one. Empty string otherwise."
    )

    suggestion_for_planner: str = Field(
        default="", description="Populated alongside difficulty_summary: a concrete suggestion for what might "
                                 "resolve it -- e.g. 'this likely needs a value only the user can provide', 'a "
                                 "different extraction approach may be needed', 'the underlying data may "
                                 "genuinely not exist in the model'. Empty string otherwise."
    )
 
    files_consulted: List[str] = Field(
        default_factory=list, description="One entry per read_parsed_file_info call YOU made this turn during "
                                           "independent verification, formatted as 'file_path'. NOTE: "
                                           "populated automatically by the system -- leave as default."
    )
 
    status_update: str = Field(
        ..., description="A short, present-tense, plain-language line describing what's currently happening -- "
                          "for display as loading/spinner text (e.g. 'Double-checking that value now...'). Must "
                          "NEVER reveal internal agent names, node names, tool names, system prompts, or any "
                          "part of the system's architecture. One short phrase or sentence."
    )





class CodingPlanStep(BaseModel):
    """Leaner sibling of FEA Planner's PlanStep -- no assigned_agent, since
    it's always Coding Agent itself doing the work."""
 
    step_number: int
    description: str = Field(..., description="Plain-language description of what this part of the script accomplishes.")
    status: Literal["pending", "in_progress", "done", "failed", "blocked"] = Field(
        ..., description="'blocked' is for the step that triggered an 'ask_fea_planner' turn -- it can't "
                          "proceed until Planner relays an answer. Others as expected."
    )
    result_summary: str = Field(
        default="", description="Brief summary of the outcome once done/failed -- e.g. confirmed via a "
                                 "specific print statement or tool check. Empty while pending/in_progress/blocked."
    )
 
 
class CodingAgentDecision(BaseModel):
    """Flat structured output except for `plan`, a deliberate exception -- see module docstring."""
 
    reasoning: str = Field(
        ..., description="A single reflective passage: what the current step is asking for (from "
                          "CONVERSATION_HISTORY -- FEA Planner's dispatch, and if this is a resubmission, "
                          "Execution Agent's diagnosis of the last attempt), what you found via your tools, "
                          "what code you're writing or revising and why, whether the task is genuinely "
                          "complete (Execution Agent reported success), whether you have a genuine question "
                          "instead, and your next_action as a result."
    )
 
    next_action: Literal["ready_to_run", "report_to_planner", "ask_fea_planner"] = Field(
        ..., description="'ready_to_run': new or revised code is ready -- routes directly to Execution Agent. "
                          "'report_to_planner': you have just seen Execution Agent report a clean success -- "
                          "this turn writes up final_success_message directly. 'ask_fea_planner': you have a "
                          "genuine question about the task itself, OR you need a specific code-level/parameter "
                          "value with no sensible default before you can draft code -- both are normal, "
                          "first-class paths, not something to avoid. Each value maps to EXACTLY ONE populated "
                          "content field -- see REPORTING TO PLANNER."
    )
 
    plan: List[CodingPlanStep] = Field(
        default_factory=list,
        description="Your own internal breakdown of this step into concrete sub-parts -- even a single-step "
                     "plan is fine for a simple script. Populate every turn, regardless of next_action. On "
                     "your FIRST turn for this dispatch, break the task into distinct operations based on "
                     "Planner's instructions. On every later turn, update each step's status based on what's "
                     "ACTUALLY been verified (EXECUTION_STDOUT, Execution Agent's diagnosis, your own review) "
                     "-- never mark a step 'done' on optimism about what should have worked. If next_action == "
                     "'ask_fea_planner', mark whichever step triggered the question as 'blocked'."
    )
 
    code: str = Field(
        default="", description="The full Abaqus Python script, written for ABAQUS 2024 compatibility. "
                                 "Populated IF AND ONLY IF next_action == 'ready_to_run'. Include print "
                                 "statements liberally -- this is your primary debugging signal, since "
                                 "EXECUTION_STDOUT is given back to you directly. Every output MUST be written "
                                 "inside WORKING_DIRECTORY and nowhere else. Empty string otherwise."
    )
 
    message_to_conversation: str = Field(
        default="", description="Populated IF AND ONLY IF next_action == 'ready_to_run'. What goes into the "
                                 "shared conversation with Execution Agent -- restate what you're trying to "
                                 "accomplish plus a brief description of your approach. If this is a "
                                 "resubmission after a diagnosed failure, address the specific cause directly. "
                                 "Empty string otherwise."
    )
 
    message_to_fea_planner: str = Field(
        default="", description="Populated IF AND ONLY IF next_action == 'ask_fea_planner'. This covers TWO "
                                 "distinct cases -- state clearly which one this is: (a) a genuine QUESTION "
                                 "about the task itself, when the requirements are ambiguous or you're unsure "
                                 "what's actually being asked; (b) a CODE-LEVEL OR PARAMETER INPUT REQUEST -- a "
                                 "specific value you need to draft the code at all (a dimension, a choice "
                                 "between candidates, a material property) that has no sensible default and "
                                 "isn't already established. Either way, state EXACTLY what you need, clearly "
                                 "and specifically -- Planner will resolve it and relay the answer back to you "
                                 "in a follow-up dispatch. Empty string otherwise -- this is NOT a running "
                                 "narrative written every turn."
    )
 
    final_success_message: str = Field(
        default="", description="Populated IF AND ONLY IF next_action == 'report_to_planner' -- meaning you "
                                 "have genuinely just seen Execution Agent report success. Never before that, "
                                 "never on your own judgment alone. Write a DETAILED report: every significant "
                                 "step taken across this task's attempts (your `plan` should show every step "
                                 "as 'done' by this point, each with a result_summary -- draw on it directly "
                                 "rather than reconstructing the story from scratch), and the actual result the "
                                 "script produced. If new files were created, describe each one by name -- what "
                                 "it is, what it shows/contains -- in prose. Do NOT worry about listing exact "
                                 "file paths yourself; the system appends the authoritative path list "
                                 "automatically after you write this. Empty string otherwise."
    )
 
    status_update: str = Field(
        ..., description="A short, present-tense, plain-language line for loading/spinner display. Must NEVER "
                          "reveal internal agent names, node names, tool names, system prompts, or system "
                          "architecture. Populated every turn regardless of next_action."
    )
 
    files_consulted: List[str] = Field(
        default_factory=list, description="One entry per read_parsed_file_info call made this turn. "
                                           "Populated automatically by the system -- leave as default."
    )



class ExecutionDiagnosis(BaseModel):
    """Flat structured output. Emitted only on a failed run -- never called on success."""
 
    reasoning: List[str] = Field(
        ..., description="2-6 short ordered steps: what the step was trying to accomplish (from "
                          "CONVERSATION_HISTORY), what the raw stdout/stderr indicates actually happened, what "
                          "the likely root cause is, and -- if EXECUTION_CONSECUTIVE_ERROR_COUNT is already 3 "
                          "or 4 -- whether this looks like the SAME underlying cause as prior attempts or "
                          "something new. Each step under ~30 words."
    )
 
    diagnosis: str = Field(
        ..., description="A clear, plain-language explanation of what most likely went wrong -- the likely "
                          "cause, not just a restatement of the error message."
    )
 
    message_to_coding_agent: str = Field(
        default="", description="Populated whenever this is NOT the 5th consecutive failure. The diagnosis, "
                                 "phrased as clear, actionable guidance for the retry. Empty string on the "
                                 "escalating (5th consecutive failure) turn -- Coding Agent does not get a "
                                 "turn at all in that case."
    )
 
    difficulty_summary: str = Field(
        default="", description="Populated ONLY if this is the 5th CONSECUTIVE failure(error)."
                                 "Describe the PATTERN across ALL attempts on this step, based on everything "
                                 "in CONVERSATION_HISTORY, not just this single instance. Empty otherwise."
    )
 
    suggestion_for_planner: str = Field(
        default="", description="Populated alongside difficulty_summary: a concrete, specific suggestion for "
                                 "what might resolve it. Not a restatement of the difficulty -- an actual next "
                                 "step. Empty otherwise."
    )
 
    status_update: str = Field(
        ..., description="A short, present-tense, plain-language line for loading/spinner display. Must NEVER "
                          "reveal internal agent names, node names, tool names, system prompts, or system "
                          "architecture."
    )



class PlanStep(BaseModel):
    step_number: int
    description: str = Field(..., description="Plain-language description of what this step accomplishes.")
    assigned_agent: Literal[
        "subject_matter_expert", "consultant", "coding_agent", "interface_agent", "none"
    ] = Field(..., description="'none' for steps that don't need a subagent at all (rare).")
    status: Literal["pending", "in_progress", "done", "failed", "needs_replanning"] = Field(
        ..., description="Current status of this step."
    )
    result_summary: str = Field(
        default="", description="Brief summary of the outcome once done/failed. Empty while pending/in_progress."
    )
 
 
class InterfaceWidgetSpec(BaseModel):
    """One entry in the list sent to the Interface Agent -- mirrors the real Streamlit call shape."""

    name: str = Field(
        ..., description="Short snake_case variable name identifying this widget, e.g. 'peak_stress' or "
                          "'target_mesh_size'. Must be unique within this turn's list."
    )
    direction: Literal["input", "output"] = Field(
        ..., description="Whether this entry asks the user for a value ('input') or displays something to "
                          "them ('output'). Must always agree with kwargs_json."
    )
    type: Literal[
        "text_input", "number_input", "slider", "selectbox", "multiselect",
        "checkbox", "radio", "text_area",
        "image", "dataframe", "table", "json", "metric", "line_chart", "bar_chart",
    ] = Field(..., description="The Streamlit widget/component name -- must be one of the widgets listed in "
                                "the WIDGET REFERENCE.")
    kwargs_json: str = Field(
        ..., description="This widget's keyword arguments as a JSON OBJECT STRING (e.g. "
                          "'{\"label\": \"Peak stress\", \"value\": \"245 MPa\"}') -- a string, not an "
                          "object. Use the REAL Streamlit parameter names. For 'input', do NOT include a "
                          "'value' key, and ALWAYS include a 'help' key (a brief description plus one or two "
                          "example inputs). For 'output', put the content in that widget's actual content "
                          "parameter -- 'data' for dataframe/table/line_chart/bar_chart, 'body' for json, "
                          "'image' for image, and 'value' for metric (the ONLY output widget that takes "
                          "'value'). Never include a 'key' on an output widget -- they have no such "
                          "parameter. NEVER include 'help' on an output widget either, with the single "
                          "exception of 'metric' -- the other output widgets have no 'help' parameter and "
                          "will fail to render."
    )
 
 
class FEAPlannerDecision(BaseModel):
    """Flat structured output (plus the plan list)."""
 
    reasoning: str = Field(
        ..., description="A single reflective passage, walked through STRICTLY in this order, skipping "
                          "sections that don't apply given the CURRENT phase you're in: "
                          "(a) if current_phase (from state) is 'identifying_task', is this a real task or "
                          "general chat, and if a task, what is it; "
                          "(b) if current_phase is 'identifying_files' (or you just resolved the task this "
                          "turn), whether the task needs file(s), how MANY/which ones, your own read of "
                          "stored_file_names against that set, and whether/why you are consulting File "
                          "Relevance Checker; "
                          "(c) if current_phase is (or just became) 'planning_and_dispatch': current plan "
                          "state, what came back from whichever subagent reported this turn, whether the plan "
                          "needs revising, which subagent to dispatch next and why, whether any code-level "
                          "input is needed and whether the user already provided it for THIS task; "
                          "(d) your resulting current_phase and next_action."
    )
 
    evidence: str = Field(
        ..., description="A single short paragraph of concrete, auditable observations grounding the "
                          "decision -- specific quotes/paraphrases from CONVERSATION_HISTORY, "
                          "stored_file_names, or a subagent's report. No vague filler."
    )
 
    current_phase: Literal["identifying_task", "identifying_files", "planning_and_dispatch"] = Field(
        ..., description="Which phase you're in AT THE END of this turn's reasoning -- i.e., if you fully "
                          "resolved task+files THIS turn, this is already 'planning_and_dispatch', paired "
                          "with your first real dispatch decision in next_action, same turn."
    )
 
    task_type: Literal["new_task", "follow_up", "general_chat", "still_determining"] = Field(
        ..., description="'general_chat': not a real task at all -- casual conversation, thanks, small talk. "
                          "'new_task': independent of anything prior. 'follow_up': continues, refines, "
                          "corrects, or answers a question about a task/thread already in play. "
                          "'still_determining': cannot yet tell. Only meaningfully re-evaluated when "
                          "current_phase is 'identifying_task' -- otherwise carry forward the already-"
                          "resolved value."
    )
 
    task_identified: str = Field(
        ..., description="Plain-language description of what's actually wanted. If a comparison/multi-file "
                          "task, say so plainly. If not yet resolvable, the exact literal string 'Still "
                          "determining'. If task_type == 'general_chat', the literal string 'N/A -- general "
                          "chat'. Once resolved, restate the same value on later turns for continuity."
    )
 
    files_needed: Literal["yes", "no", "still_determining", "not_applicable"] = Field(
        ..., description="'not_applicable' for general_chat. 'no': the task needs no file. 'yes': needs one "
                          "or more. 'still_determining': task resolved but file-need itself isn't yet."
    )
 
    file_situation: Literal[
        "not_applicable",
        "present_and_relevant",
        "present_unverified",
        "partially_present",
        "missing",
        "wrong_file_uploaded",
        "ambiguous",
        "still_determining",
    ] = Field(
        ..., description="Current best read of the file situation across the FULL required set. "
                          "'present_and_relevant' requires every file the task needs to be accounted for. "
                          "'partially_present' is normal for a comparison-style task where only some needed "
                          "files are uploaded. Once resolved to 'present_and_relevant', restate it forward on "
                          "later planning_and_dispatch turns rather than re-deriving."
    )
 
    relevant_file_names: List[str] = Field(
        default_factory=list,
        description="ALL stored file name(s) confirmed relevant to the task -- may be more than one for "
                     "multi-file tasks. Verbatim from a file name found within STORED_FILES_INFO -- never "
                     "invent.",
    )
 
    additional_files_needed_description: str = Field(
        default="", description="Plain-language description of what further file(s) are still required, used "
                                 "whenever file_situation is 'missing', 'partially_present', or "
                                 "'wrong_file_uploaded'. This is also what File Relevance Checker reads as "
                                 "WHAT_WAS_PREVIOUSLY_NOTED_AS_STILL_NEEDED -- keep it accurate and current. "
                                 "Empty string otherwise."
    )
 
    message_to_file_relevance_checker: str = Field(
        default="", description="Populated IF AND ONLY IF next_action == 'route_to_file_relevance_checker'. "
                                 "A clear, specific note: what exactly you need checked and why. Never route "
                                 "there with this blank."
    )
 
    plan: List[PlanStep] = Field(
        default_factory=list,
        description="The FULL current plan state, every step. MEANINGLESS/empty while current_phase is "
                     "'identifying_task' or 'identifying_files' -- only populate once "
                     "current_phase == 'planning_and_dispatch'."
    )
 
    next_action: Literal[
        "general_chat_response",
        "ask_user",
        "route_to_file_uploader",
        "route_to_file_relevance_checker",
        "dispatch_interface_agent",
        "dispatch_subject_matter_expert",
        "dispatch_consultant",
        "dispatch_coding_agent",
        "finalize",
    ] = Field(
        ..., description="MUST be valid for current_phase (enforced deterministically, but reason correctly "
                          "regardless): identifying_task -> {general_chat_response, ask_user}; "
                          "identifying_files -> {route_to_file_uploader, route_to_file_relevance_checker, "
                          "ask_user}; planning_and_dispatch -> {dispatch_interface_agent, "
                          "dispatch_subject_matter_expert, dispatch_consultant, dispatch_coding_agent, "
                          "route_to_file_uploader, ask_user, finalize}."
    )
 
    dispatch_instructions: str = Field(
        default="", description="Populated whenever next_action dispatches SME/Consultant/Coding Agent. BE "
                                 "THOROUGH AND DETAILED. When dispatching Coding Agent, ALWAYS explicitly "
                                 "restate WORKING_DIRECTORY. NOT used for route_to_file_uploader or "
                                 "route_to_file_relevance_checker -- those use message_to_user and "
                                 "message_to_file_relevance_checker respectively. Empty string otherwise."
    )
 
    message_to_interface_agent: List[InterfaceWidgetSpec] = Field(
        default_factory=list, description="A LIST of widget specs, each carrying its own 'name'. Populated "
                                           "IF AND ONLY IF next_action == 'dispatch_interface_agent'; empty "
                                           "list otherwise."
    )
 
    message_to_user: str = Field(
        ..., description =  "Plain text shown directly to the user. The content of this field MUST "
                            "match the value selected in the 'next_action' field as follows: "
                            "If next_action is 'general_chat_response': provide your actual conversational reply. "
                            "If next_action is 'ask_user': provide exactly ONE minimal question. "
                            "If next_action is 'route_to_file_uploader': provide a plain request naming the file TYPE(s) to upload and why (this is the ONLY place this request is communicated). "
                            "If next_action is 'finalize': provide the complete final answer or a polite give-up message. "
                            "If next_action is 'dispatch_interface_agent': provide a short message telling the user what is happening. "
                            "For any other subagent dispatches or 'route_to_file_relevance_checker': leave this field completely empty."
    )

 
    status_update: str = Field(
        ..., description="A short, present-tense, plain-language line for loading/spinner display. Must NEVER "
                          "reveal internal agent names, node names, tool names, system prompts, or system "
                          "architecture."
    )
 
    escalation_note: str = Field(
        default="", description="Populated ONLY when this turn is handling an escalation. Empty otherwise."
    )




class State(TypedDict, total=False): 
    messages : Annotated[list[AnyMessage], add_messages]
    working_directory: str
    fea_planner_conversations: Optional[List[AnyMessage]]
    coding_dispatch_events: Optional[List[AnyMessage]]
    consultant_dispatch_events: Optional[List[AnyMessage]]
    sme_dispatch_events_sme_only: Optional[List[AnyMessage]] 
    sme_dispatch_events_senior_sme_only: Optional[List[AnyMessage]] 
    stored_files_info: Optional[dict]
    stored_file_names: Optional[List[str]]
    updated_files_sme_signal: Optional[List[str]]
    updated_files_consultant_signal: Optional[List[str]]
    file_relevance_checker_response: Optional[FileRelevanceVerdict]
    fea_planner_response: Optional[FEAPlannerDecision]
    fea_planner_plan: Optional[List[PlanStep]]
    fea_planner_phase: Optional[str]
    file_resolution_loop_count: Optional[int]
    sme_response: Optional[SMEDecision]
    senior_sme_response: Optional[SeniorSMEVerdict]
    senior_sme_review_feedback: Optional[str]
    senior_sme_rejection_count: Optional[int]
    senior_sme_escalation : Optional[str] 
    senior_sme_total_escalation_count : Optional[int]
    senior_sme_continuous_escalation_count: Optional[int]
    senior_sme_verdict: Optional[str]
    consultant_response: Optional[ConsultantDecision]
    coding_escalation: Optional[str]
    coding_continuous_error_count: Optional[int]
    coding_continuous_escalation_count: Optional[int]
    coding_total_escalation_count: Optional[int]
    coding_agent_response: Optional[CodingAgentDecision]
    coding_agent_plan: Optional[List[CodingPlanStep]]
    submitted_code: Optional[str]
    execution_stdout: Optional[str]
    execution_stderr: Optional[str]
    execution_agent_verdict: Optional[str]
    files_produced_by_script: Optional[dict]
    route: Optional[str]
    last_agent: Optional[str] 






#----------------------------Tool Args Schema----------------------------

class CaptureAbaqusInpScreenshotArgs(BaseModel): 
    inp_file_path: str = Field(
        ..., description="Absolute path to the Abaqus .inp file to render."
    )
    output_image_path: str = Field(
        ...,
        description=(
            "Absolute path to write the PNG screenshot to. A '.png' "
            "extension is enforced automatically if missing."
        ),
    )
 
    model_name: str = Field(
        "ScreenshotModel",
        description="Name for the scratch Abaqus model created from the .inp file.",
    )
    step_name: Optional[str] = Field(
        None,
        description=(
            "Which analysis step's loads/BCs to display. Defaults to the "
            "first non-Initial step if one exists, else 'Initial'."
        ),
    )
    keep_model_in_db: bool = Field(
        False,
        description="Keep the imported scratch model in memory after rendering, instead of deleting it.",
    )
 
    camera_position: Optional[Tuple[float, float, float]] = Field(
        None, description="(x, y, z) camera eye position in model coordinates. Requires camera_target."
    )
    camera_target: Optional[Tuple[float, float, float]] = Field(
        None, description="(x, y, z) point the camera looks at. Required if camera_position is set."
    )
    camera_up_vector: Tuple[float, float, float] = Field(
        (0.0, 0.0, 1.0), description="Up direction for the camera, as (x, y, z)."
    )
    predefined_view: Literal["Iso", "Front", "Back", "Top", "Bottom", "Left", "Right"] = Field(
        "Iso",
        description="Named stock camera view, used only when camera_position is not provided.",
    )
    projection: Literal["PARALLEL", "PERSPECTIVE"] = Field(
        "PARALLEL", description="Camera projection type."
    )
    auto_fit: bool = Field(
        True, description="Auto-zoom the view to fit the whole model after the camera is set."
    )
    view_width: Optional[float] = Field(
        None, gt=0, description="Manual zoom: visible width (model units) of the view, applied after auto_fit."
    )
 
    show_loads: bool = Field(True, description="Show load symbols (arrows).")
    show_bcs: bool = Field(True, description="Show boundary-condition symbols (restraint glyphs).")
    show_mesh: bool = Field(False, description="Show the finite element mesh over the geometry.")
    show_predefined_fields: bool = Field(False, description="Show predefined field symbols (e.g. initial temperature).")
    show_connectors: bool = Field(False, description="Show connector element symbols.")
    show_constraints: bool = Field(False, description="Show constraint symbols (ties, couplings, etc.).")
    show_interactions: bool = Field(False, description="Show interaction/contact symbols.")
    visible_instances: Optional[List[str]] = Field(
        None, description="Restrict the view to these part instance names. None shows all instances."
    )
    render_style: Literal["WIREFRAME", "HIDDEN", "SHADED", "FILLED"] = Field(
        "SHADED", description="Face rendering style."
    )
    show_annotations: bool = Field(
        False, description="Show the triad, legend, title block, and state block overlays."
    )
 
    background_color: Optional[str] = Field(
        None, description="Solid background color as a hex string, e.g. '#FFFFFF'. Abaqus rejects "
                          "colour names like 'WHITE'. None leaves the session default."
    )

    _normalise_bg = field_validator("background_color")(_normalise_background_color)

    image_width: int = Field(1920, gt=0, description="Output image width in pixels.")
    image_height: int = Field(1080, gt=0, description="Output image height in pixels.")




class CaptureAbaqusOdbScreenshotArgs(BaseModel):
    """Arguments for capture_abaqus_odb_screenshot."""
 
    odb_file_path: str = Field(..., description="Absolute path to the Abaqus .odb file to render.")
    output_image_path: str = Field(
        ...,
        description="Absolute path to write the PNG screenshot to. A '.png' extension is enforced automatically if missing.",
    )
 
    step_name: Optional[str] = Field(
        None, description="Which step to display. None picks the first step in the odb."
    )
    frame_index: int = Field(
        -1, description="0-based POSITION within the step's frame list: 0 = first, -1 = last, "
                        "-2 = second-to-last. LEAVE THIS AT THE DEFAULT -1 unless the user "
                        "explicitly asked for a particular increment or time -- most requests "
                        "want the final deformed state. This is NOT the 'Frame ID' column in "
                        "the odb summary (that is Abaqus's increment id and is a different "
                        "number); if you need a specific frame, copy the value from the "
                        "summary's 'frame_index' column."
    )
 
    plot_state: List[Literal[
        "UNDEFORMED", "DEFORMED", "CONTOURS_ON_DEF", "CONTOURS_ON_UNDEF",
        "SYMBOLS_ON_DEF", "SYMBOLS_ON_UNDEF",
    ]] = Field(
        default_factory=lambda: ["CONTOURS_ON_DEF"],
        description="Which plot states to enable simultaneously.",
    )
    field_variable: Optional[str] = Field(
        None, description="Result field to display, e.g. 'S', 'U', 'PEEQ'. None leaves the odb's current default."
    )
    field_invariant: Optional[str] = Field(
        None, description="Invariant of field_variable to plot, e.g. 'Mises', 'Max Principal'. Mutually exclusive with field_component."
    )
    field_component: Optional[str] = Field(
        None, description="Component of field_variable to plot, e.g. 'S11', 'U1'. Mutually exclusive with field_invariant."
    )
    output_position: Literal["NODAL", "INTEGRATION_POINT", "ELEMENT_NODAL"] = Field(
        "INTEGRATION_POINT", description="Output position for field_variable. Only used when field_variable is set."
    )
    deformation_scale_factor: Optional[float] = Field(
        None, description="Uniform scale factor for the deformed shape. None leaves Abaqus's own default."
    )
 
    camera_position: Optional[Tuple[float, float, float]] = Field(
        None, description="(x, y, z) camera eye position in model coordinates. Requires camera_target."
    )
    camera_target: Optional[Tuple[float, float, float]] = Field(
        None, description="(x, y, z) point the camera looks at. Required if camera_position is set."
    )
    camera_up_vector: Tuple[float, float, float] = Field(
        (0.0, 0.0, 1.0), description="Up direction for the camera, as (x, y, z)."
    )
    predefined_view: Literal["Iso", "Front", "Back", "Top", "Bottom", "Left", "Right"] = Field(
        "Iso", description="Named stock camera view, used only when camera_position is not provided."
    )
    projection: Literal["PARALLEL", "PERSPECTIVE"] = Field("PARALLEL", description="Camera projection type.")
    auto_fit: bool = Field(True, description="Auto-zoom the view to fit the whole model after the camera is set.")
    view_width: Optional[float] = Field(
        None, gt=0, description="Manual zoom: visible width (model units) of the view, applied after auto_fit."
    )
 
    render_style: Literal["WIREFRAME", "HIDDEN", "SHADED", "FILLED"] = Field(
        "SHADED", description="Face rendering style."
    )
    show_mesh: bool = Field(
        False, description="True draws every element edge (visibleEdges=ALL); False draws only feature/silhouette edges."
    )
    visible_instances: Optional[List[str]] = Field(
        None, description="Restrict the view to these part instance names. None shows all instances."
    )
    show_annotations: bool = Field(
        False,
        description="Show the triad, legend, title block, and state block overlays. Worth enabling when plotting contours, since the legend is the only place the value scale is shown.",
    )
    background_color: Optional[str] = Field(
        None, description="Solid background color as a hex string, e.g. '#FFFFFF'. Abaqus rejects "
                          "colour names like 'WHITE'. None leaves the session default."
    )

    _normalise_bg = field_validator("background_color")(_normalise_background_color)

    image_width: int = Field(1920, gt=0, description="Output image width in pixels.")
    image_height: int = Field(1080, gt=0, description="Output image height in pixels.")
 
    close_odb_after: bool = Field(True, description="Close the odb (in this session) once the screenshot is done.")




class ReadImageFileInput(BaseModel):
    file_path: str = Field(
        ..., 
        description="Absolute path to the image file (.png, .jpeg, or .jpg)."
    )