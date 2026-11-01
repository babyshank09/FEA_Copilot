import os
import sys
import subprocess
import tempfile
import shutil
import textwrap
import re
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.backend.script_templates.input_file_parsing_template import ABAQUS_INP_PARSER_TEMPLATE
from src.backend.script_templates.odb_file_parsing_template import ABAQUS_ODB_PARSER_TEMPLATE
from src.backend.script_templates.step_file_parsing_template import STEP_FILE_PARSER_TEMPLATE
from src.backend.config.config import SIMULATION_ARTIFACTS_DIR
from src.backend.llm.azure_llm_reasoning import get_parsing_llm

load_dotenv()

CURRENT_FILE = os.path.abspath(__file__)
SCRIPT_TEMPLATES_FOLDER = os.path.dirname(CURRENT_FILE)
BACKEND_DIR = os.path.dirname(SCRIPT_TEMPLATES_FOLDER)
CODE_DISPATCH_DIR = os.path.join(SIMULATION_ARTIFACTS_DIR, "code_dispatch")
TARGET_DIR = os.path.join(SIMULATION_ARTIFACTS_DIR, "parsed_files_info")
WINDOWS_PATH_RE = re.compile(r'([A-Za-z]:)((?:\\[^\\\'"\n]+)+)')

SYS_CODE_PREFIX = textwrap.dedent(r"""
import sys
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__
""")



def get_input_parsing_script(input_file_path: str, output_summary_json_path: str) -> str:
    return (
        ABAQUS_INP_PARSER_TEMPLATE
        .replace("__INPUT_FILE_PATH__", repr(input_file_path))
        .replace("__OUTPUT_SUMMARY_JSON_PATH__", repr(output_summary_json_path))
    )


def get_odb_parsing_script(odb_file_path: str, output_summary_md_path: str) -> str:
    return (
        ABAQUS_ODB_PARSER_TEMPLATE
        .replace("__ODB_FILE_PATH__", repr(odb_file_path))
        .replace("__OUTPUT_SUMMARY_MD_PATH__", repr(output_summary_md_path))
    )


def get_step_parsing_script(step_file_path: str, output_summary_json_path: str) -> str:
    return (
        STEP_FILE_PARSER_TEMPLATE
        .replace("__STEP_FILE_PATH__", repr(step_file_path))
        .replace("__OUTPUT_SUMMARY_JSON_PATH__", repr(output_summary_json_path))
    )


def escape_windows_paths(code: str) -> str:
    def repl(m):
        drive, rest = m.group(1), m.group(2)
        return drive + rest.replace('\\', '\\\\')
    return WINDOWS_PATH_RE.sub(repl, code)



def run_abaqus_script(rendered_code: str):
    """Writes temporary Python script, executes via Abaqus, and cleans up script & log artifacts."""

    abaqus_exec = shutil.which("abaqus.bat") or shutil.which("abaqus")
    if not abaqus_exec:
        raise EnvironmentError(
            "Abaqus not found in system PATH. Ensure 'C:\\SIMULIA\\Commands' is added to Environment Variables."
        )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        dir=CODE_DISPATCH_DIR,
        delete=False,
        encoding="utf-8"
    ) as temp_file:

        cleaned_code = escape_windows_paths(rendered_code)
        full_code = SYS_CODE_PREFIX + "\n" + textwrap.dedent(cleaned_code)
        temp_file.write(full_code)
        temp_script_path = temp_file.name

    try:
        abaqus_command = [abaqus_exec, "cae", f"noGUI={temp_script_path}"]
        result = subprocess.run(
            abaqus_command,
            cwd=CODE_DISPATCH_DIR,
            check=False,
            capture_output=True,
            text=True,
        )

        return result
    
    except subprocess.CalledProcessError as e:
        error_details = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"Abaqus execution failed:\n{error_details}") from e
    finally:
        if os.path.exists(temp_script_path):
            os.remove(temp_script_path)
        if os.path.exists(os.path.join(CODE_DISPATCH_DIR, "abaqus.rpy")):
            os.remove(os.path.join(CODE_DISPATCH_DIR, "abaqus.rpy"))



def run_python_script(rendered_code: str):
    """Writes temporary Python script, executes via Python, and cleans up script."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        dir=CODE_DISPATCH_DIR,
        delete=False,
        encoding="utf-8"
    ) as temp_file:

        cleaned_code = escape_windows_paths(rendered_code)
        full_code = textwrap.dedent(cleaned_code)
        temp_file.write(full_code)
        temp_script_path = temp_file.name

    try:
        # python_command = ["python", temp_script_path]
        python_command = [sys.executable, temp_script_path]
        subprocess.run(
            python_command,
            cwd=CODE_DISPATCH_DIR,
            check=True,
            capture_output=True,
            text=True,
        ) 
    except subprocess.CalledProcessError as e:
        error_details = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"Python script execution failed:\n{error_details}") from e
    finally:
        if os.path.exists(temp_script_path):
            os.remove(temp_script_path)




def parse_file(file_path: str) -> dict:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Critical Error: The file '{file_path}' is missing.")

    code_dispatch_dir = CODE_DISPATCH_DIR
    target_dir = TARGET_DIR

    os.makedirs(code_dispatch_dir, exist_ok=True)
    os.makedirs(target_dir, exist_ok=True)

    filename = os.path.basename(file_path)
    root, ext = os.path.splitext(filename)
    ext_lower = ext.lower()


    if ext_lower == ".inp":
        inp_json_path = os.path.join(target_dir, f"{root}_inp_summary.json")
        rendered_code = get_input_parsing_script(file_path, inp_json_path)
        run_abaqus_script(rendered_code)

        with open(inp_json_path, "r", encoding="utf-8") as f:
            inp_summary_content = f.read()

        llm = get_parsing_llm()
        system_msg = SystemMessage(
            content="""
            You are an expert Abaqus model summarizer. 

            Your task is to create a **complete, zero-loss summary** of the provided Abaqus INP/ODB structured JSON. 

            ### Strict Requirements:
            - Do **not** omit any information.
            - Preserve every part name, node/element count, bounding box, element type, nset/elset name + count, surface, section, material property, instance transform, tie constraint, step setting, and meta field.
            - Never approximate or drop numerical values.
            - Never summarize away details — the output must be fully usable by another agent as a complete replacement of the original JSON.

            ### Required Output Structure:

            1. **Heading**
            2. **Parts**  
            For every part, clearly list:
            - Node count + bounding box
            - Element types + counts + nodes per element
            - All Nsets (name + count / generate info)
            - All Elsets (name + count)
            - All Surfaces
            - Sections (type, elset, material)

            3. **Assembly**
            - Table of all Instances with Part, Translate, and Rotate
            - Assembly-level Nsets, Elsets, Surfaces
            - Full list of all Tie constraints (name + connected surfaces + parameters)

            4. **Materials**
            - Table or clear list of every material with Density, Elastic properties, Plastic/Hyperelastic data, etc.

            5. **Steps**
            - Step name, procedure type, boundary conditions, loads, output requests, and other keywords

            6. **Meta**
            - source_file, part_names, material_names, step_names, instance_names, and the original note

            ### Style Guidelines:
            - Use clean Markdown formatting
            - Prefer tables for instances, materials, and mesh statistics when helpful
            - Be precise and technical
            - Keep the language concise but complete
            - Maintain hierarchical organization so the summary is easy to scan
            """)
        
        human_msg = HumanMessage(
            content=f"""
            Here is the json to be summarized:
            {inp_summary_content}
            """)
        
        response = llm.invoke([system_msg, human_msg])

        inp_md_path = os.path.join(target_dir, f"{root}_inp_summary.md")
        with open(inp_md_path, "w", encoding="utf-8") as f:
            f.write(response.content)

        if os.path.exists(inp_json_path):
            os.remove(inp_json_path)

        return {
            "file_name": filename,
            "file_path": file_path,
            "derived_files": {
                f"{root}_inp_summary.md": {
                    "file_name": f"{root}_inp_summary.md",
                    "file_path": inp_md_path,
                    "type": "inp_summary",
                }
            },
        }

    elif ext_lower == ".odb":
        odb_md_path = os.path.join(target_dir, f"{root}_odb_summary.md")
        rendered_code = get_odb_parsing_script(file_path, odb_md_path)
        run_abaqus_script(rendered_code)

        return {
            "file_name": filename,
            "file_path": file_path,
            "derived_files": {
                f"{root}_odb_summary.md": {
                    "file_name": f"{root}_odb_summary.md",
                    "file_path": odb_md_path,
                    "type": "odb_summary",
                }
            },
        }

    elif ext_lower in [".step", ".stp"]:
        step_json_path = os.path.join(target_dir, f"{root}_step_summary.json")
        rendered_code = get_step_parsing_script(file_path, step_json_path)
        run_python_script(rendered_code)

        return {
            "file_name": filename,
            "file_path": file_path,
            "derived_files": {
                f"{root}_step_summary.json": {
                    "file_name": f"{root}_step_summary.json",
                    "file_path": step_json_path,
                    "type": "step_summary",
                }
            },
        }

    return {
        "file_name": filename,
        "file_path": file_path,
    }


# if __name__ == "__main__":
#     try:
#         info1 =parse_file(os.path.join(BACKEND_DIR, "simulation_artifacts/user_uploaded_files/controller.stp"))
#         info2 =parse_file(os.path.join(BACKEND_DIR, "simulation_artifacts/user_uploaded_files/e2.inp"))
#         info3 = parse_file(os.path.join(BACKEND_DIR, "simulation_artifacts/user_uploaded_files/e2.odb"))
 
#     except Exception as e:
#         print(f"Error occurred during file parsing: {e}")

