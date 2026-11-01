"""
Loads an Abaqus .inp file into a scratch model and renders a screenshot of
the assembly to an image file, with configurable camera placement,
load/BC/mesh visibility, render style, and output resolution/format.
"""

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
        inp_file_path=r"C:\Users\RAGHUL\Documents\Abaqus Scripts\e2.inp",
        output_image_path=r"C:\Users\RAGHUL\Documents\Abaqus Scripts\e2_iso.png",
        predefined_view="Iso",
        show_loads=True,
        show_bcs=True,
        render_style="SHADED",
        image_width=1920,
        image_height=1080,
        background_color="#FFFFFF",
    )

    capture_abaqus_model_screenshot(
        inp_file_path=r"C:\Users\RAGHUL\Documents\Abaqus Scripts\e2.inp",
        output_image_path=r"C:\Users\RAGHUL\Documents\Abaqus Scripts\e2_custom_view.png",
        camera_position=(500.0, 300.0, 400.0),
        camera_target=(0.0, 0.0, 0.0),
        camera_up_vector=(0.0, 0.0, 1.0),
        projection="PERSPECTIVE",
        show_loads=False,
        show_bcs=True,
        render_style="HIDDEN",
        visible_instances=["BACKHOUSING-1", "FRONTHOUSING-1"],
        image_width=2560,
        image_height=1440,
    )