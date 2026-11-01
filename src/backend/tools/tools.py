import os
import json
import ast
import base64
import streamlit as st
from typing import Optional, Tuple, List
from langchain_core.tools import tool
from src.backend.config.logging_config import DEBUG, app_logger
from src.backend.rag.ingestion_pipeline import IngestionPipeline
from src.backend.rag.retrieval_pipeline import RetrievalPipeline
from src.backend.utils.utils import add_streamlit_files_to_storage
from src.backend.script_templates.main import run_abaqus_script, parse_file
from src.backend.state.state import CaptureAbaqusInpScreenshotArgs, CaptureAbaqusOdbScreenshotArgs, ReadImageFileInput
from src.backend.script_templates.capture_abaqus_model_screenshot_template import CAPTURE_ABAQUS_MODEL_SCREENSHOT_TEMPLATE
from src.backend.script_templates.capture_abaqus_odb_screenshot_template import CAPTURE_ABAQUS_ODB_SCREENSHOT_TEMPLATE




@st.cache_resource
def get_scripting_ingestion_pipeline() -> IngestionPipeline:
    return IngestionPipeline(rag_target="scripting", log=DEBUG)


@st.cache_resource
def get_procedural_ingestion_pipeline() -> IngestionPipeline:
    return IngestionPipeline(rag_target="procedural", log=DEBUG)


@st.cache_resource
def get_scripting_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline(
        vectorstore=get_scripting_ingestion_pipeline().vectorstore,
        rag_target="scripting",
        log=DEBUG,
    )


@st.cache_resource
def get_procedural_retrieval_pipeline() -> RetrievalPipeline:
    return RetrievalPipeline(
        vectorstore=get_procedural_ingestion_pipeline().vectorstore,
        rag_target="procedural",
        log=DEBUG,
    )



def get_embedded_filenames():
    embedded_filenames = get_scripting_ingestion_pipeline().get_embedded_filenames()
    if "abaqus_2024_scripting_reference.pdf" in embedded_filenames:
        embedded_filenames.remove("abaqus_2024_scripting_reference.pdf")
    return embedded_filenames


def ingest_user_scripting_docs(uploaded_files):
    add_streamlit_files_to_storage(files = uploaded_files)
    get_scripting_ingestion_pipeline().run_ingestion_pipeline()
    get_scripting_retrieval_pipeline().refresh_bm25()


def delete_doc_from_vectorstore(filename):
    get_scripting_ingestion_pipeline().delete_chunks_by_source(source_filename = filename)
    get_scripting_retrieval_pipeline().refresh_bm25()



@tool
def procedural_rag_tool(query: str) -> str:
    """
    Retrieve documented procedural workflows describing how a given kind
    of Abaqus task is typically approached -- the sequence of operations
    and underlying logic, not example code.

    Searches a vectorstore of written procedural guidance covering common
    task patterns in Abaqus automation. Each workflow was authored for an
    individual, specific use case, so a retrieved workflow will often only
    PARTIALLY match the current task -- read it critically rather than
    applying it mechanically, and be prepared to combine guidance from
    more than one retrieved workflow, or to disregard parts that don't
    apply. Retrieval uses a hybrid (keyword + semantic) search with a
    similarity-score threshold, so a query with no good match will
    legitimately return nothing -- this is expected and normal, not a
    failure.

    Args:
        query: A natural-language description of the TASK you're trying
            to accomplish or the kind of workflow you're looking for --
            phrase it around the goal, not a bare keyword. For example,
            "setting up a static linear analysis from an uploaded CAD
            geometry file" or "comparing stress results across two job
            runs" will retrieve better matches than a single term like
            "static analysis" or "comparison".

    Returns:
        A newline-separated block of the most relevant retrieved chunks,
        each labeled "Chunk N" for reference, drawn from documented
        workflows. If no chunk clears the similarity threshold, returns a
        plain-text message stating that no relevant information was found
        -- check for this explicitly rather than assuming a match.
    """
    retrieved_chunks = get_procedural_retrieval_pipeline().run_retrieval_pipeline(query=query, retriever_type="hybrid", vector_retriever_type="similarity_score_threshold")
    if retrieved_chunks:
        retrieved_context = "\n\n".join([f"Chunk {i+1}:\n{chunk.page_content}" for i, chunk in enumerate(retrieved_chunks)])
    else:
        retrieved_context = "No relevant chunks/information was found regarding your query"

    return retrieved_context



@tool
def scripting_rag_tool(query: str) -> str:
    """
    Retrieve example Abaqus Python script excerpts relevant to a scripting
    or automation question.

    Searches a vectorstore built from a library of SAMPLE ABAQUS SCRIPTS --
    this is a supplementary lookup for concrete example patterns and
    idiomatic usage, NOT an exhaustive API reference and NOT official
    Abaqus/SIMULIA documentation. Retrieval uses a hybrid (keyword +
    semantic) search with a similarity-score threshold, so a query with no
    good match in the sample library will legitimately return nothing --
    this is expected and normal, not a failure. When that happens, rely on
    your own established knowledge of the Abaqus scripting API rather than
    treating the absence of results as a blocker.

    Args:
        query: A natural-language description of the scripting task or
            operation you need an example for -- phrase it the way you'd
            describe the goal, not as a bare keyword. For example,
            "assigning a shell section to a part" or "extracting nodal
            displacement history output from an odb" will retrieve better
            matches than a single term like "section" or "odb".

    Returns:
        A newline-separated block of the most relevant retrieved chunks,
        each labeled "Chunk N" for reference, drawn from real sample
        scripts. If no chunk clears the similarity threshold, returns a
        plain-text message stating that no relevant information was found
        -- check for this explicitly rather than assuming a match.
    """
    retrieved_chunks = get_scripting_retrieval_pipeline().run_retrieval_pipeline(query=query, retriever_type="hybrid", vector_retriever_type="similarity_score_threshold")
    if retrieved_chunks:
        retrieved_context = "\n\n".join([f"Chunk {i+1}:\n{chunk.page_content}" for i, chunk in enumerate(retrieved_chunks)])
    else:
        retrieved_context = "No relevant chunks/information was found regarding your query"

    return retrieved_context
    


@tool
def read_parsed_file_info(file_path: str) -> str:
    """
    Read the full contents of a parsed/derived file from storage and
    return it as a JSON-formatted string.

    Typically used to read the parsed summary of an uploaded .inp, .odb,
    or .step/.stp file -- i.e. the file_path found under a
    STORED_FILES_INFO entry's "derived_files", not the path of the
    original uploaded file itself. The three expected summary types are:
    - inp_summary: model setup info (materials, sections, steps, loads,
      boundary conditions)
    - odb_summary: simulation results (stresses, displacements, reaction
      forces, step outcomes)
    - step_summary: CAD geometry info from a .step/.stp file

    This tool is extension-based, not name-based -- it reads ANY file
    ending in .json (parsed and returned directly as JSON) or .md
    (wrapped as {"file_type": "markdown", "text": <raw content>}),
    regardless of its specific filename. Any other extension is treated
    as unsupported.

    On failure -- a missing file, an unsupported extension, or an
    unreadable/corrupt file -- this tool RAISES. You will receive the error
    back as a TOOL ERROR message describing what went wrong; read it, fix
    the argument (most often a wrong or stale file_path -- re-check
    STORED_FILES_INFO for the exact derived path) and call again.

    Args:
        file_path: Absolute path to the file to read -- the file_path of
            the DERIVED/parsed entry from STORED_FILES_INFO, not the path
            of the original uploaded file.

    Returns:
        On success, a JSON-formatted string of the file's parsed content
        (for .md files, wrapped under a "text" key as described above).
    """

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"read_parsed_file_info: no file at '{file_path}'. Re-check the derived "
            f"file_path in STORED_FILES_INFO."
        )

    filename = os.path.basename(file_path)
    root, ext = os.path.splitext(filename)
    ext_lower = ext.lower()

    if ext_lower not in (".json", ".md"):
        raise ValueError(
            f"read_parsed_file_info: unsupported file extension '{ext}'. This tool reads "
            f"only .json and .md derived files."
        )

    try:
        if ext_lower == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)

        else:
            with open(file_path, "r", encoding="utf-8") as f:
                content = {"file_type": "markdown", "text": f.read()}

        return json.dumps(content, indent=4)

    except Exception as e:
        app_logger.error(f"read_parsed_file_info Tool Error Failed to read file: \n{str(e)}")
        raise Exception(f"read_parsed_file_info Tool Error Failed to read file: \n{str(e)}")
  


@tool
def syntax_check_tool(code: str) -> str:
    """
    Deterministically checks whether the given Python code is syntactically
    valid, WITHOUT executing it. Use this before submitting -- catches
    trivial errors for free, cheaper than a real execution cycle.
 
    Args:
        code: the full Python script to check.
 
    Returns:
        "VALID" if the code parses cleanly, or "INVALID: <error detail>"
        with the specific syntax error and line number if it doesn't.
    """
    try:
        ast.parse(code)
        return "VALID"
    except SyntaxError as e:
        return f"INVALID: {e.msg} at line {e.lineno}, column {e.offset}"

    

@tool("capture_abaqus_model_screenshot", args_schema=CaptureAbaqusInpScreenshotArgs)
def capture_abaqus_model_screenshot(
    inp_file_path: str,
    output_image_path: str,
    model_name: str = "ScreenshotModel",
    step_name: Optional[str] = None,
    keep_model_in_db: bool = False,
    camera_position: Optional[Tuple[float, float, float]] = None,
    camera_target: Optional[Tuple[float, float, float]] = None,
    camera_up_vector: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    predefined_view: str = "Iso",
    projection: str = "PARALLEL",
    auto_fit: bool = True,
    view_width: Optional[float] = None,
    show_loads: bool = True,
    show_bcs: bool = True,
    show_mesh: bool = False,
    show_predefined_fields: bool = False,
    show_connectors: bool = False,
    show_constraints: bool = False,
    show_interactions: bool = False,
    visible_instances: Optional[List[str]] = None,
    render_style: str = "SHADED",
    show_annotations: bool = False,
    background_color: Optional[str] = None,
    image_width: int = 1920,
    image_height: int = 1080,
) -> dict:
    """
    Renders and captures a high-resolution screenshot of an Abaqus model (.inp file).

    Use this tool to visually inspect pre-processing model setups, including geometry,
    mesh discretization, boundary conditions (BCs), applied loads, tie constraints, 
    and connector interactions prior to or during simulation setup.

    Args:
        inp_file_path (str): Absolute file path to the Abaqus input (.inp) file.
        output_image_path (str): Destination file path where the rendered PNG image will be saved.
        model_name (str, optional): Name to assign to the imported model in the Abaqus session. Defaults to "ScreenshotModel".
        step_name (str, optional): Specific step name to display boundary conditions and loads for. If None, defaults to the first non-Initial step if one exists, otherwise 'Initial'.
        keep_model_in_db (bool, optional): If True, retains the imported model in the Abaqus Mdb database after rendering. Defaults to False.
        camera_position (Tuple[float, float, float], optional): Exact (X, Y, Z) coordinates for the viewport camera placement.
        camera_target (Tuple[float, float, float], optional): Exact (X, Y, Z) focal target point for the viewport camera.
        camera_up_vector (Tuple[float, float, float], optional): Directional (X,Y,Z) vector indicating 'Up' in viewport space. Defaults to (0.0, 0.0, 1.0).
        predefined_view (str, optional): Standard viewport orientation. Options: 'Iso', 'Front', 'Back', 'Top', 'Bottom', 'Left', 'Right'. Defaults to "Iso".
        projection (str, optional): Viewport projection mode ('PARALLEL' or 'PERSPECTIVE'). Defaults to "PARALLEL".
        auto_fit (bool, optional): Automatically scales and centers the model within the viewport frame. Defaults to True.
        view_width (float, optional): Explicit viewport width in model units. Used when auto_fit is False.
        show_loads (bool, optional): Toggles visibility of load vectors and arrows. Defaults to True.
        show_bcs (bool, optional): Toggles visibility of boundary condition symbols. Defaults to True.
        show_mesh (bool, optional): Toggles element mesh wireframe visibility on model instances. Defaults to False.
        show_predefined_fields (bool, optional): Toggles display of predefined field initial conditions. Defaults to False.
        show_connectors (bool, optional): Toggles display of connector elements and wire features. Defaults to False.
        show_constraints (bool, optional): Toggles display of tie, MPC, and kinematic constraints. Defaults to False.
        show_interactions (bool, optional): Toggles display of contact surfaces and interaction pairs. Defaults to False.
        visible_instances (List[str], optional): List of assembly instance names to render. If None, all instances are displayed.
        render_style (str, optional): Model rendering mode. Options: 'SHADED', 'WIREFRAME', 'FILLED', 'HIDDEN'. Defaults to "SHADED".
        show_annotations (bool, optional): Displays Abaqus viewport annotations, legends, and title blocks. Defaults to False.
        background_color (str, optional): Solid background color as a HEX STRING only, e.g. '#FFFFFF'. Abaqus rejects color names such as 'WHITE'. Defaults to the viewport system preference.
        image_width (int, optional): Output image width in pixels. Defaults to 1920.
        image_height (int, optional): Output image height in pixels. Defaults to 1080.

    Returns:
        dict: A dictionary containing rendered visual artifacts and metadata:
            - "b64_image" (str): Base64-encoded string of the captured PNG image.
            - "image_file_info" (dict): Parsed file metadata returned by parse_file().
            - "text" (str): Human-readable execution log message confirming saving location.

    Raises:
        Exception: If the underlying Abaqus CAE execution script fails or parsing the rendered file raises an error.
    """
    
    replacements = {
    "__INP_FILE_PATH__": f"{repr(inp_file_path)},",
    "__OUTPUT_IMAGE_PATH__": f"{repr(output_image_path)},",
    "__MODEL_NAME__": f"{repr(model_name)},",
    "__STEP_NAME__": f"{repr(step_name)},",
    "__KEEP_MODEL_IN_DB__": f"{repr(keep_model_in_db)},",
    "__CAMERA_POSITION__": f"{repr(camera_position)},",
    "__CAMERA_TARGET__": f"{repr(camera_target)},",
    "__CAMERA_UP_VECTOR__": f"{repr(camera_up_vector)},",
    "__PREDEFINED_VIEW__": f"{repr(predefined_view)},",
    "__PROJECTION__": f"{repr(projection)},",
    "__AUTO_FIT__": f"{repr(auto_fit)},",
    "__VIEW_WIDTH__": f"{repr(view_width)},",
    "__SHOW_LOADS__": f"{repr(show_loads)},",
    "__SHOW_BCS__": f"{repr(show_bcs)},",
    "__SHOW_MESH__": f"{repr(show_mesh)},",
    "__SHOW_PREDEFINED_FIELDS__": f"{repr(show_predefined_fields)},",
    "__SHOW_CONNECTORS__": f"{repr(show_connectors)},",
    "__SHOW_CONSTRAINTS__": f"{repr(show_constraints)},",
    "__SHOW_INTERACTIONS__": f"{repr(show_interactions)},",
    "__VISIBLE_INSTANCES__": f"{repr(visible_instances)},",
    "__RENDER_STYLE__": f"{repr(render_style)},",
    "__SHOW_ANNOTATIONS__": f"{repr(show_annotations)},",
    "__BACKGROUND_COLOR__": f"{repr(background_color)},",
    "__IMAGE_WIDTH__": f"{repr(image_width)},",
    "__IMAGE_HEIGHT__": f"{repr(image_height)}",
    }

    script = CAPTURE_ABAQUS_MODEL_SCREENSHOT_TEMPLATE

    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)

    try:
        result = run_abaqus_script(rendered_code = script)
        stdout = result.stdout
        stderr = result.stderr
        success = "Abaqus Error: cae exited with an error." not in stdout

        if not success:
            app_logger.error(f"Error occured while running the capture_abaqus_model_screenshot tool script:\n {stderr}")
            raise Exception(f"capture_abaqus_model_screenshot Tool Error: \n{stderr}")

        else:
            image_file_info = parse_file(file_path = output_image_path)

            with open(output_image_path, "rb") as image_file:
                encoded_b64_string = base64.b64encode(image_file.read()).decode("utf-8") 

            text = f"""
            The requested image has been sent successfully. 
            Additionally, the image has been stored in storage and saved at the address: {output_image_path}. 
            """

            return {
                "b64_image": encoded_b64_string,
                "image_file_info": image_file_info,
                "text": text
            }

    except Exception as e:
        app_logger.error(f"capture_abaqus_model_screenshot Tool Error: \n{str(e)}")
        raise Exception(f"capture_abaqus_model_screenshot Tool Error: \n{str(e)}")

  

@tool("capture_abaqus_odb_screenshot", args_schema=CaptureAbaqusOdbScreenshotArgs)
def capture_abaqus_odb_screenshot(
    odb_file_path: str,
    output_image_path: str,
    step_name: Optional[str] = None,
    frame_index: int = -1,
    plot_state: List[str] = ["CONTOURS_ON_DEF"],
    field_variable: Optional[str] = None,
    field_invariant: Optional[str] = None,
    field_component: Optional[str] = None,
    output_position: str = "INTEGRATION_POINT",
    deformation_scale_factor: Optional[float] = None,
    camera_position: Optional[Tuple[float, float, float]] = None,
    camera_target: Optional[Tuple[float, float, float]] = None,
    camera_up_vector: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    predefined_view: str = "Iso",
    projection: str = "PARALLEL",
    auto_fit: bool = True,
    view_width: Optional[float] = None,
    render_style: str = "SHADED",
    show_mesh: bool = False,
    visible_instances: Optional[List[str]] = None,
    show_annotations: bool = False,
    background_color: Optional[str] = None,
    image_width: int = 1920,
    image_height: int = 1080,
    close_odb_after: bool = True,
) -> dict:
    """
    Renders and captures a post-processing screenshot of Abaqus simulation results (.odb file).

    Use this tool to visualize post-processing results such as stress/strain contours, 
    deformed vs. undeformed shapes, displacement fields, reaction forces, or material field variables 
    at a specific step and frame index.

    Args:
        odb_file_path (str): Absolute file path to the Abaqus Output Database (.odb) file.
        output_image_path (str): Destination image path where the rendered PNG format contour screenshot will be saved.
        step_name (str, optional): Name of the analysis step to extract results from. If None, defaults to the last available step.
        frame_index (int, optional): 0-based POSITION within the step's frame list (0 = first, -1 = last, -2 = second-to-last). Defaults to -1, the final frame -- leave it there unless the user explicitly asked for a particular increment or time. This is NOT the "Frame ID" column of the odb summary (Abaqus's increment id, a different number); to target a specific frame, copy the value from the summary's "frame_index" column.
        plot_state (List[str], optional): List of plot display modes. 
            Options include: 'UNDEFORMED', 'DEFORMED', 'CONTOURS_ON_DEF', 'CONTOURS_ON_UNDEF', 'SYMBOLS_ON_DEF'. 
            Defaults to ["CONTOURS_ON_DEF"].
        field_variable (str, optional): Field output variable name to display (e.g., 'S' for Stress, 'U' for Displacement, 'E' for Strain, 'PE' for Plastic Strain).
        field_invariant (str, optional): Variable invariant, written exactly as Abaqus spells it in the ODB -- title case with spaces, e.g. 'Mises', 'Max Principal', 'Min Principal', 'Magnitude', 'Pressure'. NOT upper-snake forms like 'MAX_PRINCIPAL'. Mutually exclusive with field_component.
        field_component (str, optional): Specific vector or tensor component string (e.g., 'S11', 'S22', 'U1', 'U2').
        output_position (str, optional): Integration position for field variable extractions (e.g., 'INTEGRATION_POINT', 'NODAL', 'ELEMENT_NODAL'). Defaults to "INTEGRATION_POINT".
        deformation_scale_factor (float, optional): Custom scaling factor applied to node deformations. If None, Abaqus auto-calculates scale.
        camera_position (Tuple[float, float, float], optional): Exact (X, Y, Z) coordinates for the viewport camera position.
        camera_target (Tuple[float, float, float], optional): Exact (X, Y, Z) target focus point for the camera.
        camera_up_vector (Tuple[float, float, float], optional): Vector (X, Y, Z) establishing viewport 'Up' direction. Defaults to (0.0, 0.0, 1.0).
        predefined_view (str, optional): Standard viewport perspective. Options: 'Iso', 'Front', 'Back', 'Top', 'Bottom', 'Left', 'Right'. Defaults to "Iso".
        projection (str, optional): Projection style ('PARALLEL' or 'PERSPECTIVE'). Defaults to "PARALLEL".
        auto_fit (bool, optional): Automatically zooms and centers model in the viewport. Defaults to True.
        view_width (float, optional): Exact view width dimension in physical units when auto_fit is False.
        render_style (str, optional): Surface rendering style ('SHADED', 'WIREFRAME', 'FILLED', 'HIDDEN'). Defaults to "SHADED".
        show_mesh (bool, optional): Toggles visibility of mesh element edges over contour plots. Defaults to False.
        visible_instances (List[str], optional): Specific part instance names to render. If None, displays all instances in ODB.
        show_annotations (bool, optional): Shows viewport legend, color bar scale, step information, and title blocks. Defaults to False.
        background_color (str, optional): Solid background color as a HEX STRING only, e.g. '#FFFFFF'. Abaqus rejects color names such as 'WHITE'. Defaults to the viewport system default.
        image_width (int, optional): Image width resolution in pixels. Defaults to 1920.
        image_height (int, optional): Image height resolution in pixels. Defaults to 1080.
        close_odb_after (bool, optional): Safely closes and releases the ODB file handle from memory post-rendering. Defaults to True.

    Returns:
        dict: A dictionary containing rendered visual artifacts and metadata:
            - "b64_image" (str): Base64-encoded string of the captured PNG image.
            - "image_file_info" (dict): Parsed file metadata returned by parse_file().
            - "text" (str): Human-readable confirmation message detailing output path.

    Raises:
        Exception: If Abaqus CAE encounters execution errors while reading the ODB or rendering output files.
    """
 
    replacements = {
    "__ODB_FILE_PATH__": f"{repr(odb_file_path)},",
    "__OUTPUT_IMAGE_PATH__": f"{repr(output_image_path)},",
    "__STEP_NAME__": f"{repr(step_name)},",
    "__FRAME_INDEX__": f"{repr(frame_index)},",
    "__PLOT_STATE__": f"{repr(tuple(plot_state))},",
    "__FIELD_VARIABLE__": f"{repr(field_variable)},",
    "__FIELD_INVARIANT__": f"{repr(field_invariant)},",
    "__FIELD_COMPONENT__": f"{repr(field_component)},",
    "__OUTPUT_POSITION__": f"{repr(output_position)},",
    "__DEFORMATION_SCALE_FACTOR__": f"{repr(deformation_scale_factor)},",
    "__CAMERA_POSITION__": f"{repr(camera_position)},",
    "__CAMERA_TARGET__": f"{repr(camera_target)},",
    "__CAMERA_UP_VECTOR__": f"{repr(camera_up_vector)},",
    "__PREDEFINED_VIEW__": f"{repr(predefined_view)},",
    "__PROJECTION__": f"{repr(projection)},",
    "__AUTO_FIT__": f"{repr(auto_fit)},",
    "__VIEW_WIDTH__": f"{repr(view_width)},",
    "__RENDER_STYLE__": f"{repr(render_style)},",
    "__SHOW_MESH__": f"{repr(show_mesh)},",
    "__VISIBLE_INSTANCES__": f"{repr(visible_instances)},",
    "__SHOW_ANNOTATIONS__": f"{repr(show_annotations)},",
    "__BACKGROUND_COLOR__": f"{repr(background_color)},",
    "__IMAGE_WIDTH__": f"{repr(image_width)},",
    "__IMAGE_HEIGHT__": f"{repr(image_height)},",
    "__CLOSE_ODB_AFTER__": f"{repr(close_odb_after)},",
    }

    script = CAPTURE_ABAQUS_ODB_SCREENSHOT_TEMPLATE

    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
 
    try:
        result = run_abaqus_script(rendered_code = script)
        stdout = result.stdout
        stderr = result.stderr
        success = "Abaqus Error: cae exited with an error." not in stdout

        if not success:
            app_logger.error(f"Error occured while running the capture_abaqus_odb_screenshot tool script:\n {stderr}")
            raise Exception(f"capture_abaqus_odb_screenshot Tool Error: \n{stderr}")

        else:
            image_file_info = parse_file(file_path = output_image_path)

            with open(output_image_path, "rb") as image_file:
                encoded_b64_string = base64.b64encode(image_file.read()).decode("utf-8") 

            text = f"""
            The requested image has been sent successfully. 
            Additionally, the image has been stored in storage and saved at the address: {output_image_path}. 
            """

            return {
                "b64_image": encoded_b64_string,
                "image_file_info": image_file_info,
                "text": text
            }

    except Exception as e:
        app_logger.error(f"capture_abaqus_odb_screenshot Tool Error: \n{str(e)}")
        raise Exception(f"capture_abaqus_odb_screenshot Tool Error: \n{str(e)}")

