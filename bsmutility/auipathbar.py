import os
from pathlib import Path
import wx
import aui2 as aui

from .bsmxpm import chevron_right_svg, chevron_right_grey_svg, double_right_svg, \
                    double_right_grey_svg, down_svg
from .utility import svg_to_bitmap, get_path_list
from .autocomplete import AutocompleteComboBox

wxEVT_COMMAND_AUIPATHBAR_CLICK = wx.NewEventType()
EVT_AUIPATHBAR_CLICK = wx.PyEventBinder(wxEVT_COMMAND_AUIPATHBAR_CLICK, 1)

class AuiPathBarEvent(wx.PyCommandEvent):
    def __init__(self, commandType, win_id=0):
        wx.PyCommandEvent.__init__(self, commandType, win_id)
        self.path = ""
        self.veto = False

    def GetPath(self):
        """return the attached Property"""
        return self.path

    def SetPath(self, path):
        """attach the Property instance"""
        self.path = path

    def Veto(self, veto=True):
        """refuse the event"""
        self.veto = veto

    def GetVeto(self):
        """return whether the event is refused"""
        return self.veto

class AuiPathBar(wx.Control):
    ID_PATH_EDIT = wx.NewIdRef()

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=0, agwStyle=aui.AUI_TB_DEFAULT_STYLE):

        wx.Control.__init__(self, parent, id, pos, size, style|wx.BORDER_NONE)

        self.ids_path = []
        self.ids_subfolder = []

        self._path = ""
        self._show_path_edit = True

        self.tb = aui.AuiToolBar(self, agwStyle=agwStyle | aui.AUI_TB_HORZ_TEXT)
        art = self.tb.GetArtProvider()
        art.SetDropDownBitmap(svg_to_bitmap(chevron_right_svg, win=self),
                              svg_to_bitmap(chevron_right_grey_svg, win=self))

        art.SetOverflowBitmap(svg_to_bitmap(double_right_svg, win=self),
                              svg_to_bitmap(double_right_grey_svg, win=self))
        self.tb.Realize()

        self.address = AutocompleteComboBox(self, completer=self.completer)
        self.address.Hide()
        self.box = wx.BoxSizer(wx.HORIZONTAL)
        self.box.Add(self.tb, 1, wx.EXPAND, 0)
        self.box.Add(self.address, 1, wx.EXPAND | wx.ALL, 2)
        self.box.Fit(self)
        self.SetSizer(self.box)

        self.Bind(wx.EVT_TOOL, self.OnPathEdit, id=self.ID_PATH_EDIT)
        self.address.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(wx.EVT_TEXT_ENTER, self.OnGoToNewAddress, self.address)
        self.Bind(wx.EVT_COMBOBOX, self.OnGoToAddress, self.address)

    def completer(self, query):

        path, prefix = os.path.split(query)
        k = get_path_list(path=path, prefix=prefix, files=False, folder_suffix=None)
        return k, k, len(prefix)

    def SetPathEdit(self, enable):
        self._show_path_edit = enable

    def GetPath(self):
        return self._path

    def SetPath(self, path):
        if not os.path.isdir(path):
            print(f"Invalid folder: {path}")
            return
        # step 1: set path
        self._path = path

        # step 2: update toolbar
        self.tb.Clear()

        abspath = os.path.abspath(path)
        abspath = Path(abspath).parts
        if len(abspath) > len(self.ids_path):
            new_ids = wx.NewIdRef(len(abspath) - len(self.ids_path))
            if len(abspath) - len(self.ids_path) == 1:
                new_ids = [new_ids]
            self.ids_path += new_ids
            self.Bind(wx.EVT_TOOL, self.OnGoToFolder, id=new_ids[0], id2=new_ids[-1])
            self.Bind(aui.EVT_AUITOOLBAR_TOOL_DROPDOWN, self.OnDropDownToolbarItem, id=new_ids[0], id2=new_ids[-1])


        for idx, p in enumerate(abspath):
            self.tb.AddSimpleTool(self.ids_path[idx], p,
                          wx.NullBitmap, p)
            if self.GetSubfolders(self.ids_path[idx]):
                # only show dropdown button if it contains subfolders
                self.tb.SetToolDropDown(self.ids_path[idx], True)
        self.tb.AddStretchSpacer(1)
        if self._show_path_edit:
            self.tb.AddSimpleTool(self.ID_PATH_EDIT, "",
                              svg_to_bitmap(down_svg, win=self), "")

        self.tb.Realize()
        self.Layout()

        # step3: update combobox
        wx.CallAfter(self.address.ChangeValue, os.path.abspath(self._path))
        wx.CallAfter(self.address.SetInsertionPointEnd)

    def ShowPathEdit(self, show):
        if show:
            self.address.Show()
            self.tb.Hide()
            self.address.SetFocus()
        else:
            self.address.Dismiss()
            self.address.Hide()
            self.tb.Show()
            # move the focus, otherwise in windows, if self.address has the
            # focus, it may not lose focus and the whole app can't use keyboard
            # any more
            self.SetFocus()
        self.Layout()

    def GetMinSize(self):
        return self.tb.GetMinSize()

    def DoGetBestSize(self):
        return self.tb.DoGetBestSize()

    def checkFocus(self):
        if not self.HasFocus() and not self.address.HasFocus():
            self.address.hide_popup()
            self.ShowPathEdit(False)

    def OnKillFocus(self, event):
        wx.CallAfter(self.checkFocus)
        event.Skip()

    def OnPathEdit(self, event):
        self.ShowPathEdit(True)

    def OnGoToFolder(self, event):
        # click on toolbar item
        eid = event.GetId()
        path = self.GetFolder(eid)
        if path is not None:
            e = AuiPathBarEvent(wxEVT_COMMAND_AUIPATHBAR_CLICK, self.GetId())
            e.SetPath(path)
            self.SendEvent(e)

    def GetFolder(self, eid):
        if isinstance(eid, wx.WindowIDRef):
            eid = eid.Id

        ids = [eid.Id for eid in self.ids_path]
        if isinstance(eid, int) and eid in ids:
            idx = ids.index(eid)
            path = self.GetPath()
            if path is None:
                return None
            path = os.path.abspath(path)
            subfolder = Path(path).parts
            subfolder = os.path.join(*subfolder[:idx+1])
            path = path[:path.index(subfolder)+len(subfolder)]
            return path
        return None

    def GetSubfolders(self, path):
        if not isinstance(path, str):
            path = self.GetFolder(path)
        if isinstance(path, str) and os.path.isdir(path):
            return get_path_list(path=path, files=False, folder_suffix=None)
        return []

    def OnDropDownToolbarItem(self, event):
        # toolbar dropdown
        if event.IsDropDownClicked():
            eid = event.GetId()
            path = self.GetFolder(eid)
            folders = self.GetSubfolders(path)
            if len(folders) > len(self.ids_subfolder):
                new_ids = wx.NewIdRef(len(folders) - len(self.ids_subfolder))
                if len(folders) - len(self.ids_subfolder) == 1:
                    new_ids = [new_ids]
                self.ids_subfolder += new_ids
            menu = wx.Menu()
            for i, f in enumerate(folders):
                menu.Append(self.ids_subfolder[i], f)
            id_menu = self.GetPopupMenuSelectionFromUser(menu)
            if id_menu != wx.ID_NONE and id_menu in self.ids_subfolder:
                idx = self.ids_subfolder.index(id_menu)
                self.SendPathevent(os.path.join(path, folders[idx]))

    def SendEvent(self, event):
        """send the event to the parent"""

        eventObject = self.GetParent()
        event.SetEventObject(eventObject)
        evtHandler = eventObject.GetEventHandler()

        evtHandler.ProcessEvent(event)
        return not event.GetVeto()

    def SendPathevent(self, path):
        e = AuiPathBarEvent(wxEVT_COMMAND_AUIPATHBAR_CLICK, self.GetId())
        e.SetPath(path)
        return  self.SendEvent(e)

    def OnGoToNewAddress(self, event):
        self.ShowPathEdit(False)

        path = self.address.GetValue()
        self.SendPathevent(path)
        # add the address to the combo
        while True:
            # delete the path if it is in the list
            item = self.address.FindString(path)
            if item == wx.NOT_FOUND:
                break
            self.address.Delete(item)
        # add the path to the beginning
        self.address.Insert(path, 0)

        while self.address.GetCount() > 30:
            # only remember the last 30 path
            self.address.Delete(30)


    def OnGoToAddress(self, event):
        path = self.address.GetValue()
        self.ShowPathEdit(False)
        self.SendPathevent(path)
