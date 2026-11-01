CAPTURE_ABAQUS_MODEL_SCREENSHOT_TEMPLATE = """
from abaqus import mdb, session
from abaqusConstants import (
    ON, OFF,
    PARALLEL, PERSPECTIVE,
    WIREFRAME, HIDDEN, SHADED, FILLED,
    PNG,
    SOLID,
)

RENDER_STYLES = {"WIREFRAME": WIREFRAME, "HIDDEN": HIDDEN, "SHADED": SHADED, "FILLED": FILLED}
PROJECTIONS = {"PARALLEL": PARALLEL, "PERSPECTIVE": PERSPECTIVE}


def capture_abaqus_model_screenshot(
    inp_file_path,
    output_image_path,

    model_name="ScreenshotModel",
    step_name=None,                  
    keep_model_in_db=False,          
                                    
    camera_position=None,            
    camera_target=None,              
    camera_up_vector=(0.0, 0.0, 1.0),
    predefined_view="Iso",          
    projection="PARALLEL",           
    auto_fit=True,                   
    view_width=None,                

    show_loads=True,
    show_bcs=True,
    show_mesh=False,
    show_predefined_fields=False,
    show_connectors=False,
    show_constraints=False,
    show_interactions=False,
    visible_instances=None,         
    render_style="SHADED",        
    show_annotations=False,          

    background_color=None,           
    image_width=1920,
    image_height=1080,
):

    if render_style not in RENDER_STYLES:
        raise ValueError("render_style must be one of {}".format(list(RENDER_STYLES.keys())))
    if projection not in PROJECTIONS:
        raise ValueError("projection must be one of {}".format(list(PROJECTIONS.keys())))
    if camera_position is not None and camera_target is None:
        raise ValueError("camera_target is required when camera_position is given")


    if model_name in mdb.models:
        del mdb.models[model_name]
    mdb.ModelFromInputFile(name=model_name, inputFileName=inp_file_path)
    model = mdb.models[model_name]
    assembly = model.rootAssembly

    try:

        vp_name = list(session.viewports.keys())[0]
        vp = session.viewports[vp_name]
        vp.setValues(displayedObject=assembly)


        vp.assemblyDisplay.setValues(
            renderStyle=RENDER_STYLES[render_style],
            mesh=ON if show_mesh else OFF,
            loads=ON if show_loads else OFF,
            bcs=ON if show_bcs else OFF,
            predefinedFields=ON if show_predefined_fields else OFF,
            connectors=ON if show_connectors else OFF,
            constraints=ON if show_constraints else OFF,
            interactions=ON if show_interactions else OFF,
        )

        resolved_step = step_name
        if resolved_step is None:
            non_initial = [s for s in model.steps.keys() if s != "Initial"]
            resolved_step = non_initial[0] if non_initial else "Initial"
        try:
            vp.assemblyDisplay.setValues(step=resolved_step)
        except Exception:
            pass  

        if visible_instances:
            vp.assemblyDisplay.setValues(visibleInstances=tuple(visible_instances))


        vp.viewportAnnotationOptions.setValues(
            triad=ON if show_annotations else OFF,
            legend=ON if show_annotations else OFF,
            title=ON if show_annotations else OFF,
            state=ON if show_annotations else OFF,
        )
        session.printOptions.setValues(vpDecorations=ON if show_annotations else OFF)


        if background_color:
            session.graphicsOptions.setValues(backgroundStyle=SOLID, backgroundColor=background_color)


        if camera_position is not None:
            vp.view.setValues(
                cameraPosition=camera_position,
                cameraTarget=camera_target,
                cameraUpVector=camera_up_vector,
                projection=PROJECTIONS[projection],
            )
        else:
            try:
                vp.view.setValues(session.views[predefined_view])
            except KeyError:
                pass 

        if auto_fit:
            vp.view.fitView()

        if view_width:
            vp.view.setValues(width=view_width)


        session.pngOptions.setValues(imageSize=(image_width, image_height))


        session.printToFile(
            fileName=output_image_path,
            format=PNG,
            canvasObjects=(vp,),
        )

    finally:
        if not keep_model_in_db:
            del mdb.models[model_name]

    return output_image_path




if __name__ == "__main__":
    
    capture_abaqus_model_screenshot(
        inp_file_path = __INP_FILE_PATH__
        output_image_path = __OUTPUT_IMAGE_PATH__

        model_name = __MODEL_NAME__
        step_name = __STEP_NAME__                  
        keep_model_in_db = __KEEP_MODEL_IN_DB__          
                                        
        camera_position = __CAMERA_POSITION__            
        camera_target = __CAMERA_TARGET__              
        camera_up_vector = __CAMERA_UP_VECTOR__
        predefined_view = __PREDEFINED_VIEW__          
        projection = __PROJECTION__           
        auto_fit = __AUTO_FIT__                   
        view_width = __VIEW_WIDTH__                

        show_loads = __SHOW_LOADS__
        show_bcs = __SHOW_BCS__
        show_mesh = __SHOW_MESH__
        show_predefined_fields = __SHOW_PREDEFINED_FIELDS__
        show_connectors = __SHOW_CONNECTORS__
        show_constraints = __SHOW_CONSTRAINTS__
        show_interactions = __SHOW_INTERACTIONS__
        visible_instances = __VISIBLE_INSTANCES__         
        render_style = __RENDER_STYLE__        
        show_annotations = __SHOW_ANNOTATIONS__          

        background_color = __BACKGROUND_COLOR__           
        image_width = __IMAGE_WIDTH__
        image_height = __IMAGE_HEIGHT__ 
    )
"""