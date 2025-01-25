import wx
import wx.py.dispatcher as dp
import propgrid
from propgrid import PropControl, PropGrid, TextValidator, PropCheckBox, \
                     PropText, PropSeparator
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

    def AllowKeyNavigation(self):
        if self.window is not None and self.window.IsShown():
            return False
        return super().AllowKeyNavigation()

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

        self.SetEscapeId(wx.ID_CANCEL)
        self.config = config
        if self.config and '.' in self.config:
            self.config = self.config.split('.')
        assert not self.config or len(self.config) == 2

        self.propgrid = PropGrid(self)
        g = self.propgrid
        g.GetArtProvider().SetTitleWidth(200)
        g.Draggable(False)
        g.SetFocus()

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(g, 1, wx.EXPAND|wx.ALL, 1)

        # ok/cancel button
        btnsizer = wx.BoxSizer(wx.HORIZONTAL)
        btnsizer.AddStretchSpacer(1)
        for btn in self.CreateButtons():
            btnsizer.Add(btn, 0, wx.ALL, 5)
        sizer.Add(btnsizer, 0, wx.ALL|wx.EXPAND, 15)

        self.SetSizer(sizer)

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self.Bind(propgrid.EVT_PROP_KEYDOWN, self.OnPropKeyDown)
        g.Bind(propgrid.EVT_PROP_RIGHT_CLICK, self.OnRightClick)

    def CreateButtons(self):
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_ok.SetDefault()
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        return [btn_ok, btn_cancel]

    def OnPropKeyDown(self, event):
        data = event.GetData()
        keycode = data.get('keycode', '')
        if keycode in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_SPACE, wx.WXK_ESCAPE] and \
           not wx.GetKeyState(wx.WXK_COMMAND):
            # only allow up/down/space/escape
            return
        event.Veto()

    def OnRightClick(self, event):
        pass

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
            # apply the change from editing
            p.Activated(False)
            if p.IsSeparator():
                continue
            name = p.GetName()
            if p:
                settings[name] = p.GetValue()
                if isinstance(p, PropCheckBox):
                    settings[name] = bool(settings[name])

        self.SetConfig(settings)
        return settings


class SignalSelSettingDlg(SettingDlgBase):
    def __init__(self, parent, data=None, items=None, values=None, args=None,
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
        for item in items:
            g.Insert(PropAutoCompleteEditBox(self.completer).Label(f'Input ({item})')
                     .Name(item).Value(cfg.get(item, '')))
        if args is not None:
            for name, signal, default in args:
                g.Insert(PropText().Label(f'{name.capitalize()}({signal})')
                     .Name(signal).Value(default))

        for p in self.additional:
            value = cfg.get(p.GetName(), None)
            if value is not None:
                p.Value(value)
            g.Insert(p)

        # not close the dialog with escape key, so escape will only dismiss
        # the popup from PropAutoCompleteEditBox
        self.SetEscapeId(wx.ID_NONE)

    def completer(self, query):
        path = get_tree_item_path(query)
        d = self.data
        for p in path[:-1]:
            if p in d:
                d = d[p]
        objs = [k for k in d if k.startswith(path[-1])]
        return objs, objs, len(path[-1])

    def CreateButtons(self):
        btn = super().CreateButtons()
        # manually close the dialog when click Cancel button
        self.Bind(wx.EVT_BUTTON, self.OnCancel, id=wx.ID_CANCEL)
        return btn

    def OnCancel(self, event):
        self.EndModal(wx.ID_CANCEL)

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

class ConvertManagingDlg(SettingDlgBase):
    ID_DELETE = wx.NewIdRef()
    ID_ADD_ARGUMENT = wx.NewIdRef()

    def __init__(self, parent, converts, labels=None, title='Settings ...',
                 size=wx.DefaultSize, pos=wx.DefaultPosition,
                 style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        SettingDlgBase.__init__(self, parent, None, title, size, pos, style)

        self.labels = labels or {}
        g = self.propgrid
        g.Draggable(True)
        for c in converts:
            self.add_convert(c)

        # expand the 1st convert
        if g.GetCount() > 0:
            g.Get(0).Expand(True)

        self.Bind(propgrid.EVT_PROP_DROP, self.OnDrop)
        self.Bind(propgrid.EVT_PROP_BEGIN_DRAG, self.OnDrag)
        self.Bind(wx.EVT_BUTTON, self.OnAddArgument, id=self.ID_ADD_ARGUMENT)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateCmdUI)

    def OnUpdateCmdUI(self, event):
        eid = event.GetId()
        if eid == self.ID_ADD_ARGUMENT:
            event.Enable(self.propgrid.GetSelected() is not None)

    def _T(self, name):
        label = self.labels.get(name, name)
        label = label.replace('_', ' ').capitalize()
        return label

    def add_argument(self, arg, index=-1, indent=1):

        p = self.propgrid.Insert(PropText().Label(self._T('name'))
                                           .Value(arg[0]).Indent(indent),
                                           index=index)
        if index != -1:
            index += 1
        self.propgrid.Insert(PropText().Label(self._T('argument'))
                                       .Value(arg[1]).Indent(indent+1),
                                        index=index)

        if index != -1:
            index += 1
        if isinstance(arg[2], bool):
            self.propgrid.Insert(PropCheckBox().Label(self._T('default'))
                                               .Value(arg[2]).Indent(indent+1),
                                               index=index)
        else:
            self.propgrid.Insert(PropText().Label(self._T('default'))
                                           .Value(arg[2]).Indent(indent+1),
                                           index=index)

        self.propgrid.SetSelection(p)
        self.propgrid.EnsureVisible(p)

    def add_convert(self, setting):

        label = setting['label']
        inputs = setting['inputs']
        args = setting.get('args', None) or []
        equation = setting.get('equation', '#1')
        outputs = setting.get('outputs', '~#1')
        g = self.propgrid

        p = g.Insert(PropText().Name('label').Label(self._T('label'))
                               .Value(label).Indent(0).Expand(False))
        if inputs is None:
            inputs = ["#1"]
        g.Insert(PropText().Name('inputs').Label(self._T('inputs'))
                           .Value(','.join(inputs)).Indent(1))

        g.Insert(PropSeparator().Name('args').Label(self._T('args'))
                                .Indent(1).Expand(False).Visible(len(args) > 0))
        for arg in args:
            self.add_argument(arg, indent=2)

        g.Insert(PropText().Name('equation').Label(self._T('equation'))
                           .Value(equation).Indent(1))
        g.Insert(PropText().Name('outputs').Label(self._T('outputs'))
                           .Value(outputs).Indent(1))
        # other settings
        for k, v in setting.items():
            if k in ['label', 'inputs', 'args', 'equation', 'outputs']:
                continue
            label = self._T(k)
            if isinstance(v, bool):
                g.Insert(PropCheckBox().Label(label).Name(k).Value(v).Indent(1)
                         .Draggable(False))
            else:
                g.Insert(PropText().Label(label).Name(k).Value(v).Indent(1)
                         .Draggable(False))
        return p


    def get_next_index(self, prop):
        idx = self.propgrid.Index(prop)
        indent = self.propgrid.Get(idx).GetIndent()
        idx += 1
        while idx < self.propgrid.GetCount():
            p = self.propgrid.Get(idx)
            if p.GetIndent() == indent:
                break
            idx += 1
        return idx

    def GetCurrentConvert(self):
        prop = self.propgrid.GetSelected()
        # find the current convert
        while prop and prop.GetIndent() != 0:
            prop = prop.GetParent()

        return prop

    def GetCurrentArgs(self):
        prop = self.GetCurrentConvert()
        if prop is None:
            return None
        idx = self.propgrid.Index(prop)
        # find the args in current convert
        while prop:
            prop = self.propgrid.Get(idx)
            if prop.GetName() == 'args':
                return prop
            idx += 1
        return None

    def OnAddArgument(self, event):
        # find the args in current convert
        prop = self.GetCurrentArgs()
        if prop is None:
            return

        # show the arguments section
        prop.Visible(True).Expand(True).Show()
        idx = self.get_next_index(prop)
        self.add_argument(["", "", "0"], index=idx, indent=prop.GetIndent()+1)

    def CreateButtons(self):
        btns = [wx.Button(self, self.ID_ADD_ARGUMENT, label="Add argument")]
        return btns + super().CreateButtons()

    def OnDrag(self, event):
        prop = event.GetProp()
        if prop.IsExpanded():
            # not allow to move if in expanded mode
            event.Veto()

    def OnDrop(self, event):
        prop = event.GetProp()
        if (prop is not None) and prop.GetIndent() != 0:
            event.Veto()

    def OnRightClick(self, event):
        prop = event.GetProp()
        if prop.GetIndent() in [0, 2]:
            menu = wx.Menu()
            menu.Append(self.ID_DELETE, 'Delete')
            cmd = self.GetPopupMenuSelectionFromUser(menu)
            if cmd == wx.ID_NONE:
                return
            if cmd == self.ID_DELETE:
                idx = self.propgrid.Index(prop)
                # delete the group
                self.propgrid.Delete(idx)
                while idx < self.propgrid.GetCount():
                    p = self.propgrid.Get(idx)
                    if p.GetIndent() <= prop.GetIndent():
                        break
                    self.propgrid.Delete(idx)
            if prop.GetIndent() == 2:
                p = self.GetCurrentArgs()
                if p and not p.HasChildren():
                    p.Visible(False)
            self.propgrid.UpdateGrid()

    def GetConvert(self, index = 0):
        p = self.propgrid.Get(index)
        if p.GetIndent() != 0:
            return None
        convert = {}
        convert[p.GetName()] = p.GetValue()
        index += 1
        while index < self.propgrid.GetCount():
            p = self.propgrid.Get(index)
            if p.GetIndent() == 0:
                break
            if p.GetName() == 'args':
                index += 1
                args = []
                while index < self.propgrid.GetCount():
                    p = self.propgrid.Get(index)
                    if p is None or p.GetIndent() <= 1:
                        break
                    name = p.GetValue()
                    p = self.propgrid.Get(index+1)
                    signal = p.GetValue()
                    p = self.propgrid.Get(index+2)
                    default = p.GetValue()
                    args.append([name, signal, default])
                    index += 3
                convert['args'] = args
                continue
            name = p.GetName()
            value = p.GetValue()
            if isinstance(p, PropCheckBox):
                value = bool(value)
            if name == 'inputs':
                value = [v.strip() for v in value.split(',')]
            convert[name] = value
            index += 1
        return convert, index

    def GetSettings(self):
        for i in range(self.propgrid.GetCount()):
            p = self.propgrid.Get(i)
            # apply the change from editing
            p.Activated(False)

        settings = []
        index = 0
        while index < self.propgrid.GetCount():
            convert, index = self.GetConvert(index)
            if convert:
                settings.append(convert)
        return settings
