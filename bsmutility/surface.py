import platform
import wx
import wx.py.dispatcher as dp
import aui2 as aui
from glsurface.glsurface import TrackingSurface
from .bsmxpm import pause_svg, pause_grey_svg, run_svg, run_grey_svg, more_svg, \
                    forward_svg, forward_gray_svg, backward_svg, backward_gray_svg, \
                    save_svg, save_gray_svg, copy_svg, copy_gray_svg, new_page_svg
from .pymgr_helpers import Gcm
from .utility import svg_to_bitmap
from .fileviewbase import PanelBase
from .bsminterface import InterfaceRename


class Surface(TrackingSurface):
    def __init__(self, *args, **kwargs):
        TrackingSurface.__init__(self, *args, **kwargs)

        self.SetShowStepSurface(False)
        self.SetShowMode(mesh=True)

    def GetContextMenu(self):
        menu = super().GetContextMenu()
        menu.AppendSeparator()
        menu.Append(wx.ID_CLEAR, 'Clear')
        if platform.system() == 'Linux':
            menu.Append(wx.ID_RESET, 'Reset')
        return menu

    def OnProcessMenuEvent(self, event):
        eid = event.GetId()
        if eid == wx.ID_CLEAR:
            self.Clear()
        elif eid == wx.ID_RESET:
            try:
                parent = self.GetTopLevelParent()
                msg = 'Would you like to re-create  drawing surface?'
                dlg = wx.MessageDialog(self, msg, parent.GetLabel(), wx.YES_NO)
                dlg.SetExtendedMessage("Only call this if the drawing surface is messed up; otherwise, it may crash!")
                if dlg.ShowModal() == wx.ID_YES:
                    self.CreateSurface()
                    self.Update()
            except:
                pass
        else:
            super().OnProcessMenuEvent(event)

class DataDropTarget(wx.DropTarget):
    def __init__(self, canvas):
        wx.DropTarget.__init__(self)
        self.obj = wx.TextDataObject()
        self.SetDataObject(self.obj)
        self.canvas = canvas
        self.SetDefaultAction(wx.DragMove)

    def OnEnter(self, x, y, d):
        #self.canvas.OnEnter(x, y, d)
        return d

    def OnLeave(self):
        #self.frame.OnLeave()
        pass

    def OnDrop(self, x, y):
        return True

    def OnData(self, x, y, d):
        if not self.GetData():
            return wx.DragNone
        dp.send('graph.drop', axes=self.canvas, allowed=True)
        return d

    def OnDragOver(self, x, y, d):
        #self.frame.OnDragOver(x, y, d)
        return d


class SurfacePanel(PanelBase):
    Gcc = Gcm()
    ID_RUN = wx.NewIdRef()
    ID_PAUSE = wx.NewIdRef()
    ID_MORE = wx.NewIdRef()
    ID_SHOW_SLIDER = wx.NewIdRef()
    ID_FORWARD = wx.NewIdRef()
    ID_BACKWARD = wx.NewIdRef()

    def __init__(self, parent, title, num):
        PanelBase.__init__(self, parent, title, num=num)

        sizer = wx.BoxSizer(wx.VERTICAL)

        tb = aui.AuiToolBar(self,
                            -1,
                            wx.DefaultPosition,
                            wx.DefaultSize,
                            agwStyle=aui.AUI_TB_OVERFLOW
                            | aui.AUI_TB_PLAIN_BACKGROUND)
        tb.SetToolBitmapSize(wx.Size(16, 16))
        if platform.system() != 'Linux':
            tb.AddSimpleTool(wx.ID_NEW, 'New window', bitmap=svg_to_bitmap(new_page_svg, win=self),
                             short_help_string='Create a new glsurface window')
            tb.AddSeparator()
        tb.AddTool(wx.ID_SAVE, "Save", bitmap=svg_to_bitmap(save_svg, win=self),
                   disabled_bitmap=svg_to_bitmap(save_gray_svg, win=self),
                   kind=aui.ITEM_NORMAL,
                   short_help_string="Save to file")
        tb.AddTool(wx.ID_COPY, "Copy", bitmap=svg_to_bitmap(copy_svg, win=self),
                   disabled_bitmap=svg_to_bitmap(copy_gray_svg, win=self),
                   kind=aui.ITEM_NORMAL,
                   short_help_string="Copy to clipboard")

        tb.AddStretchSpacer()
        tb.AddTool(self.ID_MORE, "More", svg_to_bitmap(more_svg, win=self),
                        wx.NullBitmap, wx.ITEM_NORMAL, "More")
        tb.Realize()
        sizer.Add(tb, 0, wx.EXPAND, 0)

        self.canvas = Surface(self, None)
        sizer.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 0)
        self.tbSlider = aui.AuiToolBar(self,
                                       -1,
                                       wx.DefaultPosition,
                                       wx.DefaultSize,
                                       agwStyle=aui.AUI_TB_OVERFLOW
                                       | aui.AUI_TB_PLAIN_BACKGROUND)
        self.tbSlider.AddTool(self.ID_RUN, "Play", bitmap=svg_to_bitmap(run_svg, win=self),
                              disabled_bitmap=svg_to_bitmap(run_grey_svg, win=self),
                              kind=aui.ITEM_NORMAL,
                              short_help_string="Play")
        self.tbSlider.AddTool(self.ID_PAUSE, "Pause", bitmap=svg_to_bitmap(pause_svg, win=self),
                              disabled_bitmap=svg_to_bitmap(pause_grey_svg, win=self),
                              kind=aui.ITEM_NORMAL,
                              short_help_string="Pause")
        self.tbSlider.AddTool(self.ID_BACKWARD, "Back", bitmap=svg_to_bitmap(backward_svg, win=self),
                              disabled_bitmap=svg_to_bitmap(backward_gray_svg, win=self),
                              kind=aui.ITEM_NORMAL,
                              short_help_string="Go to previous frame")

        self.tbSlider.AddTool(self.ID_FORWARD, "Forward", bitmap=svg_to_bitmap(forward_svg, win=self),
                              disabled_bitmap=svg_to_bitmap(forward_gray_svg, win=self),
                              kind=aui.ITEM_NORMAL,
                              short_help_string="Go to next frame")
        self.slider = wx.Slider(self.tbSlider, 0, style=wx.SL_HORIZONTAL | wx.SL_TOP)
        item = self.tbSlider.AddControl(self.slider)
        item.SetProportion(1)
        self.slider.SetRange(-self.canvas.GetBufLen()+1, 0)
        self.tbSlider.Realize()
        self.tbSlider.Hide()
        sizer.Add(self.tbSlider, 0, wx.EXPAND | wx.ALL, 0)
        self.SetSizer(sizer)

        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateTool)
        self.Bind(wx.EVT_TOOL, self.OnProcessTool)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.slider.Bind(wx.EVT_SCROLL, self.OnSelectFrame)
        #self.timer.Start(100)
        self.is_running = False
        self.last_frame_id = -1

        self.title = title

        accel_tbl = [
            (wx.ACCEL_CTRL, ord('S'), wx.ID_SAVE),
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY),
        ]

        self.SetAcceleratorTable(wx.AcceleratorTable(accel_tbl))

        dt = DataDropTarget(self)
        self.canvas.SetDropTarget(dt)

        dp.connect(self.DataUpdated, 'graph.data_updated')

    def Destroy(self):
        dp.disconnect(self.DataUpdated, 'graph.data_updated')
        super().Destroy()

    def DataUpdated(self):
        if not hasattr(self, 'trace_signal'):
            return

        resp = dp.send(**self.trace_signal, last_frame_id=self.last_frame_id)
        if not resp:
            return

        # ignore the zmq when different "num"
        resp = [r for r in resp if len(r[1]) == 3 and r[1][0] is not None and r[1][1] is not None]
        if not resp:
            return

        x, y, self.last_frame_id = resp[0][1]
        if x is None or y is None:
            return

        self.plot(y, clear=False)

    def UpdateSlider(self, value):
        self.slider.SetValue(value)
        self.canvas.SetCurrentFrame(value)

    def OnSelectFrame(self, event):
        self.canvas.SetCurrentFrame(self.slider.GetValue())

    def GetCaption(self):
        return self.title or f"glsurface-{self.num}"

    def OnUpdateTool(self, event):
        eid = event.GetId()
        multi_frame = self.canvas.frames is not None and self.canvas.GetBufLen() > 1
        if multi_frame:
            # update the slider range
            rng = self.slider.GetRange()
            if rng[1] - rng[0] + 1 != self.canvas.GetBufLen():
                self.slider.SetRange(-self.canvas.GetBufLen()+1, 0)
                self.UpdateSlider(0)

        if eid == self.ID_RUN:
            event.Enable(not self.is_running and multi_frame)
            self.slider.Enable(multi_frame)
        elif eid == self.ID_PAUSE:
            event.Enable(self.is_running)
        elif eid == self.ID_BACKWARD:
            event.Enable(multi_frame and self.slider.GetValue() > self.slider.GetMin())
        elif eid == self.ID_FORWARD:
            event.Enable(multi_frame and self.slider.GetValue() < self.slider.GetMax())
        else:
            event.Skip()

    def ShowSlider(self, show=True):
        self.tbSlider.Show(show)
        self.Layout()

    def OnProcessTool(self, event):
        eid = event.GetId()
        if eid == self.ID_RUN:
            self.is_running = True
            self.timer.Start(50)
        elif eid == self.ID_PAUSE:
            self.is_running = False
            self.timer.Stop()
        elif eid == self.ID_MORE:
            menu = wx.Menu()
            mitem = menu.AppendCheckItem(self.ID_SHOW_SLIDER, "Show slider bar")
            mitem.Check(self.tbSlider.IsShown())
            self.PopupMenu(menu)
        elif eid == self.ID_SHOW_SLIDER:
            self.ShowSlider(not self.tbSlider.IsShown())
        elif eid == self.ID_BACKWARD:
            self.UpdateSlider(self.slider.GetValue()-1)
        elif eid == self.ID_FORWARD:
            self.UpdateSlider(self.slider.GetValue()+1)
        elif eid == wx.ID_COPY:
            bitmap = self.canvas.GetBitmap()
            if bitmap is None:
                print('No bitmap available')
                return
            bmp_obj = wx.BitmapDataObject()
            bmp_obj.SetBitmap(bitmap)
            if not wx.TheClipboard.IsOpened():
                open_success = wx.TheClipboard.Open()
                if open_success:
                    wx.TheClipboard.SetData(bmp_obj)
                    wx.TheClipboard.Flush()
                    wx.TheClipboard.Close()
        elif eid == wx.ID_SAVE:
            self.doSave()
        elif eid == wx.ID_NEW:
            GLSurface.AddFigure()
        else:
            event.Skip()

    def doSave(self):
        wildcard = [
                [wx.BITMAP_TYPE_BMP, 'Windows bitmap (*.bmp)|*.bmp'],
                [wx.BITMAP_TYPE_XBM, 'X BitMap (*.xbm)|*.xbm'],
                [wx.BITMAP_TYPE_XPM, 'X pixmap (*.xpm)|*.xpm'],
                [wx.BITMAP_TYPE_TIFF, 'Tagged Image Format File (*.tif;*.tiff)|*.tif;*.tiff'],
                [wx.BITMAP_TYPE_GIF, 'Graphics Interchange Format (*.gif)|*.gif'],
                [wx.BITMAP_TYPE_PNG, 'Portable Network Graphics (*.png)|*.png'],
                [wx.BITMAP_TYPE_JPEG, 'JPEG (*.jpeg;*.jpg)|*.jpeg;*.jpg'],
                [wx.BITMAP_TYPE_PNM, 'Portable Anymap (*.pnm)|*.pnm'],
                [wx.BITMAP_TYPE_PCX, 'PCX (*.pcx)|*.pc'],
                [wx.BITMAP_TYPE_PICT, 'Macintosh PICT (*.pict)|*.pict'],
                ]
        dlg = wx.FileDialog(self, "Save XYZ file", wildcard='|'.join([w[1] for w in wildcard]),
                       style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        dlg.SetFilterIndex(5)
        if dlg.ShowModal() == wx.ID_CANCEL:
            return     # the user changed their mind

        # save the current contents in the file
        pathname = dlg.GetPath()
        filterIndex = dlg.GetFilterIndex()
        fileTypes = [w[0] for w in wildcard]
        if filterIndex < 0 or filterIndex >= len(fileTypes):
            print("Unsupported file format!")
            return
        bitmap = self.canvas.GetBitmap()
        if bitmap:
            bitmap.SaveFile(pathname, fileTypes[filterIndex])
        else:
            print("No bitmap available!")

    def OnTimer(self, event):
        if self.slider.GetValue() >= self.slider.GetMax():
            self.is_running = False
            self.timer.Stop()
            return
        self.UpdateSlider(self.slider.GetValue()+1)


    def plot(self, points, clear=True):
        if clear:
            self.canvas.SetFrames(points, reset_buf_len=True, silent=False)
            # update the slider
            self.slider.SetRange(-self.canvas.GetBufLen()+1, 0)
            self.UpdateSlider(0)
            if self.canvas.frames is not None and self.canvas.GetBufLen() > 1:
                # show slider if needed
                self.ShowSlider(True)
        else:
            if len(points.shape) == 3:
                shape = list(points.shape)
                for f in range(shape[0]):
                    self.canvas.NewFrameArrive(points[f, :, :], silent=False)
            else:
                self.canvas.NewFrameArrive(points, silent=False)


class GLSurface(InterfaceRename):
    kwargs = {}
    ID_NEW_FIGURE = wx.NOT_FOUND
    ID_PANE_CLOSE = wx.NewIdRef()
    ID_PANE_CLOSE_OTHERS = wx.NewIdRef()
    ID_PANE_CLOSE_ALL = wx.NewIdRef()
    MENU_NEW_FIG = 'File:New:glsurface\tCtrl+G'

    icon = None

    @classmethod
    def initialize(cls, frame, **kwargs):
        super().initialize(frame, **kwargs)
        cls.kwargs = kwargs

        resp = dp.send('frame.add_menu',
                       path=cls.MENU_NEW_FIG,
                       rxsignal='bsm.glsurface')
        if resp:
            cls.ID_NEW_FIGURE = resp[0][1]

        if cls.ID_NEW_FIGURE is not wx.NOT_FOUND:
            dp.connect(cls.ProcessCommand, 'bsm.glsurface')
        dp.connect(cls.SetActive, 'frame.activate_panel')
        dp.connect(cls.OnBufferChanged, 'sim.buffer_changed')
        dp.connect(cls.PaneMenu, 'bsm.glsurface.pane_menu')

        #cls.icon = svg_to_bitmap(polyline_svg, win=frame)

    @classmethod
    def initialized(cls):
        # add glsurface interface to the shell
        dp.send(signal='shell.run',
                command='from bsmutility.pysurface import *',
                prompt=False,
                verbose=False,
                history=False)

    @classmethod
    def PaneMenu(cls, pane, command):
        if not pane or not isinstance(pane.window, SurfacePanel):
            return
        if command == cls.ID_PANE_CLOSE:
            dp.send(signal='frame.delete_panel', panel=pane.window)
        elif command == cls.ID_PANE_CLOSE_OTHERS:
            mgrs = SurfacePanel.Gcc.get_all_managers()
            for mgr in mgrs:
                if mgr == pane.window:
                    continue
                dp.send(signal='frame.delete_panel', panel=mgr)
        elif command == cls.ID_PANE_CLOSE_ALL:
            mgrs = SurfacePanel.Gcc.get_all_managers()
            for mgr in mgrs:
                dp.send(signal='frame.delete_panel', panel=mgr)
        elif command == cls.ID_PANE_RENAME:
            cls.RenamePane(pane)

    @classmethod
    def OnBufferChanged(cls, bufs):
        """the buffer has be changes, update the plot_trace"""
        for p in SurfacePanel.Gcc.get_all_managers():
            p.update_buffer(bufs)

    @classmethod
    def SetActive(cls, pane):
        if pane and isinstance(pane, SurfacePanel):
            if SurfacePanel.Gcc.get_active() == pane:
                return
            SurfacePanel.Gcc.set_active(pane)

    @classmethod
    def uninitializing(cls):
        super().uninitializing()
        # before save perspective
        for mgr in SurfacePanel.Gcc.get_all_managers():
            dp.send('frame.delete_panel', panel=mgr)
        dp.send('frame.delete_menu', path=cls.MENU_NEW_FIG, id=cls.ID_NEW_FIGURE)

    @classmethod
    def uninitialized(cls):
        dp.disconnect(cls.SetActive, 'frame.activate_panel')
        dp.disconnect(cls.OnBufferChanged, 'sim.buffer_changed')
        dp.disconnect(cls.PaneMenu, 'bsm.glsurface.pane_menu')
        super().uninitialized()

    @classmethod
    def ProcessCommand(cls, command):
        """process the menu command"""
        if command == cls.ID_NEW_FIGURE:
            cls.AddFigure()

    @classmethod
    def AddFigure(cls, title=None, num=None):

        if SurfacePanel.Gcc.has_num(num):
            return SurfacePanel.Gcc.get_manager(num=num)

        fig = SurfacePanel(cls.frame, title, num)
        direction = cls.kwargs.get('direction', 'top')
        # set the minsize to be large enough to avoid some following assert; it
        # will not eliminate all as if a page is added to a notebook, the
        # minsize of notebook is not the max of all its children pages (check
        # frameplus.py).
        # wxpython/ext/wxWidgets/src/gtk/bitmap.cpp(539): assert ""width > 0 &&
        # height > 0"" failed in Create(): invalid bitmap size
        dp.send('frame.add_panel',
                panel=fig,
                direction=direction,
                title=fig.GetCaption(),
                target=SurfacePanel.Gcc.get_active(),
                minsize=(75, 75),
                pane_menu={'rxsignal': 'bsm.glsurface.pane_menu',
                           'menu': [
                               {'id':cls.ID_PANE_RENAME, 'label':'Rename'},
                               {'type': wx.ITEM_SEPARATOR},
                               {'id':cls.ID_PANE_CLOSE, 'label':'Close\tCtrl+W'},
                               {'id':cls.ID_PANE_CLOSE_OTHERS, 'label':'Close Others'},
                               {'id':cls.ID_PANE_CLOSE_ALL, 'label':'Close All'},
                               ]},
                icon=cls.icon)
        return fig


def surface(points):
    pane = SurfacePanel.Gcc.get_active()
    if pane is None:
        pane = GLSurface.AddFigure()
    if pane is None:
        print('Fail to create glsurface window')
        return
    pane.canvas.NewFrameArrive(points, False)
