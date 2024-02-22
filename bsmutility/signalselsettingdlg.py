import wx
import wx.py.dispatcher as dp
from propgrid import PropControl, PropGrid, TextValidator, PropSeparator
from .autocomplete import AutocompleteTextCtrl
from .utility import get_tree_item_path

class PropAutoCompleteEditBox(PropControl):
    def __init__(self, completer, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self.completer = completer

    def doCreateControl(self):
        """create the control"""
        if self.window is not None:
            return self.window
        style = wx.TE_PROCESS_ENTER
        sz = self.GetMinSize()
        if sz.y > 50:
            style = wx.TE_MULTILINE
        win = AutocompleteTextCtrl(self.grid, completer=self.completer,
                                   multiline= style & wx.TE_MULTILINE,
                                   value=self.GetValueAsString())
        win.SetInsertionPointEnd()
        if self.formatter:
            validator = TextValidator(self, 'value', self.formatter, False, None)
            win.SetValidator(validator)
        if style & wx.TE_PROCESS_ENTER:
            win.Bind(wx.EVT_TEXT_ENTER, self.OnPropTextEnter)

        return win

    def OnPropTextEnter(self, evt):
        """send when the enter key is pressed in the property control window"""
        if self.window:
            wx.CallAfter(self.OnTextEnter)

    def doGetValueFromWin(self):
        """update the value"""
        if self.window is None:
            return None

        value = None
        if isinstance(self.window, wx.TextCtrl):
            value = self.window.GetValue()

        return value

class SettingDlgBase(wx.Dialog):
    def __init__(self, parent, config=None, title='Settings ...',
                 size=wx.DefaultSize, pos=wx.DefaultPosition,
                 style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        wx.Dialog.__init__(self)
        self.SetExtraStyle(wx.DIALOG_EX_CONTEXTHELP)
        self.Create(parent, title=title, pos=pos, size=size, style=style)

        self.config = config
        if '.' in self.config:
            self.config = self.config.split('.')
        assert not self.config or len(self.config) == 2

        self.propgrid = PropGrid(self)
        g = self.propgrid
        g.Draggable(False)
        g.SetFocus()

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(g, 1, wx.EXPAND|wx.ALL, 1)

        # ok/cancel button
        btnsizer = wx.StdDialogButtonSizer()
        btnsizer.AddStretchSpacer(1)

        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)

        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        sizer.Add(btnsizer, 0, wx.ALL|wx.EXPAND, 5)

        self.SetSizer(sizer)

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

    def OnContextMenu(self, event):
        # it is necessary, otherwise when right click on the dialog, the context
        # menu of the MatplotPanel will show; it may be due to some 'bug' in
        # CaptureMouse/ReleaseMouse (canvas is a panel that capture mouse)
        # and we also need to release the mouse before show the MatplotPanel
        # context menu (wchich will eventually show this dialog)
        pass

    def SetConfig(self, settings):
        if not self.config:
            return
        dp.send('frame.set_config', group=self.config[0], **{self.config[1]: settings})

    def LoadConfig(self):
        if not self.config:
            return None
        resp = dp.send('frame.get_config', group=self.config[0], key=self.config[1])
        if resp and resp[0][1] is not None:
            return resp[0][1]
        return None

    def GetSettings(self):
        settings = {}
        for i in range(self.propgrid.GetCount()):
            p = self.propgrid.Get(i)
            if p.IsSeparator():
                continue
            name = p.GetName()
            if p:
                settings[name] = p.GetValue()

        self.SetConfig(settings)
        return settings


class SignalSelSettingDlg(SettingDlgBase):
    def __init__(self, parent, data=None, items=None, values=None,
                 config=None, additional=None, title='Settings ...',
                 size=wx.DefaultSize, pos=wx.DefaultPosition,
                 style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        SettingDlgBase.__init__(self, parent, config, title, size, pos, style)

        self.data = data
        self.items = items or []
        self.additional = additional or []
        g = self.propgrid
        cfg = self.LoadConfig() or {}
        if values:
            cfg.update(values)
        g.Insert(PropSeparator().Label('Input'))
        for item in items:
            g.Insert(PropAutoCompleteEditBox(self.completer).Label(item)
                     .Name(item).Value(cfg.get(item, '')))
        for p in additional:
            value = cfg.get(p.GetName(), None)
            if value is not None:
                p.Value(value)
            g.Insert(p)

    def completer(self, query):
        path = get_tree_item_path(query)
        d = self.data
        for p in path[:-1]:
            if p in d:
                d = d[p]
        objs = [k for k in d if k.startswith(path[-1])]
        return objs, objs, len(path[-1])

class PropSettingDlg(SettingDlgBase):
    def __init__(self, parent, props=None, config=None, title='Settings ...',
                 size=wx.DefaultSize, pos=wx.DefaultPosition,
                 style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        SettingDlgBase.__init__(self, parent, config, title, size, pos, style)

        g = self.propgrid
        cfg = self.LoadConfig() or {}
        for p in props:
            value = cfg.get(p.GetName(), None)
            if value is not None:
                p.Value(value)
            g.Insert(p)
