import numpy as np
from .surface import SurfacePanel, GLSurface

def gcs():
    """
    Get the current glsurface window, and create one if there is no one available
    """
    if GLSurface.frame is None:
        print('surface is not initialized')
        return None
    pane = SurfacePanel.Gcc.get_active()
    if pane is None:
        pane = GLSurface.AddFigure()
    if pane is None:
        print('Fail to create glsurface window')
        return None
    return pane

def surface(points=None, clear=True, num=None):
    """
    Create a new glsurface window, or activate an existing one.

    If points is not none, plot it in the glsurface window. If clear is True,
    reset the frame buffer of the glsurface window, otherwise add the points as
    the new frame.
    """
    if num is not None:
        pane = SurfacePanel.Gcc.get_manager(num)
    else:
        pane = gcs()
    if pane is None:
        GLSurface.AddFigure(num=num)
    if pane is not None and points is not None:
        if np.ndim(points) in (2, 3):
            pane.plot(points, clear=clear)
        else:
            print("Error: unsupported data format")

    return pane
