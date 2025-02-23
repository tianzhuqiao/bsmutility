import os
import six
import wx
import wx.py.dispatcher as dp
import wx.lib.mixins.listctrl as listmix
import aui2 as aui
from .bsmxpm import (run_svg, run_grey_svg, step_over_svg, step_over_grey_svg,
                     step_into_svg, step_into_grey_svg, step_out_svg,
                     step_out_grey_svg, stop_svg, stop_grey_svg, layer_svg)

from .utility import svg_to_bitmap
from .bsminterface import Interface

class StackListCtrl(wx.ListCtrl, listmix.ListCtrlAutoWidthMixin,
                    listmix.ListRowHighlighter):
    def __init__(self, *args, **kwargs):
        wx.ListCtrl.__init__(self, *args, **kwargs)

        listmix.ListCtrlAutoWidthMixin.__init__(self)
        listmix.ListRowHighlighter.__init__(self, mode=listmix.HIGHLIGHT_ODD)
        self.SetHighlightColor(wx.Colour(240, 240, 250))


class StackPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.listctrl = StackListCtrl(self,
                                      style=wx.LC_REPORT
                                      | wx.BORDER_NONE
                                      | wx.LC_VRULES
                                      | wx.LC_HRULES | wx.LC_SINGLE_SEL)
        # | wx.BORDER_SUNKEN
        # | wx.LC_SORT_ASCENDING
        # | wx.LC_NO_HEADER
        self.listctrl.InsertColumn(0, 'Name')
        self.listctrl.InsertColumn(1, 'Line')
        self.listctrl.InsertColumn(2, 'File')
        sizer.Add(self.listctrl, 1, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated,
                  self.listctrl)
        dp.connect(self.OnDebugEnded, 'debugger.ended')
        dp.connect(self.OnDebugUpdateScopes, 'debugger.update_scopes')
        dp.connect(self.OnDebugUpdateScopes, 'debugger.paused')

        self.frames = []

        self.show_all_frames = False
        resp = dp.send('frame.get_config', group='debugtool', key='show_all_frames')
        if resp and resp[0][1] is not None:
            self.show_all_frames = resp[0][1]

    def Destroy(self):
        dp.disconnect(self.OnDebugEnded, 'debugger.ended')
        dp.disconnect(self.OnDebugUpdateScopes, 'debugger.update_scopes')
        dp.disconnect(self.OnDebugUpdateScopes, 'debugger.paused')
        super().Destroy()

    def OnDebugEnded(self):
        """debugger is ended"""
        # clear the scopes
        self.listctrl.DeleteAllItems()

    def OnDebugUpdateScopes(self):
        """debugger changes the scope"""
        self.listctrl.DeleteAllItems()
        resp = dp.send(signal='debugger.get_status')
        if not resp or not resp[0][1]:
            return
        status = resp[0][1]
        frames = status['frames']
        level = status['active_scope']
        self.frames = []
        if frames is not None:
            for l, frame in enumerate(reversed(frames)):
                name = frame.f_code.co_name
                filename = frame.f_code.co_filename
                lineno = frame.f_lineno
                if not self.show_all_frames and filename == '<input>':
                    break
                index = self.listctrl.InsertItem(self.listctrl.GetItemCount(), name)
                filename_short = os.path.relpath(filename)
                if len(filename_short) > len(filename):
                    filename_short = filename
                self.listctrl.SetItem(index, 2, filename_short)
                self.listctrl.SetItem(index, 1, f'{lineno}')
                self.frames.append([name, filename, lineno, len(frames)-1-l])
                self.listctrl.SetItemData(index, len(self.frames)-1)
        level_idx = len(frames)-1-level
        if 0 <= level_idx < self.listctrl.GetItemCount():
            self.listctrl.SetItemTextColour(level_idx, 'blue')
        self.listctrl.RefreshRows()

    def OnItemActivated(self, event):
        item = event.GetIndex()
        index = self.listctrl.GetItemData(item)
        if 0 <=  index < len(self.frames):
            _, filename, lineno, level = self.frames[index]
        else:
            return
        # open the script first
        dp.send(signal='frame.file_drop',
                filename=filename,
                lineno=int(lineno))
        # ask the debugger to trigger the update scope event to set mark
        dp.send(signal='debugger.set_scope', level=level)


class DebugTool(Interface):
    isInitialized = False
    showStackPanel = True

    @classmethod
    def initialize(cls, frame, **kwargs):
        super().initialize(frame, **kwargs)

        # stack panel
        cls.panelStack = StackPanel(frame)
        bmp = svg_to_bitmap(layer_svg, win=cls.panelStack)
        dp.send('frame.add_panel',
                panel=cls.panelStack,
                title="Call Stack",
                active=False,
                showhidemenu='View:Panels:Call Stack',
                name='call_stack',
                icon=bmp)

        # debugger toolbar
        dp.send('frame.add_menu',
                path='Tools:Debug',
                rxsignal='',
                kind='Popup')
        cls.tbDebug = aui.AuiToolBar(frame, agwStyle=aui.AUI_TB_OVERFLOW)
        items = (
            ('Run\tF5', 'resume', run_svg, run_grey_svg, 'paused'),
            ('Stop\tShift-F5', 'stop', stop_svg, stop_grey_svg, 'paused'),
            ('Step\tF10', 'step', step_over_svg, step_over_grey_svg, 'paused'),
            ('Step Into\tF11', 'step_into', step_into_svg, step_into_grey_svg, 'can_stepin'),
            ('Step Out\tShift-F11', 'step_out', step_out_svg, step_out_grey_svg, 'can_stepout'),
        )
        cls.menus = {}
        for label, signal, img, img_grey, status in items:
            resp = dp.send('frame.add_menu',
                           path='Tools:Debug:' + label,
                           rxsignal='debugger.' + signal,
                           updatesignal='debugtool.updateui')
            if not resp:
                continue
            cls.menus[resp[0][1]] = status
            cls.tbDebug.AddTool(resp[0][1], label, svg_to_bitmap(img, win=cls.tbDebug),
                                svg_to_bitmap(img_grey, win=cls.tbDebug), wx.ITEM_NORMAL, label)
        cls.tbDebug.Realize()

        dp.send('frame.add_panel',
                panel=cls.tbDebug,
                title='Debugger',
                active=False,
                paneInfo=aui.AuiPaneInfo().Name('debugger').Caption(
                    'Debugger').ToolbarPane().Top(),
                showhidemenu='View:Toolbars:Debugger',
                name='debug_toolbar')
        dp.connect(cls.OnUpdateMenuUI, 'debugtool.updateui')
        dp.connect(cls.OnDebugPaused, 'debugger.paused')
        dp.connect(cls.OnDebugEnded, 'debugger.ended')

    @classmethod
    def uninitialized(cls):
        """destroy the module"""
        super().uninitialized()
        dp.disconnect(cls.OnUpdateMenuUI, 'debugtool.updateui')
        dp.disconnect(cls.OnDebugPaused, 'debugger.paused')
        dp.disconnect(cls.OnDebugEnded, 'debugger.ended')

    @classmethod
    def OnDebugPaused(cls):
        """update the debug toolbar status"""
        resp = dp.send('debugger.get_status')
        if not resp or not resp[0][1]:
            return
        status = resp[0][1]
        paused = status['paused']
        for k, s in six.iteritems(cls.menus):
            cls.tbDebug.EnableTool(k, paused and status.get(s, False))
        cls.tbDebug.Refresh(False)
        if paused and not cls.tbDebug.IsShown():
            dp.send('frame.show_panel', panel=cls.tbDebug)

        if cls.showStackPanel and paused and not cls.panelStack.IsShownOnScreen():
            dp.send('frame.show_panel', panel=cls.panelStack)
            # allow the use to hide the Stack panel
            cls.showStackPanel = False

    @classmethod
    def OnDebugEnded(cls):
        """debugger is ended"""
        # disable and hide the debugger toolbar
        for k in six.iterkeys(cls.menus):
            cls.tbDebug.EnableTool(k, False)
        cls.tbDebug.Refresh(False)

        # hide the debugger toolbar and Stack panel
        dp.send('frame.show_panel', panel=cls.tbDebug, show=False)
        dp.send('frame.show_panel', panel=cls.panelStack, show=False)
        # show the Stack panel next time
        cls.showStackPanel = True

    @classmethod
    def OnUpdateMenuUI(cls, event):
        """update the debugger toolbar"""
        eid = event.GetId()
        resp = dp.send('debugger.get_status')
        enable = False
        if resp and resp[0][1]:
            status = resp[0][1]
            paused = status['paused']

            s = cls.menus.get(eid, 'paused')

            enable = paused and status[s]
        event.Enable(enable)
