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
        if clear:
            pane.canvas.SetFrames(points, reset_buf_len=True, silent=False)
        else:
            pane.canvas.NewFrameArrive(points, silent=False)

        if pane.canvas.frames is not None and pane.canvas.frames.shape[0] > 1:
            pane.ShowSlider(True)
