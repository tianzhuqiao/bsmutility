import pydoc
import os
import time
import traceback
import sys
import re
import six
import wx
import wx.py.dispatcher as dp
import wx.svg
import aui2 as aui
from .dirtreectrl import DirListCtrl, EVT_DIR_OPEN, DirTreeCtrl, DirTreeList
from .bsmxpm import backward_svg2, backward_gray_svg2, forward_svg2, \
                    forward_gray_svg2, up_svg, home_svg2, more_svg, refresh_svg, \
                    files_svg, history_svg, help_svg
from .autocomplete import AutocompleteTextCtrl
from .utility import FastLoadTreeCtrl, svg_to_bitmap, get_path_list, \
                     unescape_path
from .editor_base import EditorBase
from .bsminterface import InterfaceRename
from .auipathbar import AuiPathBar, EVT_AUIPATHBAR_CLICK
from .findmixin import FindTreeMixin

class HelpText(EditorBase):

    ID_WRAP_MODE = wx.NewIdRef()

    def __init__(self, parent):
        super().__init__(parent)

        self.SetLexer(wx.stc.STC_LEX_NULL)
        self.SetCaretStyle(wx.stc.STC_CARETSTYLE_INVISIBLE)

        # disable replace
        self.findDialogStyle = 0

        self.Bind(wx.EVT_MENU, self.OnWrapMode, self.ID_WRAP_MODE)

        self.LoadConfig()

    def GetContextMenu(self):
        """
            Create and return a context menu for the shell.
            This is used instead of the scintilla default menu
            in order to correctly respect our immutable buffer.
        """
        menu = super().GetContextMenu()

        menu.AppendSeparator()
        menu.AppendCheckItem(self.ID_WRAP_MODE, 'Word wrap')
        menu.Check(self.ID_WRAP_MODE, self.GetWrapMode() != wx.stc.STC_WRAP_NONE)
        return menu

    def OnWrapMode(self, event):
        if self.GetWrapMode() == wx.stc.STC_WRAP_NONE:
            self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        else:
            self.SetWrapMode(wx.stc.STC_WRAP_NONE)
        self.SetConfig()

    def SetConfig(self):
        dp.send('frame.set_config', group='helppanel', wrap=self.GetWrapMode() != wx.stc.STC_WRAP_NONE)

    def LoadConfig(self):
        resp = dp.send('frame.get_config', group='helppanel', key='wrap')
        if resp and resp[0][1] is not None:
            if resp[0][1]:
                self.SetWrapMode(wx.stc.STC_WRAP_WORD)
            else:
                self.SetWrapMode(wx.stc.STC_WRAP_NONE)

class HelpPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        self.html = HelpText(self)

        agwStyle = aui.AUI_TB_OVERFLOW
        self.tb = aui.AuiToolBar(self, agwStyle=agwStyle)
        self.tb.AddTool(wx.ID_BACKWARD, 'Back',
                        svg_to_bitmap(backward_svg2, win=self),
                        svg_to_bitmap(backward_gray_svg2, win=self),
                        aui.ITEM_NORMAL,
                        'Go the previous page')

        self.tb.AddTool(wx.ID_FORWARD, 'Forward',
                        svg_to_bitmap(forward_svg2, win=self),
                        svg_to_bitmap(forward_gray_svg2, win=self),
                        aui.ITEM_NORMAL,
                        'Go to the next page')
        self.search = AutocompleteTextCtrl(self.tb, completer=self.completer)
        item = self.tb.AddControl(self.search)
        item.SetProportion(1)
        self.tb.Realize()

        # Setup the layout
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tb, 0, wx.ALL | wx.EXPAND, 0)
        sizer.Add(self.html, 1, wx.ALL | wx.EXPAND, 0)
        self.SetSizer(sizer)

        self.history = []
        self.history_index = -1

        self.Bind(wx.EVT_TEXT_ENTER, self.OnDoSearch, self.search)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateUI)
        self.Bind(wx.EVT_TOOL, self.OnBack, id=wx.ID_BACKWARD)
        self.Bind(wx.EVT_TOOL, self.OnForward, id=wx.ID_FORWARD)
        dp.connect(receiver=self.show_help, signal='help.show')

        self.LoadConfig()
        self.html.SetReadOnly(True)
        command = self.search.GetValue()
        if command:
            self.show_help(command)

    def LoadConfig(self):
        resp = dp.send('frame.get_config', group='helppanel', key='search')
        if resp and resp[0][1] is not None:
            # use ChangeValue, instead of SetValue, otherwise a suggestion
            # window may popup
            self.search.ChangeValue(resp[0][1])

    def SaveConfig(self):
        dp.send('frame.set_config', group='helppanel', search=self.search.GetValue())

    def completer(self, query):
        response = dp.send(signal='shell.auto_complete_list', command=query)
        if response:
            root = query[0:query.rfind('.') + 1]
            remain = query[query.rfind('.') + 1:]
            remain = remain.lower()
            objs = [o for o in response[0][1] if o.lower().startswith(remain)]
            return objs, objs, len(query) - len(root)
        return [], [], 0

    def add_history(self, command):
        if not self.history or self.history[-1] != command:
            self.history.append(command)
            self.history_index = -1

    def show_help(self, command, addhistory=True):
        try:
            strhelp = pydoc.plain(pydoc.render_doc(str(command), "Help on %s"))
            self.html.SetReadOnly(False)
            self.html.SetText(strhelp)
            # do not use SetValue since it will trigger the text update event, which
            # will popup the auto complete list window
            self.search.ChangeValue(command)
            if addhistory:
                self.add_history(command)
        except:
            traceback.print_exc(file=sys.stdout)
        self.html.SetReadOnly(True)

        if not self.IsShownOnScreen():
            dp.send('frame.show_panel', panel=self)

    def OnDoSearch(self, evt):
        command = self.search.GetValue()
        self.show_help(command)

    def OnWebViewNavigating(self, evt):
        # this event happens prior to trying to get a resource
        strURL = evt.GetURL()
        if strURL[:8] == 'bsmhelp:':
            # This is how you can cancel loading a page.
            evt.Veto()
            command = strURL[8:]
            self.show_help(command)

    def OnUpdateUI(self, event):
        idx = event.GetId()
        h_idx = -1
        h_len = len(self.history)
        if h_len > 0:
            h_idx = self.history_index % h_len
        if idx == wx.ID_FORWARD:
            event.Enable(0 <= h_idx < h_len - 1)
        elif idx == wx.ID_BACKWARD:
            event.Enable(h_idx > 0)

    def OnBack(self, event):
        # the button is only enabled when history_index>0
        self.history_index -= 1
        command = self.history[self.history_index]
        self.show_help(command, False)

    def OnForward(self, event):
        # the button is only enable when history_index hasn't reached the last
        # one
        self.history_index += 1
        command = self.history[self.history_index]
        self.show_help(command, False)

class HistoryTreeCtrl(FastLoadTreeCtrl, FindTreeMixin):

    def __init__(self, *args, **kwargs):
        FastLoadTreeCtrl.__init__(self, *args, **kwargs)
        FindTreeMixin.__init__(self)

        accel = FindTreeMixin.BuildAccelTable(self)
        self.accel = wx.AcceleratorTable(accel)
        self.SetAcceleratorTable(self.accel)

    def GetNextItem(self, item):
        if self.ItemHasChildren(item):
            self.FillChildren(item)

        return super().GetNextItem(item)

    def GetPrevItem(self, item):
        if self.ItemHasChildren(item):
            self.FillChildren(item)

        return super().GetPrevItem(item)

class HistoryPanel(wx.Panel):
    ID_EXECUTE = wx.NewIdRef()
    TIME_STAMP_HEADER = "#bsm#"

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        style = wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT |wx.TR_MULTIPLE |\
                wx.TR_HAS_VARIABLE_ROW_HEIGHT
        # no need to sort the commands, as they are naturally sorted by
        # execution time
        self.tree = HistoryTreeCtrl(self,
                                     getchildren=self.get_children,
                                     style=style,
                                     sort=False)

        agwStyle = aui.AUI_TB_OVERFLOW
        self.tb = aui.AuiToolBar(self, agwStyle=agwStyle)
        self.search = AutocompleteTextCtrl(self.tb, completer=self.completer)
        self.search.SetHint('command pattern (*)')
        item = self.tb.AddControl(self.search)
        item.SetProportion(1)
        self.tb.SetMargins(right=15)
        self.tb.Realize()

        self.clr_folder = wx.Colour(100, 174, 100)
        self.history = {}
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tree, 1, wx.ALL | wx.EXPAND, 0)
        sizer.Add(self.tb, 0, wx.ALL | wx.EXPAND, 0)
        self.SetSizer(sizer)
        dp.connect(receiver=self.AddHistory, signal='Shell.addHistory')
        self.root = self.tree.AddRoot('The Root Item')
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnActivate, self.tree)
        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnRightClick, self.tree)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_EXECUTE)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_DELETE)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_CLEAR)
        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)

        accel = [
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY),
            (wx.ACCEL_CTRL, ord('X'), wx.ID_CUT),
            (wx.ACCEL_CTRL, ord('E'), self.ID_EXECUTE),
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, wx.ID_DELETE),
        ]
        self.accel = wx.AcceleratorTable(accel)
        self.SetAcceleratorTable(self.accel)
        self.LoadConfig()
        self.LoadHistory()

    def LoadConfig(self):
        resp = dp.send('frame.get_config', group='historypanel', key='file_pattern')
        if resp and resp[0][1] is not None:
            self.search.SetValue(resp[0][1])

    def SaveConfig(self):
        dp.send('frame.set_config', group='historypanel', file_pattern=self.search.GetValue())

    def completer(self, query):
        response = dp.send(signal='shell.auto_complete_list', command=query)
        if response:
            root = query[0:query.rfind('.') + 1]
            remain = query[query.rfind('.') + 1:]
            remain = remain.lower()
            objs = [o for o in response[0][1] if o.lower().startswith(remain)]
            return objs, objs, len(query) - len(root)
        return [], [], 0

    def Destroy(self):
        dp.disconnect(receiver=self.AddHistory, signal='Shell.addHistory')
        super(HistoryPanel, self).Destroy()

    def get_children(self, item):
        """ callback function to return the children of item """
        if item == self.tree.GetRootItem():
            childlist = list(six.iterkeys(self.history))
            childlist = [c for c in childlist if len(self.history[c]) > 0]
            # sort by time-stamp
            childlist.sort()
            is_folder = True
            clr = self.clr_folder
        else:
            stamp = self.tree.GetItemText(item)
            childlist = self.history.get(stamp, [])
            is_folder = False
            clr = None
            # free the list
            #self.history.pop(stamp, None)
        children = []
        for obj in reversed(childlist):
            child = {
                'label': obj,
                'img': -1,
                'imgsel': -1,
                'data': '',
                'color': clr
            }
            child['is_folder'] = is_folder
            children.append(child)
        return children

    def filterHistory(self, history):
        pattern = self.search.GetValue()
        if not pattern:
            return history
        try:
            pattern = re.compile(pattern)
            self.search.SetForegroundColour(wx.NullColour)
        except:
            self.search.SetForegroundColour('red')
            return history

        return [h for h in history if h.startswith(self.TIME_STAMP_HEADER) or pattern.search(h) is not None]

    def LoadHistory(self):
        resp = dp.send('frame.get_config', group='shell', key='history')
        history = []
        if resp and resp[0][1]:
            history = resp[0][1]

        history = self.filterHistory(history)
        self.history = {}
        stamp = time.strftime('%Y/%m/%d')
        for i in six.moves.range(len(history) - 1, -1, -1):
            value = history[i]
            if value.startswith(self.TIME_STAMP_HEADER):
                stamp = value[len(self.TIME_STAMP_HEADER):]
                self.history[stamp] = self.history.get(stamp, [])
            elif self.history.get(stamp, None) is not None:
                self.history[stamp].append(value)
        self.tree.DeleteChildren(self.root)
        self.tree.FillChildren(self.root)
        item, _ = self.tree.GetFirstChild(self.root)
        if item.IsOk():
            self.tree.Expand(item)
            child, _ = self.tree.GetFirstChild(item)
            if child.IsOk():
                self.tree.SelectItem(child)
                self.tree.EnsureVisible(child)

    def SaveHistory(self, config):
        """save the history"""
        config.DeleteGroup('/CommandHistory')
        config.SetPath('/CommandHistory')
        (item, cookie) = self.tree.GetFirstChild(self.root)
        pos = 0
        while item.IsOk():
            stamp = self.tree.GetItemText(item)
            config.Write("item%d" % pos, self.TIME_STAMP_HEADER + stamp)
            pos += 1

            childitem, childcookie = self.tree.GetFirstChild(item)
            if childitem.IsOk() and self.tree.GetItemText(childitem) != "...":
                while childitem.IsOk():
                    config.Write("item%d" % pos,
                                 self.tree.GetItemText(childitem))
                    childitem, childcookie = self.tree.GetNextChild(
                        item, childcookie)
                    pos = pos + 1
            # save the unexpanded folder
            for child in self.history.get(stamp, []):
                config.Write("item%d" % pos, child)
                pos = pos + 1

            (item, cookie) = self.tree.GetNextChild(self.root, cookie)

    def AddHistory(self, command, stamp=""):
        """ add history to treectrl """
        command = command.strip()
        if not command:
            return
        if not stamp:
            stamp = time.strftime('%Y/%m/%d')

        if not self.filterHistory([command]):
            # not match the pattern
            return

        # search the time stamp
        pos = 0
        item, cookie = self.tree.GetFirstChild(self.root)
        while item.IsOk():
            if self.tree.GetItemText(item) == stamp:
                break
            elif self.tree.GetItemText(item) < stamp:
                item = self.tree.InsertItem(self.root, pos, stamp)
                self.tree.SetItemTextColour(item, self.clr_folder)
                break
            pos = pos + 1
            (item, cookie) = self.tree.GetNextChild(self.root, cookie)
        # not find the time stamp, create one
        if not item.IsOk():
            item = self.tree.PrependItem(self.root, stamp)
            self.tree.SetItemTextColour(item, self.clr_folder)
        if stamp not in self.history:
            self.history[stamp] = []
        self.history[stamp].append(command)
        # append the history
        if item.IsOk():
            self.tree.Expand(item)
            child = self.tree.PrependItem(item, command)
            self.tree.EnsureVisible(child)

    def OnActivate(self, event):
        item = event.GetIndex()
        filepath = self.tree.GetItemPath(item)
        if os.path.isfile(filepath):
            command = self.tree.GetItemText(item)
            dp.send(signal='shell.run', command=command)

    def OnRightClick(self, event):
        menu = wx.Menu()
        menu.Append(wx.ID_COPY, "Copy\tCtrl+C")
        menu.Append(wx.ID_CUT, "Cut\tCtrl+X")
        menu.Append(self.ID_EXECUTE, "Evaluate\tCtrl+E")
        menu.AppendSeparator()
        menu.AppendSeparator()
        menu.Append(wx.ID_DELETE, "Delete\tDel")
        menu.Append(wx.ID_CLEAR, "Clear history")
        self.PopupMenu(menu)
        menu.Destroy()

    def GetChildIndex(self, parent, child):
        item, cookie = self.tree.GetFirstChild(parent)
        index = 0
        while item.IsOk():
            index += 1
            if item == child:
                return index
            item, cookie = self.tree.GetNextChild(parent, cookie)
        return -1

    def OnProcessEvent(self, event):
        items = self.tree.GetSelections()
        cmd = []
        for item in items:
            cmd.append(self.tree.GetItemText(item))
        evtId = event.GetId()
        if evtId in (wx.ID_COPY, wx.ID_CUT):
            clipData = wx.TextDataObject()
            clipData.SetText("\n".join(cmd))
            wx.TheClipboard.Open()
            wx.TheClipboard.SetData(clipData)
            wx.TheClipboard.Close()
            if evtId == wx.ID_CUT:
                for item in items:
                    if self.tree.ItemHasChildren(item):
                        self.tree.DeleteChildren(item)
                    self.tree.Delete(item)
        elif evtId == self.ID_EXECUTE:
            for c in cmd:
                dp.send(signal='shell.run', command=c)
        elif evtId == wx.ID_DELETE:
            for item in items:
                cmd = self.tree.GetItemText(item)
                timestamp = ""
                parent = self.tree.GetItemParent(item)
                index = -1
                if parent != self.root:
                    timestamp = self.tree.GetItemText(parent)
                    index = self.GetChildIndex(parent, item)
                    if index > 0:
                        index = len(self.history[timestamp]) - index
                        assert self.history[timestamp][index] == cmd
                        del self.history[timestamp][index]
                    timestamp = f"#bsm#{timestamp}"
                else:
                    self.history.pop(cmd, None)
                    cmd = f"#bsm#{cmd}"
                    timestamp = cmd
                dp.send(signal='shell.delete_history', command=cmd, timestamp=timestamp, \
                        index=index)
                if self.tree.ItemHasChildren(item):
                    self.tree.DeleteChildren(item)
                self.tree.Delete(item)
        elif evtId == wx.ID_CLEAR:
            dp.send(signal='shell.clear_history')
            self.tree.DeleteAllItems()
            self.history = {}

    def OnDoSearch(self, evt):
        self.LoadHistory()

class DirPanel(wx.Panel):

    ID_GOTO_PARENT = wx.NewIdRef()
    ID_GOTO_HOME = wx.NewIdRef()
    ID_MORE = wx.NewIdRef()
    ID_STYLE_LIST = wx.NewIdRef()
    ID_STYLE_TREE = wx.NewIdRef()
    ID_STYLE_TREELIST = wx.NewIdRef()
    ID_SHOW_HIDDEN = wx.NewIdRef()
    ID_SHOW_PATTERN_TOOLBAR = wx.NewIdRef()

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)


        agwStyle = aui.AUI_TB_OVERFLOW
        self.tb = aui.AuiToolBar(self, agwStyle=agwStyle)
        self.tb.AddTool(wx.ID_BACKWARD, 'Back',
                        svg_to_bitmap(backward_svg2, win=self),
                        svg_to_bitmap(backward_gray_svg2, win=self),
                        aui.ITEM_NORMAL,
                        'Back')

        self.tb.AddTool(wx.ID_FORWARD, 'Forward',
                        svg_to_bitmap(forward_svg2, win=self),
                        svg_to_bitmap(forward_gray_svg2, win=self),
                        aui.ITEM_NORMAL,
                        'Forward')
        self.tb.AddSeparator()
        self.tb.AddSimpleTool(self.ID_GOTO_PARENT, 'Parent',
                              svg_to_bitmap(up_svg, win=self), 'Parent folder')
        self.tb.AddSeparator()
        self.tb.AddSimpleTool(self.ID_GOTO_HOME, 'Home',
                              svg_to_bitmap(home_svg2, win=self), 'Current folder')
        self.tb.AddSeparator()
        self.tb.AddSimpleTool(wx.ID_REFRESH, 'Refresh',
                              svg_to_bitmap(refresh_svg, win=self), 'Refresh the current folder')


        self.showHidden = True
        self.tb.AddSimpleTool(self.ID_MORE, 'More ...',
                              svg_to_bitmap(more_svg, win=self), 'More ...')

        self.tb.AddSeparator()
        self.Bind(wx.EVT_TOOL, self.OnMenuDropDown, id=self.ID_MORE)
        self.Bind(wx.EVT_MENU, self.OnProcessMenu, id=self.ID_STYLE_LIST)
        self.Bind(wx.EVT_MENU, self.OnProcessMenu, id=self.ID_STYLE_TREE)
        self.Bind(wx.EVT_MENU, self.OnProcessMenu, id=self.ID_STYLE_TREELIST)
        self.Bind(wx.EVT_MENU, self.OnProcessMenu, id=self.ID_SHOW_HIDDEN)
        self.Bind(wx.EVT_MENU, self.OnProcessMenu, id=self.ID_SHOW_PATTERN_TOOLBAR)

        self.tb.Realize()

        self.addressbar = AuiPathBar(self, agwStyle=agwStyle | aui.AUI_TB_HORZ_TEXT)


        ctrl_style = 'list'
        resp = dp.send('frame.get_config', group='dirpanel', key='ctrl_style')
        if resp and resp[0][1] is not None:
            ctrl_style = resp[0][1]
        if ctrl_style == 'treelist':
            self.dirwin = DirTreeList(self)
        elif ctrl_style == 'tree':
            self.dirwin = DirTreeCtrl(self)
        else:
            self.dirwin = DirListCtrl(self, style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_EDIT_LABELS)

        agwStyle = aui.AUI_TB_OVERFLOW | aui.AUI_TB_PLAIN_BACKGROUND
        self.tb2 = aui.AuiToolBar(self, agwStyle=agwStyle)
        self.search = AutocompleteTextCtrl(self.tb2)
        self.search.SetHint('file pattern (*.*)')
        item = self.tb2.AddControl(self.search)
        item.SetProportion(1)
        self.tb2.SetMargins(right=15)
        self.tb2.Realize()

        self.box = wx.BoxSizer(wx.VERTICAL)
        boxtb = wx.BoxSizer(wx.HORIZONTAL)
        boxtb.Add(self.tb, 0, wx.EXPAND, 0)
        boxtb.Add(self.addressbar, 1, wx.EXPAND, 0)
        self.box.Add(boxtb, 0, wx.EXPAND, 0)
        #self.box.Add(wx.StaticLine(self), 0, wx.EXPAND)
        self.box.Add(self.dirwin, 1, wx.EXPAND)
        self.box.Add(self.tb2, 0, wx.EXPAND)

        self.box.Fit(self)
        self.SetSizer(self.box)

        self.history = []
        self.history_index = 0
        self.LoadConfig()

        self.Bind(wx.EVT_TOOL, self.OnGotoHome, id=self.ID_GOTO_HOME)
        self.Bind(wx.EVT_TOOL, self.OnGotoParent, id=self.ID_GOTO_PARENT)
        self.Bind(wx.EVT_TOOL, self.OnForward, id=wx.ID_FORWARD)
        self.Bind(wx.EVT_TOOL, self.OnBack, id=wx.ID_BACKWARD)
        self.Bind(wx.EVT_TOOL, self.OnRefresh, id=wx.ID_REFRESH)

        self.Bind(EVT_DIR_OPEN, self.OnOpenPath, self.dirwin)
        self.Bind(EVT_AUIPATHBAR_CLICK, self.OnPathBarClick, self.addressbar)

        self.Bind(wx.EVT_TEXT, self.OnDoSearch, self.search)

        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateUI)

        dp.connect(receiver=self.GoTo, signal='dirpanel.goto')


    def completer(self, query):

        path, prefix = os.path.split(query)
        k = get_path_list(path=path, prefix=prefix, files=False)
        return k, k, len(prefix)

    def OnOpenPath(self, event):
        self.doGoToAddress(event.GetPath())

    def LoadConfig(self):
        resp = dp.send('frame.get_config', group='dirpanel', key='show_hidden')
        if resp and resp[0][1] is not None:
            self.showHidden = resp[0][1]
        resp = dp.send('frame.get_config', group='dirpanel', key='file_pattern')
        if resp and resp[0][1] is not None:
            self.search.SetValue(resp[0][1])

        resp = dp.send('frame.get_config', group='dirpanel', key='show_pattern_toolbar')
        if resp and resp[0][1] is not None:
            self.tb2.Show(resp[0][1])
            self.Layout()
            self.Update()

        resp = dp.send('frame.get_config', group='dirpanel', key='path_list')
        if resp and resp[0][1] is not None:
            items = resp[0][1]
            self.addressbar.address.SetItems(items)

        resp = dp.send('frame.get_config', group='dirpanel', key='path_active')
        path = os.getcwd()
        if resp and resp[0][1] is not None:
            if os.path.isdir(resp[0][1]):
                path = resp[0][1]

        self.dirwin.LoadConfig()
        self.doGoToAddress(path)

    def SaveConfig(self):
        dp.send('frame.set_config', group='dirpanel', show_hidden=self.showHidden)
        dp.send('frame.set_config', group='dirpanel', file_pattern=self.search.GetValue())
        dp.send('frame.set_config', group='dirpanel', show_pattern_toolbar=self.tb2.IsShown())

        dp.send('frame.set_config', group='dirpanel', path_active=self.addressbar.GetPath())
        dp.send('frame.set_config', group='dirpanel', path_list=self.addressbar.address.GetItems())

        self.dirwin.SaveConfig()

    def OnMenuDropDown(self, event):
        menu = wx.Menu()
        menu.AppendSeparator()
        item = menu.AppendCheckItem(self.ID_STYLE_LIST, "Show path as list")
        item.Check(isinstance(self.dirwin, DirListCtrl))
        item = menu.AppendCheckItem(self.ID_STYLE_TREE, "Show path as tree")
        item.Check(isinstance(self.dirwin, DirTreeCtrl))
        item = menu.AppendCheckItem(self.ID_STYLE_TREELIST, "Show path as treelist")
        item.Check(isinstance(self.dirwin, DirTreeList))
        menu.AppendSeparator()
        item = menu.AppendCheckItem(self.ID_SHOW_HIDDEN, "Show hidden file/folder")
        item.Check(self.showHidden)
        menu.AppendSeparator()
        item = menu.AppendCheckItem(self.ID_SHOW_PATTERN_TOOLBAR, "Pattern toolbar")
        item.Check(self.tb2.IsShown())

        # line up our menu with the button
        tb = event.GetEventObject()
        tb.SetToolSticky(event.GetId(), True)
        rect = tb.GetToolRect(event.GetId())
        pt = tb.ClientToScreen(rect.GetBottomLeft())
        pt = self.ScreenToClient(pt)

        self.PopupMenu(menu)

        # make sure the button is "un-stuck"
        tb.SetToolSticky(event.GetId(), False)

    def OnProcessMenu(self, event):
        eid = event.GetId()
        if eid == self.ID_SHOW_HIDDEN:
            self.showHidden = not self.showHidden
            self.SetRootDir()
        elif eid == self.ID_SHOW_PATTERN_TOOLBAR:
            self.tb2.Show(not self.tb2.IsShown())
            self.Layout()
            self.Update()
        elif eid in [self.ID_STYLE_LIST, self.ID_STYLE_TREE, self.ID_STYLE_TREELIST]:
            ctrl_style = 'list'
            if eid == self.ID_STYLE_TREE:
                ctrl_style = 'tree'
            elif eid == self.ID_STYLE_TREELIST:
                ctrl_style = 'treelist'
            dp.send('frame.set_config', group='dirpanel', ctrl_style=ctrl_style)
            msg = 'Restart is require for changes to take effect!'
            parent = self.GetTopLevelParent()
            dlg = wx.MessageDialog(self, msg, parent.GetLabel(), wx.OK)
            dlg.ShowModal()

    def GoTo(self, filepath, show=None):
        folder = filepath
        if os.path.isfile(filepath):
            folder = os.path.dirname(filepath)
        if not os.path.isdir(folder):
            return

        self.doGoToAddress(folder)
        if os.path.isfile(filepath):
            filename = os.path.basename(filepath)
            for item in range(self.dirwin.GetItemCount()):
                text = self.dirwin.GetItemText(item)
                if os.path.normpath(text) == os.path.normpath(filename):
                    self.dirwin.Select(item)
                    self.dirwin.EnsureVisible(item)
                    break

        if show:
            dp.send(signal='frame.show_panel', panel=self, focus=True)

    def OnPathBarClick(self, event):
        path = event.GetPath()
        self.doGoToAddress(path)

    def doGoToAddress(self, path):
        path = unescape_path(path)
        if os.path.isdir(path):
            self.SetRootDir(path)
            self.addressbar.SetPath(path)
            self.Layout()
        else:
            print(f"Invalid folder: {path}")

    def OnRefresh(self, event):
        d = self.dirwin.GetRootDir()
        self.doGoToAddress(d)

    def OnGotoHome(self, event):
        root = self.dirwin.GetRootDir()
        if os.path.normpath(root) == os.path.normpath(os.getcwd()):
            return
        self.doGoToAddress(os.getcwd())

    def OnGotoParent(self, event):
        root = self.dirwin.GetRootDir()
        path = os.path.abspath(os.path.join(root, os.path.pardir))
        if path == os.path.abspath(root):
            return
        self.doGoToAddress(path)

    def OnBack(self, event):
        # the button is only enabled when history_index>0
        root = self.history[self.history_index-1]
        self.doGoToAddress(root)

    def OnForward(self, event):
        # the button is only enable when history_index hasn't reached the last
        # one
        root = self.history[self.history_index+1]
        self.doGoToAddress(root)

    def OnDoSearch(self, evt):
        self.SetRootDir()

    def SetRootDir(self, root_dir=None):
        if not root_dir:
            root_dir = self.dirwin.GetItemPath(self.dirwin.GetRootItem())
        pattern = self.search.GetValue()
        self.dirwin.SetRootDir(root_dir, pattern=pattern, show_hidden=self.showHidden)
        if self.history_index + 1 < len(self.history) and root_dir == self.history[self.history_index+1]:
            self.history_index += 1
        elif self.history_index - 1 >= 0 and root_dir == self.history[self.history_index-1]:
            self.history_index -= 1
        else:
            if 0 <= self.history_index < len(self.history):
                # remove the history after current point
                self.history = self.history[:self.history_index+1]
            if not (len(self.history) > 0 and self.history[-1] == root_dir):
                self.history.append(root_dir)
            self.history_index = len(self.history)-1

    def OnShowHidden(self, event):
        self.SetRootDir()

    def OnUpdateUI(self, event):
        idx = event.GetId()
        h_idx = -1
        h_len = len(self.history)
        if h_len > 0:
            h_idx = self.history_index % h_len
        if idx == wx.ID_FORWARD:
            event.Enable(0 <= h_idx < h_len - 1)
        elif idx == wx.ID_BACKWARD:
            event.Enable(h_idx > 0)

class MiscTools(InterfaceRename):

    panelHistory = None
    panelHelp = None
    panelDir = None

    @classmethod
    def initialize(cls, frame, history_panel=True, help_panel=True, dir_panel=True,
                   **kwargs):
        super().initialize(frame, **kwargs)

        active = kwargs.get('active', True)
        direction = kwargs.get('direction', 'top')
        # history panel
        if history_panel:
            cls.panelHistory = HistoryPanel(frame)
            bmp = svg_to_bitmap(history_svg, win=cls.panelHistory)
            dp.send(signal='frame.add_panel',
                    panel=cls.panelHistory,
                    title="History",
                    showhidemenu='View:Panels:Command History',
                    active=active,
                    direction=direction,
                    name="history",
                    icon=bmp,
                    pane_menu={'rxsignal': 'misctool.pane_menu',
                               'menu': [{'id':cls.ID_PANE_RENAME, 'label':'Rename'}]
                               }
                    )
        # help panel
        if help_panel:
            cls.panelHelp = HelpPanel(frame)
            bmp = svg_to_bitmap(help_svg, win=cls.panelHelp)
            dp.send(signal='frame.add_panel',
                    panel=cls.panelHelp,
                    title="Help",
                    target='History',
                    showhidemenu='View:Panels:Command Help',
                    active=active,
                    direction=direction,
                    name='help',
                    icon=bmp,
                    pane_menu={'rxsignal': 'misctool.pane_menu',
                               'menu': [{'id':cls.ID_PANE_RENAME, 'label':'Rename'}]
                               }
                    )
        # directory panel
        if dir_panel:
            cls.panelDir = DirPanel(frame)
            bmp = svg_to_bitmap(files_svg, win=cls.panelDir)
            dp.send(signal='frame.add_panel',
                    panel=cls.panelDir,
                    title="Browsing",
                    target="History",
                    showhidemenu='View:Panels:Browsing',
                    active=active,
                    direction=direction,
                    name='browsing',
                    icon=bmp,
                    pane_menu={'rxsignal': 'misctool.pane_menu',
                               'menu': [{'id':cls.ID_PANE_RENAME, 'label':'Rename'}]
                               }
                    )

        dp.connect(cls.PaneMenu, 'misctool.pane_menu')

    @classmethod
    def PaneMenu(cls, pane, command):
        if not pane or pane.window not in [cls.panelHistory, cls.panelHelp, cls.panelDir]:
            return

        if command == cls.ID_PANE_RENAME:
            cls.RenamePane(pane)

    @classmethod
    def uninitializing(cls):
        if cls.panelHistory is not None:
            cls.panelHistory.SaveConfig()
        if cls.panelHelp is not None:
            cls.panelHelp.SaveConfig()
        if cls.panelDir is not None:
            cls.panelDir.SaveConfig()
