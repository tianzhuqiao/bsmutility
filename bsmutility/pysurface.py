from .surface import SurfacePanel, GLSurface

def gcs():
    '''
    Get the current glsurface window, and create one if there is no one available
    '''
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

def surface(points, clear=True):
    pane = gcs()
    if pane is not None:
        pane.plot(points, clear=clear)
