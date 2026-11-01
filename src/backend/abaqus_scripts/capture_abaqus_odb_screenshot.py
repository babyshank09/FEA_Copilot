"""
capture_odb_screenshot.py

Loads an Abaqus .odb file and renders a screenshot of it to a PNG file,
with configurable camera placement, step/frame selection, contour/
deformed-shape display, and output resolution.

-------------------------------------------------------------------------
IMPORTANT -- HOW TO RUN THIS
-------------------------------------------------------------------------
Same as the .inp screenshot script: this needs Abaqus/CAE's Visualization
kernel (`session`, `Viewport`), which only exists inside the CAE kernel.
Run with:

    abaqus cae noGUI=capture_odb_screenshot.py

-------------------------------------------------------------------------
WHY THIS ISN'T JUST THE .inp SCRIPT WITH A DIFFERENT FILE EXTENSION
-------------------------------------------------------------------------
An .odb has no Load/BoundaryCondition objects -- those are pre-processing
concepts that live on a Model, not on a results database. What's actually
worth visualizing on an odb is a CONTOUR PLOT of a result field on the
deformed (or undeformed) shape, for a specific step/frame -- so that
replaces the show_loads/show_bcs toggles from the .inp version. Loading
mechanism is different too: odbs are opened with session.openOdb (not
mdb.ModelFromInputFile), and displayed via vp.odbDisplay (not
vp.assemblyDisplay).

-------------------------------------------------------------------------
WHY DELETING THE ODB IS HANDLED THE SAME CAUTIOUS WAY AS THE .inp SCRIPT
-------------------------------------------------------------------------
Same class of bug as before: closing an odb while a viewport still
displays it leaves Abaqus/CAE holding a dangling reference, which can
crash the kernel on the next viewport operation (especially noticeable
across repeated calls in one interactive GUI session). This function
always clears vp.displayedObject back to None before opening/closing any
odb, both defensively at the start and during cleanup.

-------------------------------------------------------------------------
VISIBLE INSTANCES
-------------------------------------------------------------------------
Restricting which part instances are shown works differently for an odb
than for a model: instead of a simple visibleInstances kwarg, it goes
through Abaqus's DisplayGroup mechanism (displayGroupOdbToolset.
LeafFromPartInstance). If you pass names that don't actually exist in
the odb's assembly, this raises a clear ValueError listing the real
instance names up front, rather than letting Abaqus fail silently or
obscurely later.
"""

from abaqus import session
import visualization
import displayGroupOdbToolset as dgo
from abaqusConstants import (
    ON, OFF,
    PARALLEL, PERSPECTIVE,
    WIREFRAME, HIDDEN, SHADED, FILLED,
    PNG,
    SOLID,
    UNDEFORMED, DEFORMED, CONTOURS_ON_DEF, CONTOURS_ON_UNDEF,
    SYMBOLS_ON_DEF, SYMBOLS_ON_UNDEF,
    NODAL, INTEGRATION_POINT, ELEMENT_NODAL,
    INVARIANT, COMPONENT,
    FEATURE, ALL,
    UNIFORM,
)

RENDER_STYLES = {"WIREFRAME": WIREFRAME, "HIDDEN": HIDDEN, "SHADED": SHADED, "FILLED": FILLED}
PROJECTIONS = {"PARALLEL": PARALLEL, "PERSPECTIVE": PERSPECTIVE}
PLOT_STATES = {
    "UNDEFORMED": UNDEFORMED,
    "DEFORMED": DEFORMED,
    "CONTOURS_ON_DEF": CONTOURS_ON_DEF,
    "CONTOURS_ON_UNDEF": CONTOURS_ON_UNDEF,
    "SYMBOLS_ON_DEF": SYMBOLS_ON_DEF,
    "SYMBOLS_ON_UNDEF": SYMBOLS_ON_UNDEF,
}
OUTPUT_POSITIONS = {
    "NODAL": NODAL,
    "INTEGRATION_POINT": INTEGRATION_POINT,
    "ELEMENT_NODAL": ELEMENT_NODAL,
}


def capture_abaqus_odb_screenshot(
    odb_file_path,
    output_image_path,

    step_name=None,                 
    frame_index=-1,                 

    plot_state=("CONTOURS_ON_DEF",), 
                                      
    field_variable=None,             
    field_invariant=None,            
    field_component=None,            
    output_position="INTEGRATION_POINT",  
                                           
    deformation_scale_factor=None,   
                                    

    camera_position=None,            
    camera_target=None,              
    camera_up_vector=(0.0, 0.0, 1.0),
    predefined_view="Iso",         
    projection="PARALLEL",          
    auto_fit=True,
    view_width=None,                

    render_style="SHADED",          
    show_mesh=False,                 
    visible_instances=None,          
    show_annotations=False,          
    background_color=None,           

    image_width=1920,
    image_height=1080,

    close_odb_after=True,            
):
    if render_style not in RENDER_STYLES:
        raise ValueError("render_style must be one of {}".format(list(RENDER_STYLES.keys())))
    if projection not in PROJECTIONS:
        raise ValueError("projection must be one of {}".format(list(PROJECTIONS.keys())))
    if output_position not in OUTPUT_POSITIONS:
        raise ValueError("output_position must be one of {}".format(list(OUTPUT_POSITIONS.keys())))
    if camera_position is not None and camera_target is None:
        raise ValueError("camera_target is required when camera_position is given")
    if field_invariant and field_component:
        raise ValueError("field_invariant and field_component are mutually exclusive")
    bad_states = [p for p in plot_state if p not in PLOT_STATES]
    if bad_states:
        raise ValueError("plot_state contains unknown values {}; valid options are {}".format(
            bad_states, list(PLOT_STATES.keys())))


    vp_name = list(session.viewports.keys())[0]
    vp = session.viewports[vp_name]
    try:
        vp.setValues(displayedObject=None)
    except Exception:
        pass


    if odb_file_path in session.odbs:
        try:
            session.odbs[odb_file_path].close()
        except Exception:
            pass
    odb = session.openOdb(name=odb_file_path, readOnly=True)

    try:

        vp.setValues(displayedObject=odb)


        if visible_instances:
            available = list(odb.rootAssembly.instances.keys())
            unknown = [n for n in visible_instances if n not in available]
            if unknown:
                raise ValueError(
                    "visible_instances contains unknown instance name(s) {}. "
                    "Available instances in this odb: {}".format(unknown, available)
                )
            leaf = dgo.LeafFromPartInstance(partInstanceName=tuple(visible_instances))
            vp.odbDisplay.displayGroup.replace(leaf=leaf)


        step_keys = list(odb.steps.keys())
        if not step_keys:
            raise RuntimeError("odb has no steps: {}".format(odb_file_path))
        resolved_step_name = step_name if step_name is not None else step_keys[0]
        if resolved_step_name not in odb.steps:
            raise ValueError("step_name '{}' not found. Available steps: {}".format(
                resolved_step_name, step_keys))
        step_index = step_keys.index(resolved_step_name)

        num_frames = len(odb.steps[resolved_step_name].frames)
        resolved_frame = frame_index if frame_index >= 0 else num_frames + frame_index
        if not (0 <= resolved_frame < num_frames):
            raise ValueError("frame_index {} out of range for step '{}' ({} frames)".format(
                frame_index, resolved_step_name, num_frames))

        vp.odbDisplay.setFrame(step=step_index, frame=resolved_frame)


        vp.odbDisplay.display.setValues(plotState=tuple(PLOT_STATES[p] for p in plot_state))


        if field_variable:
            kwargs = {
                "variableLabel": field_variable,
                "outputPosition": OUTPUT_POSITIONS[output_position],
            }
            if field_invariant:
                kwargs["refinement"] = (INVARIANT, field_invariant)
            elif field_component:
                kwargs["refinement"] = (COMPONENT, field_component)
            vp.odbDisplay.setPrimaryVariable(**kwargs)


        if deformation_scale_factor is not None:
            vp.odbDisplay.commonOptions.setValues(
                deformationScaling=UNIFORM, uniformScaleFactor=deformation_scale_factor)


        vp.odbDisplay.commonOptions.setValues(
            renderStyle=RENDER_STYLES[render_style],
            visibleEdges=ALL if show_mesh else FEATURE,
        )

      
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
        if close_odb_after:
            try:
                vp.setValues(displayedObject=None)
            except Exception:
                pass
            try:
                odb.close()
            except Exception:
                pass

    return output_image_path


if __name__ == "__main__":
    capture_abaqus_odb_screenshot(
        odb_file_path=r"C:\Users\RAGHUL\Documents\Abaqus_Scripts\Assets\e2.odb",
        output_image_path=r"C:\Users\RAGHUL\Documents\Abaqus_Scripts\e2_mises_contour.png",
        step_name=None,
        frame_index=4,
        plot_state=("CONTOURS_ON_DEF",),
        field_variable="S",
        field_invariant="Mises",
        deformation_scale_factor=1.0,
        predefined_view="Iso",
        render_style="SHADED",
        show_annotations=True,  
        image_width=1920,
        image_height=1080,
        background_color="#FFFFFF",
    )

    capture_abaqus_odb_screenshot(
        odb_file_path=r"C:\Users\RAGHUL\Documents\Abaqus_Scripts\Assets\e2.odb",
        output_image_path=r"C:\Users\RAGHUL\Documents\Abaqus_Scripts\e2_undeformed.png",
        plot_state=("CONTOURS_ON_DEF",),
        frame_index=4,
        camera_position=(500.0, 300.0, 400.0),
        camera_target=(0.0, 0.0, 0.0),
        projection="PERSPECTIVE",
        render_style="SHADED",
        show_annotations=True, 
        show_mesh=True, 
        visible_instances=["PCB", "CHIP"],
        image_width=2560,
        image_height=1440,
    )
