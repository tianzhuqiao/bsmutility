import sys
import traceback
import importlib
import json
import pkgutil
import six
import wx
import wx.py.dispatcher as dp
import aui2 as aui
from .utility import build_menu_from_list, svg_to_bitmap
from .bsmxpm import restore_svg

class FileDropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        super().__init__()
        self.frame = frame

    def OnDropFiles(self, x, y, filenames):
        for fname in filenames:
            wx.CallAfter(self.frame.doOpenFile, filename=fname)
        return True

class AuiManagerPlus(aui.AuiManager):
    def __init__(self, managed_window=None, agwFlags=None):
        aui.AuiManager.__init__(self,
                                managed_window=managed_window,
                                agwFlags=agwFlags)

    def CreateNotebook(self):
        """
        Creates an automatic :class:`~wx.lib.agw.aui.auibook.AuiNotebook` when a pane is docked on
        top of another pane.
        """
        nb = super(AuiManagerPlus, self).CreateNotebook()
        # the default size is (0, 0) from previous step, set it to (100, 100) so it will not assert
        # wxpython/ext/wxWidgets/src/gtk/bitmap.cpp(539): assert ""width > 0 &&
        # height > 0"" failed in Create(): invalid bitmap size
        nb.SetSize(100, 100)
        return nb

    def UpdateNotebook(self):
        """ Updates the automatic :class:`~lib.agw.aui.auibook.AuiNotebook` in
        the layout (if any exists). """

        super(AuiManagerPlus, self).UpdateNotebook()

        # set the notebook minsize to be the largest one of its children page.
        # otherwise, when you drag the notebook, its children page's size may
        # be zero in one dimension, which may cause some assert (e.g., invalid
        # bitmap size as show above)

        for _, nb in self._notebooks.items():
            pages = nb.GetPageCount()
            nb_pane = self.GetPane(nb)
            min_x, min_y = nb_pane.min_size
            # Check each tab ...
            for page in range(pages):
                window = nb.GetPage(page)
                page_pane = self.GetPane(window)
                min_x = max(page_pane.min_size.x, min_x)
                min_y = max(page_pane.min_size.y, min_y)
            nb_pane.MinSize(min_x, min_y)

    def OnClose(self, event):
        # AuiManager will call UnInit(), skip it and will be called by the
        # main frame
        event.Skip()

class MultiDimensionalArrayEncoder(json.JSONEncoder):
    def encode(self, o):
        def hint_tuples(item):
            if isinstance(item, tuple):
                return {'__tuple__': True, 'items': item}
            if isinstance(item, list):
                return [hint_tuples(e) for e in item]
            if isinstance(item, dict):
                return {key: hint_tuples(value) for key, value in item.items()}
            else:
                return item

        return super().encode(hint_tuples(o))

def hinted_tuple_hook(obj):
    if '__tuple__' in obj:
        return tuple(obj['items'])
    else:
        return obj


class TaskBarIcon(wx.adv.TaskBarIcon):
    TBMENU_RESTORE = wx.NewIdRef()
    TBMENU_CLOSE = wx.NewIdRef()

    def __init__(self, frame, icon, project_name):
        super().__init__(iconType=wx.adv.TBI_DOCK)
        self.frame = frame
        self.project_name = project_name

        # Set the image
        self.SetIcon(icon, project_name)
        self.imgidx = 1

        # bind some events
        #self.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.OnTaskBarActivate)
        self.Bind(wx.EVT_MENU, self.OnTaskBarActivate, id=self.TBMENU_RESTORE)
        self.Bind(wx.EVT_MENU, self.OnTaskBarClose, id=self.TBMENU_CLOSE)


    def CreatePopupMenu(self):
        """
        This method is called by the base class when it needs to popup
        the menu for the default EVT_RIGHT_DOWN event.  Just create
        the menu how you want it and return it from this function,
        the base class takes care of the rest.
        """
        menu = wx.Menu()
        menu.Append(self.TBMENU_RESTORE, f"Restore {self.project_name}")
        menu.Append(self.TBMENU_CLOSE, f"Close {self.project_name}")
        return menu


    def MakeIcon(self, img):
        """
        The various platforms have different requirements for the
        icon size...
        """
        if "wxMSW" in wx.PlatformInfo:
            img = img.Scale(16, 16)
        elif "wxGTK" in wx.PlatformInfo:
            img = img.Scale(22, 22)
        # wxMac can be any size upto 128x128, so leave the source img alone....
        icon = wx.Icon(img.ConvertToBitmap())
        return icon


    def OnTaskBarActivate(self, evt):
        if self.frame.IsIconized():
            self.frame.Iconize(False)
        if not self.frame.IsShown():
            self.frame.Show(True)
        self.frame.Raise()


    def OnTaskBarClose(self, evt):
        wx.CallAfter(self.frame.Close)


class FramePlus(wx.Frame):
    CONFIG_NAME='bsm'
    ID_SHOW_TAB_BOTTOM = wx.NewIdRef()
    ID_SHOW_WINDOWLIST = wx.NewIdRef()

    def __init__(self,
                 parent,
                 title="",
                 pos=wx.DefaultPosition,
                 size=wx.DefaultSize,
                 style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL, **kwargs):
        wx.Frame.__init__(self,
                          parent,
                          title=title,
                          pos=pos,
                          size=size,
                          style=style)
        self._mgr = AuiManagerPlus()
        self._mgr.SetManagedWindow(self)
        self._mgr.GetArtProvider().SetMetric(aui.AUI_DOCKART_PANE_BUTTON_SIZE, 25)
        self._mgr.SetRestoreButtonBitmap(svg_to_bitmap(restore_svg, win=self))
        self.menuAddon = {}
        self.paneAddon = {}
        self.paneMenu = {}
        self._pane_num = 0

        # persistent configuration
        conf = kwargs.get('config', self.CONFIG_NAME)
        self.config = wx.FileConfig(conf, style=wx.CONFIG_USE_LOCAL_FILE)

        self.closing = False
        self.InitMenu()

        self.statusbar = None
        self.statusbar_width = []
        self.InitStatusbar()

        # append sys path
        for p in kwargs.get('path', []):
            sys.path.append(p)

        dp.connect(self.AddMenu, 'frame.add_menu')
        dp.connect(self.DeleteMenu, 'frame.delete_menu')
        dp.connect(self.AddPanel, 'frame.add_panel')
        dp.connect(self.DeletePanel, 'frame.delete_panel')
        dp.connect(self.ShowPanel, 'frame.show_panel')
        dp.connect(self.TogglePanel, 'frame.check_menu')
        dp.connect(self.UpdateMenu, 'frame.update_menu')
        dp.connect(self.SetConfig, 'frame.set_config')
        dp.connect(self.GetConfig, 'frame.get_config')
        dp.connect(self.SetPanelTitle, 'frame.set_panel_title')
        dp.connect(self.ShowStatusText, 'frame.show_status_text')
        dp.connect(self.AddFileHistory, 'frame.add_file_history')

        # recent file list
        hsz = self.GetConfig('mainframe', 'file_history_length') or 20
        if hsz < 0:
            hsz = 10
        self.ids_file_history = wx.NewIdRef(hsz)
        self.filehistory = wx.FileHistory(hsz, self.ids_file_history[0])
        self.config.SetPath('/FileHistory')
        self.filehistory.Load(self.config)
        self.filehistory.UseMenu(self.menuRecentFiles)
        self.filehistory.AddFilesToMenu()
        self.Bind(wx.EVT_MENU_RANGE,
                  self.OnMenuFileHistory,
                  id=self.ids_file_history[0],
                  id2=self.ids_file_history[-1])



        tab_at_bottom = self.GetConfig('mainframe', 'show_tab_at_bottom', default=True)
        self.SetTabPosition(aui.AUI_NB_BOTTOM if tab_at_bottom else aui.AUI_NB_TOP)
        tab_windowlist = self.GetConfig('mainframe', 'show_tab_windowlist', default=False)
        if tab_windowlist:
            self._mgr.SetAutoNotebookStyle(self._mgr.GetAutoNotebookStyle() | aui.AUI_NB_WINDOWLIST_BUTTON)

        # load addon
        self.addon = {}
        self.InitAddOn(kwargs.get('module', ()),
                       debug=kwargs.get('debug', False))
        # initialization done, broadcasting the message so plugins can do some
        # after initialization processing.
        dp.send('frame.initialized')

        # load the perspective
        if not kwargs.get('ignore_perspective', False):
            self.LoadPerspective()
            dp.send('frame.perspective_loaded')

        # Create & Link the Drop Target Object to main window
        self.SetDropTarget(FileDropTarget(self))

        # bind events
        self.Bind(aui.EVT_AUINOTEBOOK_TAB_RIGHT_DOWN, self.OnPageRightDown)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        self.Bind(wx.EVT_ACTIVATE, self.OnActivate)
        self.Bind(aui.EVT_AUI_PANE_ACTIVATED, self.OnPaneActivated)
        self.Bind(aui.EVT_AUI_PANE_CLOSE, self.OnPaneClose)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # append the current folder, to make it easy to import the module in
        # it; move it to the end of initialization so it will not impact
        # initialization (e.g, add-on) (otherwise, for example, if current
        # folder has the propgrid repo folder, it will try to load it from
        # there, which is not correct, as the actual one in that folder shall
        # be propgrid/propgrid)
        sys.path.append('')

    def InitMenu(self):
        """initialize the menubar"""
        menubar = wx.MenuBar()
        self.SetMenuBar(menubar)

        self.AddMenu('&File:New', kind="Popup", autocreate=True)
        self.AddMenu('&File:Open', kind="Popup", autocreate=True)
        self.AddMenu('&File:Open:Open\tCtrl+O', id=wx.ID_OPEN)
        self.AddMenu('&File:Open:Sep', kind="Separator")
        self.AddMenu('&File:Sep', kind="Separator")
        self.AddMenu('&File:Recent Files', kind="Popup")
        self.menuRecentFiles = self.GetMenu(['File', 'Recent Files'])
        self.AddMenu('&File:Sep', kind="Separator")
        self.AddMenu('&File:&Quit', id=wx.ID_CLOSE)

        self.AddMenu('&View:Toolbars', kind="Popup", autocreate=True)
        self.AddMenu('&View:Sep', kind="Separator")
        self.AddMenu('&View:Panels', kind="Popup")

        self.AddMenu('&Tools', kind="Popup", autocreate=True)
        self.AddMenu('&Tools:Show tabs at the bottom', id=self.ID_SHOW_TAB_BOTTOM,
                     autocreate=True, kind="Check")
        self.AddMenu('&Tools:Show window list button', id=self.ID_SHOW_WINDOWLIST,
                     autocreate=True, kind="Check")
        self.AddMenu('&Tools:Sep', kind="Separator")

        # Connect Events
        self.Bind(wx.EVT_MENU, self.OnFileOpen, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnFileQuit, id=wx.ID_CLOSE)
        self.Bind(wx.EVT_MENU, self.OnOptions, id=self.ID_SHOW_TAB_BOTTOM)
        self.Bind(wx.EVT_UPDATE_UI, self.OnMenuCmdUI, id=self.ID_SHOW_TAB_BOTTOM)
        self.Bind(wx.EVT_MENU, self.OnOptions, id=self.ID_SHOW_WINDOWLIST)
        self.Bind(wx.EVT_UPDATE_UI, self.OnMenuCmdUI, id=self.ID_SHOW_WINDOWLIST)

    def InitStatusbar(self):
        self.statusbar = wx.StatusBar(self)
        self.statusbar_width = [-1]
        self.SetStatusBar(self.statusbar)
        self.statusbar.SetStatusWidths(self.statusbar_width)

    def OnFileQuit(self, event):
        """close the program"""
        self.Close()

    def doOpenFile(self, filename):
        resp = dp.send(signal='frame.file_drop', filename=filename)
        succeed = resp is not None and any([r[1] is not None for r in resp])
        if not succeed:
            print(f"Can't open: {filename}")

    def OnFileOpen(self, event):
        style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE
        wildcard = "All files (*.*)|*.*"
        dlg = wx.FileDialog(self, "Choose a file", "", "", wildcard, style)
        if dlg.ShowModal() == wx.ID_OK:
            for fname in dlg.GetFilenames():
                self.doOpenFile(fname)

    def SetTabPosition(self, style):
        nb_style = self._mgr.GetAutoNotebookStyle()
        if style & aui.AUI_NB_BOTTOM:
            nb_style &= ~aui.AUI_NB_TOP
            nb_style |= aui.AUI_NB_BOTTOM
        else:
            nb_style &= ~aui.AUI_NB_BOTTOM
            nb_style |= aui.AUI_NB_TOP
        self._mgr.SetAutoNotebookStyle(nb_style)

    def OnOptions(self, event):
        eid = event.GetId()
        if eid == self.ID_SHOW_TAB_BOTTOM:
            style = self._mgr.GetAutoNotebookStyle()
            self.SetTabPosition(aui.AUI_NB_TOP if style & aui.AUI_NB_BOTTOM else aui.AUI_NB_BOTTOM)
        elif eid == self.ID_SHOW_WINDOWLIST:
            self._mgr.SetAutoNotebookStyle(self._mgr.GetAutoNotebookStyle() ^ aui.AUI_NB_WINDOWLIST_BUTTON)

    def GetDefaultAddonPackages(self):
        return []

    def GetAbsoluteAddonPath(self, pkg):
        return pkg

    def GetAddOnPrefix(self):
        return 'bsm_'

    def InitAddOn(self, modules, debug=False):
        if not modules:
            modules = self.GetDefaultAddonPackages()

        # load the installed addon package
        addon_prefix = self.GetAddOnPrefix()
        modules += [name for _, name, _ in pkgutil.iter_modules() if name.startswith(addon_prefix)]

        for module in modules:
            module = module.split('+')
            options = {'debug': debug}
            if len(module) == 2:
                if all([c in 'htblr' for c in module[1]]):
                    if 'h' in module[1]:
                        options['active'] = False
                    if 't' in module[1]:
                        options['direction'] = 'Top'
                    if 'b' in module[1]:
                        options['direction'] = 'bottom'
                    if 'l' in module[1]:
                        options['direction'] = 'left'
                    if 'r' in module[1]:
                        options['direction'] = 'right'
                options['data'] = module[1]

            pkg = self.GetAbsoluteAddonPath(module[0])

            if pkg in self.addon:
                # already loaded
                continue
            self.addon[pkg] = False
            try:
                mod = importlib.import_module(pkg)
            except ImportError:
                traceback.print_exc(file=sys.stdout)
            else:
                if hasattr(mod, 'bsm_initialize'):
                    mod.bsm_initialize(self, **options)
                    self.addon[pkg] = True
                else:
                    print("Error: Invalid module: %s" % pkg)

    def OnActivate(self, event):
        if not self.closing:
            dp.send('frame.activate', activate=event.GetActive())
        event.Skip()

    def OnPaneActivated(self, event):
        """notify the window managers that the panel is activated"""
        if self.closing:
            return
        pane = event.GetPane()
        if isinstance(pane, aui.auibook.AuiNotebook):
            window = pane.GetCurrentPage()
        else:
            window = pane

        dp.send('frame.activate_panel', pane=window)

    def OnPaneClose(self, event):
        """notify the window managers that the pane is closing"""
        if self.closing:
            return
        dp.send('frame.close_pane', event=event)

    def OnPageRightDown(self, evt):
        # get the index inside the current tab control
        idx = evt.GetSelection()
        tabctrl = evt.GetEventObject()
        tabctrl.SetSelection(idx)
        page = tabctrl.GetPage(idx)
        self.OnPanelContextMenu(page)

    def OnRightDown(self, evt):
        evt.Skip()

        part = self._mgr.HitTest(*evt.GetPosition())
        if not part or part.pane.IsNotebookControl():
            return

        self.OnPanelContextMenu(part.pane.window)

    def OnPanelContextMenu(self, panel):
        if not panel:
            return
        pane = self._mgr.GetPane(panel)
        if not pane.IsOk():
            return
        menu = wx.Menu()

        pane_menu = None
        if panel in self.paneMenu:
            if menu.GetMenuItemCount() > 0:
                menu.AppendSeparator()
            pane_menu = self.paneMenu[panel]
            build_menu_from_list(pane_menu['menu'], menu)
        command = self.GetPopupMenuSelectionFromUser(menu)
        if command == wx.ID_NONE:
            return
        if command != 0 and pane_menu is not None:
            for m in pane_menu['menu']:
                if command == m.get('id', None):
                    dp.send(signal=pane_menu['rxsignal'], command=command, pane=pane)
                    break

    def AddFileHistory(self, filename):
        self.config.SetPath('/FileHistory')
        self.filehistory.AddFileToHistory(filename)
        self.filehistory.Save(self.config)
        self.config.Flush()

    def OnMenuFileHistory(self, event):
        """open the recent file"""
        fileNum = event.GetId() - self.ids_file_history[0].GetId()
        path = self.filehistory.GetHistoryFile(fileNum)
        self.filehistory.AddFileToHistory(path)
        self.doOpenFile(path)

    def ShowStatusText(self, text, index=0, width=-1):
        """set the status text"""
        if self.statusbar is None:
            return

        if index >= len(self.statusbar_width):
            exd = [0] * (index + 1 - len(self.statusbar_width))
            self.statusbar_width.extend(exd)
            self.statusbar.SetFieldsCount(index + 1)

        if width == 0:
            # auto calculate the width from text
            dc = wx.ClientDC(self.statusbar)
            width, _ = dc.GetTextExtent(text)
            width += 20

        if self.statusbar_width[index] != width:
            self.statusbar_width[index] = width
            self.statusbar.SetStatusWidths(self.statusbar_width)
        self.statusbar.SetStatusText(text, index)

    def SetPanelTitle(self, pane, title, tooltip=None, name=None, icon=None):
        """set the panel title"""
        if pane:
            info = self._mgr.GetPane(pane)
            if info and info.IsOk():
                if name is not None:
                    info.Name(name)
            self._mgr.SetPaneTitle(pane, title=str(title), tooltip=tooltip, icon=icon)
            pane.SetLabel(title)
            self.UpdatePaneMenuLabel()

    def SetConfig(self, group, **kwargs):
        if not group.startswith('/'):
            group = '/' + group
        for key, value in six.iteritems(kwargs):
            if key in ['signal', 'sender']:
                # reserved key for dp.send
                continue
            if not isinstance(value, str):
                # add sign to indicate that the value needs to be deserialize
                enc = MultiDimensionalArrayEncoder()
                value = '__bsm__' + enc.encode(value)
            self.config.SetPath(group)
            self.config.Write(key, value)

    def GetConfig(self, group, key=None, default=None):
        if not group.startswith('/'):
            group = '/' + group
        if self.config.HasGroup(group):
            self.config.SetPath(group)
            if key is None:
                rst = {}
                more, k, index = self.config.GetFirstEntry()
                while more:
                    value = self.config.Read(k)
                    if value.startswith('__bsm__'):
                        value = json.loads(value[7:], object_hook=hinted_tuple_hook)
                    rst[k] = value
                    more, k, index = self.config.GetNextEntry(index)
                return rst

            if self.config.HasEntry(key):
                value = self.config.Read(key)
                if value.startswith('__bsm__'):
                    value = json.loads(value[7:], object_hook=hinted_tuple_hook)
                return value
        return default

    def LoadPerspective(self):
        perspective = self.GetConfig('mainframe', 'perspective')
        if perspective and not wx.GetKeyState(wx.WXK_SHIFT):
            sz = self.GetConfig('mainframe', 'frame_size')
            pos = self.GetConfig('mainframe', 'frame_pos')
            if sz is not None and pos is not None:
                self.SetSize(sz)
                self.SetPosition(pos)
            self._mgr.LoadPerspective(perspective)
            self.UpdatePaneMenuLabel()

    def UpdatePaneMenuLabel(self):
        # update the menu
        for (pid, panel) in six.iteritems(self.paneAddon):
            pathlist = panel['path'].split(':')
            menuitem = self.GetMenu(pathlist[:-1])
            if not menuitem:
                continue
            pane = self._mgr.GetPane(panel['panel'])
            item = menuitem.FindItemById(pid)
            if item and pane.caption != item.GetItemLabelText():
                item.SetItemLabel(pane.caption)

    def OnClose(self, event):
        # close the app in 2 steps, to wait for all the window's events
        # triggered in 1st step to be processed
        if self.closing or not event.CanVeto():
            # step 2 finished all clean-up, do the actual close now
            self.config.Flush()
            event.Skip()
            return

        # step 1 do the clean up
        dp.send('frame.closing', event=event)
        if event.GetVeto():
            return
        self.closing = True
        # close all temporary windows
        dp.send('frame.exiting')

        # update the perspective
        sz = self.GetSize()
        pos = self.GetPosition()
        self.SetConfig('mainframe', frame_size=(sz[0], sz[1]), frame_pos=(pos[0], pos[1]))
        self.SetConfig('mainframe', perspective=self._mgr.SavePerspective())
        tab_at_bottom = (self._mgr.GetAutoNotebookStyle() & aui.AUI_NB_BOTTOM) != 0
        self.SetConfig('mainframe', show_tab_at_bottom=tab_at_bottom)
        tab_windowlist = (self._mgr.GetAutoNotebookStyle() & aui.AUI_NB_WINDOWLIST_BUTTON) != 0
        self.SetConfig('mainframe', show_tab_windowlist=tab_windowlist)

        # close all addon
        dp.send('frame.exit')

        self._mgr.UnInit()
        #del self._mgr
        event.Veto()

        # trigger the 2nd step close
        wx.CallAfter(self.Close, True)

    def GetMenu(self, pathlist, autocreate=False):
        """
        find the menu item.

        if autocreate is True, then recursive submenu creation.
        """
        if not pathlist:
            return None
        # the top level menu
        menuidx = self.GetMenuBar().FindMenu(pathlist[0])
        if menuidx == wx.NOT_FOUND:
            if autocreate:
                self.GetMenuBar().Append(wx.Menu(), pathlist[0])
                menuidx = self.GetMenuBar().FindMenu(pathlist[0])
            else:
                return None
        menuitem = self.GetMenuBar().GetMenu(menuidx)
        for p in pathlist[1:]:
            if menuitem is None:
                return None
            for m in six.moves.range(menuitem.GetMenuItemCount()):
                child = menuitem.FindItemByPosition(m)
                if not child.IsSubMenu():
                    continue
                stritem = child.GetItemLabelText()
                stritem = stritem.split('\t')[0]
                if stritem == p.split('\t')[0]:
                    menuitem = child.GetSubMenu()
                    break
            else:
                if autocreate:
                    child = self._append_menu(menuitem, p, kind='Popup')
                    menuitem = child.GetSubMenu()
                else:
                    return None
        return menuitem

    def _append_menu(self,
                     menu,
                     label,
                     id=None,
                     rxsignal=None,
                     updatesignal=None,
                     kind='Normal'):
        """
        append an item to menu.
            kind: 'Separator', 'Normal', 'Check', 'Radio', 'Popup'
        """
        if menu is None:
            return None

        if kind == 'Separator':
            return menu.AppendSeparator()
        elif kind == 'Popup':
            return menu.AppendSubMenu(wx.Menu(), label)
        else:
            newid = id
            if newid is None:
                newid = wx.NewIdRef()

            if kind == 'Check':
                newitem = wx.MenuItem(menu,
                                      newid,
                                      label,
                                      label,
                                      kind=wx.ITEM_CHECK)
            elif kind == 'Radio':
                newitem = wx.MenuItem(menu,
                                      newid,
                                      label,
                                      label,
                                      kind=wx.ITEM_RADIO)
            else:
                # 'Normal'
                newitem = wx.MenuItem(menu,
                                      newid,
                                      label,
                                      label,
                                      kind=wx.ITEM_NORMAL)
            self.menuAddon[newid] = (rxsignal, updatesignal)
            child = menu.Append(newitem)
            self.Bind(wx.EVT_MENU, self.OnMenuAddOn, id=newid)
            if updatesignal:
                self.Bind(wx.EVT_UPDATE_UI, self.OnMenuCmdUI, id=newid)
            return child
        return None

    def AddMenu(self,
                path,
                id=None,
                rxsignal=None,
                updatesignal=None,
                kind='Normal',
                autocreate=False):
        """
        add the item to menubar.
            path: e.g., New:Open:Figure

            kind: 'Separator', 'Normal', 'Check', 'Radio', 'Popup'
        """

        paths = path.split(':')
        menu = None

        if len(paths) == 1:
            # top level menu
            return self.GetMenuBar().Append(wx.Menu(), paths[0])
        elif len(paths) > 1:
            menu = self.GetMenu(paths[:-1], autocreate)
            child = self._append_menu(menu, paths[-1], id, rxsignal,
                                      updatesignal, kind)
            if child:
                return child.GetId()
        return wx.NOT_FOUND

    def DeleteMenu(self, path, id=None):
        """delete the menu item"""
        pathlist = path.split(':')
        menuitem = self.GetMenu(pathlist[:-1])
        if menuitem is None:
            return False
        if id is None:
            # delete a submenu
            for m in six.moves.range(menuitem.GetMenuItemCount()):
                item = menuitem.FindItemByPosition(m)
                stritem = item.GetItemLabelText()
                stritem = stritem.split('\t')[0]
                if stritem == pathlist[-1].split('\t')[0] and item.IsSubMenu():
                    menuitem.DestroyItem(item)
                    return True
        else:
            item = menuitem.FindItemById(id)
            if item is None:
                return False
            menuitem.DestroyItem(item)
            # unbind the event and delete from menuAddon list
            self.Unbind(wx.EVT_MENU, id=id)
            if self.menuAddon[id][1]:
                self.Unbind(wx.EVT_UPDATE_UI, id=id)
            del self.menuAddon[id]

            return True
        return False

    def OnMenuAddOn(self, event):
        idx = event.GetId()
        signal = self.menuAddon.get(idx, None)
        if signal:
            signal = signal[0]
            dp.send(signal=signal, command=idx)

    def OnMenuCmdUI(self, event):
        idx = event.GetId()

        if idx == self.ID_SHOW_TAB_BOTTOM:
            event.Check(self._mgr.GetAutoNotebookStyle() & aui.AUI_NB_BOTTOM)
        elif idx == self.ID_SHOW_WINDOWLIST:
            event.Check(self._mgr.GetAutoNotebookStyle() & aui.AUI_NB_WINDOWLIST_BUTTON)

        signal = self.menuAddon.get(idx, None)
        if signal:
            signal = signal[1]
            dp.send(signal=signal, event=event)
        else:
            event.Enable(True)


    def AddPanel(self,
                 panel,
                 title='Untitle',
                 active=True,
                 paneInfo=None,
                 target=None,
                 showhidemenu=None,
                 icon=None,
                 maximize=False,
                 direction='top',
                 minsize=None,
                 pane_menu=None,
                 tooltip="",
                 name=""
                 ):
        """add the panel to AUI"""
        if not panel:
            return False
        panel.Reparent(self)
        # hide the window for now to avoid flicker
        panel.Hide()
        # always try to find the notebook control that has the same
        # type as panel. It tries to put the same type panels in the same
        # notebook
        for pane in self._mgr.GetAllPanes():
            if isinstance(pane.window, type(panel)):
                target = pane.window
                break
        if isinstance(target, six.string_types):
            # find the target panel with caption
            for pane in self._mgr.GetAllPanes():
                if pane.caption == target:
                    target = pane.window
                    break
        targetpane = None
        try:
            if target:
                targetpane = self._mgr.GetPane(target)
                if targetpane and not targetpane.IsOk():
                    targetpane = None
        except:
            targetpane = None

        auipaneinfo = paneInfo
        dirs = {
            'top': aui.AUI_DOCK_TOP,
            'bottom': aui.AUI_DOCK_BOTTOM,
            'left': aui.AUI_DOCK_LEFT,
            'right': aui.AUI_DOCK_RIGHT,
            'center': aui.AUI_DOCK_CENTER
        }
        direction = dirs.get(direction, aui.AUI_DOCK_TOP)
        if auipaneinfo is None:
            # default panel settings. dock_row = -1 to add the pane to the
            # dock with same direction and layer, and dock_pos = 99 (a large
            # number) to add it to the right side
            auipaneinfo = aui.AuiPaneInfo().BestSize((600, 600)).Snappable()\
                          .Dockable().MinimizeButton(True).MaximizeButton(True)\
                          .Row(-1).Position(99)

        auipaneinfo.Caption(str(title)).DestroyOnClose(not showhidemenu).Icon(icon)\
                   .Direction(direction).Tooltip(str(tooltip))

        if not self._mgr.GetAllPanes():
            # set the first pane to be center pane
            auipaneinfo.DestroyOnClose(False).CenterPane()
            active = True

        # auto generate the unique panel name
        if name == "":
            name = "pane-%d" % self._pane_num
        self._pane_num += 1
        auipaneinfo.Name(name)
        if minsize:
            auipaneinfo.MinSize(minsize)

        panel.SetLabel(title)
        self._mgr.AddPane(panel, auipaneinfo, target=targetpane)
        if maximize:
            self._mgr.MaximizePane(auipaneinfo)
        self.ShowPanel(panel, active)
        # add the menu item to show/hide the panel
        if showhidemenu:
            mid = self.AddMenu(showhidemenu,
                               rxsignal='frame.check_menu',
                               updatesignal='frame.update_menu',
                               kind='Check',
                               autocreate=True)
            if mid != wx.NOT_FOUND:
                self.paneAddon[mid] = {'panel': panel, 'path': showhidemenu}
        if pane_menu is not None:
            self.paneMenu[panel] = pane_menu
        return True

    def DeletePanel(self, panel):
        """hide and destroy the panel"""
        # delete the show/hide menu
        for (pid, pane) in six.iteritems(self.paneAddon):
            if panel == pane['panel']:
                self.DeleteMenu(pane['path'], pid)
                del self.paneAddon[pid]
                break

        # delete the pane menu
        self.paneMenu.pop(panel, None)

        # delete the panel from the manager
        pane = self._mgr.GetPane(panel)
        if pane is None or not pane.IsOk():
            return False
        pane.DestroyOnClose(True)
        self._mgr.ClosePane(pane)
        self._mgr.Update()
        return True

    def ShowPanel(self, panel, show=True, focus=False):
        """show/hide the panel"""
        pane = self._mgr.GetPane(panel)
        if pane is None or not pane.IsOk():
            return False
        root_pane = pane
        if pane.IsNotebookPage():
            root_pane = self._mgr.GetPane(panel.GetParent())
        if show and root_pane.IsOk() and root_pane.IsMinimized():
            # the panel is minimized, restore it first
            self._mgr.RestoreMinimizedPane(root_pane)
        self._mgr.ShowPane(panel, show)
        if focus:
            panel.SetFocus()
        return True

    def TogglePanel(self, command):
        """toggle the display of the panel"""
        pane = self.paneAddon.get(command, None)
        if not pane:
            return
        panel = pane['panel']
        # IsShown may not work, since the panel may be hidden while IsShown()
        # returns True
        show = panel.IsShownOnScreen()
        self.ShowPanel(panel, not show)

    def UpdateMenu(self, event):
        """update the menu checkbox"""
        pane = self.paneAddon.get(event.GetId(), None)
        if not pane:
            return
        panel = pane['panel']
        show = panel.IsShownOnScreen()
        event.Check(show)
