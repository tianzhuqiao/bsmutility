"""
    DirListCtrl/DirTreeCtrl/DirTreeList
    @summary: A list/tree/treelist control to show directories
    The idea is based on the DirTreeCtrl 0.9.0 from Collin Green (http://keeyai.com)
"""

import os
import abc
import platform
import stat
from pathlib import Path
import traceback
import datetime
import shutil
import fnmatch
import wx
import wx.py.dispatcher as dp
import wx.lib.agw.hypertreelist as HTL
from .findlistctrl import ListCtrlBase
from .findmixin import FindTreeMixin
from .utility import open_file_with_default_app, get_file_icon, \
                     show_file_in_finder, get_file_finder_name
wxEVT_DIR_OPEN = wx.NewEventType()

EVT_DIR_OPEN = wx.PyEventBinder(wxEVT_DIR_OPEN, 1)

class DirEvent(wx.PyCommandEvent):
    def __init__(self, commandType, path, eid=0, **kwargs):
        wx.PyCommandEvent.__init__(self, commandType, eid)
        self.path = path
        self.veto = False
        self.data = kwargs

    def GetPath(self):
        """return the attached path"""
        return self.path

    def SetPath(self, path):
        """attach the path string"""
        self.path = path

    def Veto(self, veto=True):
        """refuse the event"""
        self.veto = veto

    def GetVeto(self):
        """return whether the event is refused"""
        return self.veto

    def GetData(self):
        return self.data

def is_hidden(filepath):

    filepath = os.path.abspath(filepath)
    name = os.path.basename(filepath)
    if platform.system() == 'Darwin':       # macOS
        return name.startswith('.')
    elif platform.system() == 'Windows':    # Windows
        return bool(os.stat(filepath).st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
    else:                                   # linux variants
        return name.startswith('.')

class Directory(object):
    """Simple class for using as the data object in the DirTreeCtrl"""
    __name__ = 'Directory'

    def __init__(self, directory=''):
        self.directory = directory

class DirMixin:
    """helper class to handle files/folders in a folder"""

    ID_COPY_NAME = wx.NewIdRef()
    ID_COPY_PATH = wx.NewIdRef()
    ID_COPY_PATH_REL = wx.NewIdRef()
    ID_COPY_PATH_POSIX = wx.NewIdRef()
    ID_COPY_PATH_REL_POSIX = wx.NewIdRef()
    ID_OPEN_IN_FINDER = wx.NewIdRef()
    ID_RENAME = wx.NewIdRef()
    ID_PASTE_FOLDER = wx.NewIdRef()

    FOLDER = 0
    FILE = 1
    def __init__(self):

        self.rootdir = ""
        self.pattern = None
        self.show_hidden = True
        self.active_items = []

        # some hack-ish code here to deal with imagelists
        self.iconentries = {}
        self.imagelist = wx.ImageList(16, 16)

        # blank default
        self.iconentries['default'] = -1
        self.iconentries['directory'] = -1
        self.iconentries['directory_open'] = -1
        scale = 1
        if not wx.Platform == '__WXMSW__':
            # looks like Windows doesn't support high DPI image (wx 4.2.2)
            scale = self.GetDPIScaleFactor()
        bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (int(16*scale), int(16*scale)))
        bmp.SetScaleFactor(scale)
        self.addBitmap(bmp, 'directory')
        bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_OTHER, (int(16*scale), int(16*scale)))
        bmp.SetScaleFactor(scale)
        self.addBitmap(bmp, 'directory_open')
        bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (int(16*scale), int(16*scale)))
        bmp.SetScaleFactor(scale)
        self.addBitmap(bmp, 'default')

        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_DELETE)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_OPEN_IN_FINDER)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_COPY_NAME)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_COPY_PATH)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_COPY_PATH_REL)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_COPY_PATH_POSIX)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_COPY_PATH_REL_POSIX)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_RENAME)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self.OnProcessEvent, id=self.ID_PASTE_FOLDER)

        accel = self.BuildAccelTable()

        self.accel = wx.AcceleratorTable(accel)
        self.SetAcceleratorTable(self.accel)

    def BuildAccelTable(self):
        accel = [
            #(wx.ACCEL_CTRL, wx.WXK_RETURN, wx.ID_OPEN),
            (wx.ACCEL_ALT | wx.ACCEL_CTRL, ord('R'), self.ID_OPEN_IN_FINDER),
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY),
            (wx.ACCEL_ALT | wx.ACCEL_CTRL, ord('N'), self.ID_COPY_NAME),
            (wx.ACCEL_ALT | wx.ACCEL_CTRL, ord('C'), self.ID_COPY_PATH),
            (wx.ACCEL_ALT | wx.ACCEL_SHIFT | wx.ACCEL_CTRL, ord('C'), self.ID_COPY_PATH_REL),
            (wx.ACCEL_SHIFT, wx.WXK_RETURN, self.ID_RENAME),
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, wx.ID_DELETE),
        ]
        return accel

    def addBitmap(self, bitmap, name):
        try:
            if bitmap:
                key = self.imagelist.Add(bitmap)
                self.iconentries[name] = key
        except:
            traceback.print_exc()

    def addIcon(self, filepath, wxBitmapType, name):
        """Adds an icon to the imagelist and registers it with the iconentries dict
        using the given name. Use so that you can assign custom icons to the tree
        just by passing in the value stored in self.iconentries[name]
        @param filepath: path to the image
        @param wxBitmapType: wx constant for the file type - eg wx.BITMAP_TYPE_PNG
        @param name: name to use as a key in the self.iconentries dict -
                     get your imagekey by calling self.iconentries[name]
        """
        try:
            if os.path.exists(filepath):
                key = self.imagelist.Add(wx.Bitmap(filepath, wxBitmapType))
                self.iconentries[name] = key
        except:
            traceback.print_exc()

    def GetRootDir(self):
        return self.rootdir

    def GetItemPath(self, item):
        filename = self.GetItemText(item)
        rootdir = self.GetRootDir()
        return os.path.join(rootdir, filename)

    def SetRootDir(self, directory, pattern=None, show_hidden=True):
        # check if directory exists and is a directory
        if not os.path.isdir(directory):
            raise ValueError("%s is not a valid directory" % directory)

        self.DeleteAllItems()

        self.rootdir = directory
        self.pattern = pattern
        self.show_hidden = show_hidden
        self.LoadPath(directory)

    def GetPathInfo(self, filepath):
        # return a list of info to be displayed
        name = os.path.basename(filepath)
        return [name]

    def LoadPath(self, directory):
        """Private function that gets called to load the file list
        for the given directory and append the items to the tree.
        Throws an exception if the directory is invalid.

        @note: does not add items if the node already has children"""
        # check if directory exists and is a directory
        if not os.path.isdir(directory):
            raise ValueError(f"{directory} is not a valid directory")

        # get files in directory
        try:
            files = os.listdir(directory)
        except:
            traceback.print_exc()
            return []
        files_all = []
        folders_all = []
        # add directory nodes to tree
        for f in files:
            # if directory, tell tree it has children
            if os.path.isdir(os.path.join(directory, f)):
                folders_all.append(f)
            else:
                files_all.append(f)
        if self.pattern:
            files_all = fnmatch.filter(files_all, self.pattern)
        if not self.show_hidden:
            folders_all = [f for f in folders_all if not is_hidden(os.path.join(directory, f))]
            files_all = [f for f in files_all if not is_hidden(os.path.join(directory, f))]

        data = []
        folders_all.sort(key=lambda y: y.lower())
        files_all.sort(key=lambda y: y.lower())
        for f in folders_all:
            info = self.GetPathInfo(os.path.join(directory, f))
            data.append(info + [self.iconentries['directory'], self.FOLDER])

        # add file nodes
        for f in files_all:
            # process the file extension to build image list
            imagekey = self.processFileExtension(os.path.join(
                directory, f))

            info = self.GetPathInfo(os.path.join(directory, f))
            data.append(info + [imagekey, self.FILE])
        return data

    def getFileExtension(self, filename):
        """Helper function for getting a file's extension"""
        # check if directory
        if not os.path.isdir(filename):
            # search for the last period
            _, ext = os.path.splitext(filename)
            return ext
        else:
            return 'directory'

    def processFileExtension(self, filename):
        """Helper function. Called for files and collects all the necessary
        icons into in image list which is re-passed into the tree every time
        (imagelists are a lame way to handle images)"""
        ext = self.getFileExtension(filename)
        ext = ext.lower()

        excluded = ['', '.exe', '.ico']
        # do nothing if no extension found or in excluded list
        if ext not in excluded:

            # only add if we dont already have an entry for this item
            if ext not in self.iconentries:

                # sometimes it just crashes
                bitmap = get_file_icon(filename)
                if bitmap is not None:
                    # add to imagelist and store returned key
                    iconkey = self.imagelist.Add(bitmap)
                    self.iconentries[ext] = iconkey
                    # update tree with new imagelist - inefficient
                    #self.SetImageList(self.imagelist)

            if ext in self.iconentries:
                return self.iconentries[ext]

        elif ext in ['.exe', '.ico']:
            # if exe, get first icon out of it
            if filename not in self.iconentries:
                bitmap = get_file_icon(filename)
                if bitmap is not None:
                    # add to imagelist and store returned key
                    iconkey = self.imagelist.Add(bitmap)
                    self.iconentries[filename] = iconkey
                    # update tree with new imagelist - inefficient
                    #self.SetImageList(self.imagelist)
            if filename in self.iconentries:
                return self.iconentries[filename]

        # if no key returned already, return default
        return self.iconentries['default']

    def HitTestItem(self, pos):
        # hit test to see if pos is on some item
        # return (is_on, item)
        return False, None

    def OnContextMenu(self, event):
        ison, item = self.HitTestItem(event.GetPosition())
        if ison:
            # right click on an item
            self.OnRightClickItem(item)
            return

        self.active_items = [self.GetRootItem()]
        menu = wx.Menu()
        menu.Append(wx.ID_NEW, "New folder")
        manager = get_file_finder_name()
        menu.Append(self.ID_OPEN_IN_FINDER, f"Reveal in {manager}\tAlt+Ctrl+R")
        if wx.TheClipboard.Open():
            data = wx.FileDataObject()
            if wx.TheClipboard.GetData(data):
                menu.AppendSeparator()
                menu.Append(self.ID_PASTE_FOLDER, "Paste\tCtrl+V")
            wx.TheClipboard.Close()

        menu.AppendSeparator()
        menu.Append(self.ID_COPY_NAME, "Copy name\tAlt+Ctrl+N")
        menu.Append(self.ID_COPY_PATH, "Copy path\tAlt+Ctrl+C")
        menu.Append(self.ID_COPY_PATH_REL, "Copy relative path\tAlt+Shift+Ctrl+C")

        if platform.system() == 'Windows':
            menu.Append(self.ID_COPY_PATH_POSIX, 'Copy path with forward slashes (/)')
            menu.Append(self.ID_COPY_PATH_REL_POSIX, 'Copy relative path with forward slashes (/)')

        self.PopupMenu(menu)
        menu.Destroy()

    def OnItemActivated(self, event):
        currentItem = self.GetItemFromEvent(event)
        self.open([currentItem])

    def OnRightClickItem(self, item):
        self.Select(item)
        self.active_items = self.GetSelections()
        menu = wx.Menu()
        menu.Append(wx.ID_OPEN, "Open\tCtrl+Enter")
        menu.Append(self.ID_OPEN_IN_FINDER, f"Reveal in {get_file_finder_name()}\tAlt+Ctrl+R")
        menu.AppendSeparator()
        #menu.Append(wx.ID_CUT, "Cut\tCtrl+X")
        menu.Append(wx.ID_COPY, "Copy\tCtrl+C")
        if wx.TheClipboard.Open():
            data = wx.FileDataObject()
            if wx.TheClipboard.GetData(data):
                menu.Append(self.ID_PASTE_FOLDER, "Paste\tCtrl+V")
            wx.TheClipboard.Close()
        menu.AppendSeparator()
        menu.Append(self.ID_COPY_NAME, "Copy name\tAlt+Ctrl+N")
        menu.Append(self.ID_COPY_PATH, "Copy path\tAlt+Ctrl+C")
        menu.Append(self.ID_COPY_PATH_REL, "Copy relative path\tAlt+Shift+Ctrl+C")

        if platform.system() == 'Windows':
            menu.Append(self.ID_COPY_PATH_POSIX, 'Copy path with forward slashes (/)')
            menu.Append(self.ID_COPY_PATH_REL_POSIX, 'Copy relative path with forward slashes (/)')

        menu.AppendSeparator()
        menu.Append(self.ID_RENAME, "Rename\tReturn")
        menu.Append(wx.ID_DELETE, "Delete\tDelete")
        self.PopupMenu(menu)
        menu.Destroy()

    def copy(self, items):
        data = wx.FileDataObject()
        for item in items:
            data.AddFile(self.GetItemPath(item))

        wx.TheClipboard.Open()
        wx.TheClipboard.SetData(data)
        wx.TheClipboard.Close()

    def delete(self, items):
        confirm = True
        for item in items:
            path = self.GetItemPath(item)
            if confirm:
                _, basename = os.path.split(path)
                msg = f'Do you want to delete "{basename}"?'
                parent = self.GetTopLevelParent()
                dlg = wx.RichMessageDialog(self, msg, parent.GetLabel(), wx.YES_NO)
                if len(items) > 1:
                    dlg.ShowCheckBox('Do not ask me again', False)
                result = dlg.ShowModal() == wx.ID_YES
                confirm = not dlg.IsCheckBoxChecked()
                dlg.Destroy()
                if not result:
                    continue
            try:
                if os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except:
                traceback.print_exc()
                continue
            self.Delete(item)

    def OnProcessEvent(self, event):
        evtId = event.GetId()
        if not self.active_items:
            self.active_items = self.GetSelections()
        self.do_process(evtId, self.active_items)
        self.active_items = []

    def do_process(self, evtId, items):
        if evtId == wx.ID_OPEN:
            self.open(items)
        elif evtId == self.ID_OPEN_IN_FINDER:
            self.open_in_finder(items)
        elif evtId in (wx.ID_COPY, wx.ID_CUT):
            self.copy(items)
            if evtId == wx.ID_CUT:
                self.delete(items)
        elif evtId == wx.ID_DELETE:
            self.delete(items)
        elif evtId == wx.ID_CLEAR:
            self.tree.DeleteAllItems()
        elif evtId in (self.ID_COPY_NAME, self.ID_COPY_PATH, self.ID_COPY_PATH_REL,
                       self.ID_COPY_PATH_POSIX, self.ID_COPY_PATH_REL_POSIX):
            self.copy_path(items,
                           relative=evtId in [self.ID_COPY_PATH_REL, self.ID_COPY_PATH_REL_POSIX],
                           posix=evtId in [self.ID_COPY_PATH_POSIX, self.ID_COPY_PATH_REL_POSIX],
                           basename=evtId in [self.ID_COPY_NAME])
        elif evtId == self.ID_RENAME:
            if items:
                # only edit the first item
                self.EditLabel(items[0])
        elif evtId == wx.ID_NEW:
            self.new_folder()
        elif evtId == self.ID_PASTE_FOLDER:
            if wx.TheClipboard.Open():
                data = wx.FileDataObject()
                files_copied = []
                if len(items) == 1:
                    item = items[0]
                    if wx.TheClipboard.GetData(data):
                        root_dir = self.GetItemPath(item)
                        if os.path.isfile(root_dir):
                            root_dir = os.path.dirname(root_dir)
                        for src in data.GetFilenames():
                            des = os.path.join(root_dir, os.path.basename(src))
                            if os.path.abspath(des) == os.path.abspath(src):
                                # same location, ignore it
                                continue
                            shutil.copy2(src, des)
                            files_copied.append(os.path.basename(src))
                wx.TheClipboard.Close()
                if files_copied:
                    if self.SendDirEvent(wxEVT_DIR_OPEN, root_dir):
                        self.SetRootDir(root_dir, self.pattern, self.show_hidden)
                    for filename in files_copied:
                        self.HighlightPath(filename)

    def HighlightPath(self, filename):
        return

    def new_folder(self):
        title = self.GetTopLevelParent().GetLabel()
        dlg = wx.TextEntryDialog(self, "Folder name", caption=title, value='')
        dlg.ShowModal()
        filename = dlg.GetValue()
        dlg.Destroy()
        if not filename:
            return
        root_dir = self.GetRootDir()
        new_folder = os.path.join(root_dir, filename)
        if  os.path.exists(new_folder):
            msg = f"{filename} already exists. Please choose a different name."
            dlg = wx.MessageDialog(self, msg, title, style=wx.OK)
            dlg.ShowModal()
            dlg.Destroy()
            return

        os.makedirs(new_folder)
        self.SetRootDir(root_dir, self.pattern, self.show_hidden)

        self.HighlightPath(filename)

    def copy_path(self, items, relative=False, posix=False, basename=False):
        file_path = []
        for item in items:
            path = self.GetItemPath(item)
            if relative:
                path = os.path.relpath(path, os.getcwd())
            if posix:
                path = Path(path).as_posix()
            if basename:
                path = Path(path).name
            file_path.append(path)

        clipData = wx.TextDataObject()
        clipData.SetText("\n".join(file_path))
        wx.TheClipboard.Open()
        wx.TheClipboard.SetData(clipData)
        wx.TheClipboard.Close()

    def GetItemFromEvent(self, event):
        return event.GetItem()

    def OnRename(self, event):
        label = event.GetLabel()
        item = self.GetItemFromEvent(event)
        old_label = self.GetItemText(item)
        if label == old_label or not label:
            return
        old_path = self.GetItemPath(item)
        new_path = os.path.join(os.path.dirname(old_path), label)
        os.rename(old_path, new_path)

    def open(self, items):
        for item in items:
            filepath = self.GetItemPath(item)
            if os.path.isdir(filepath):
                if self.SendDirEvent(wxEVT_DIR_OPEN, filepath):
                    self.SetRootDir(filepath, pattern=self.pattern, show_hidden=self.show_hidden)
                return
            (_, ext) = os.path.splitext(filepath)

            # try to open it with the main app
            resp = dp.send(signal='frame.file_drop', filename=filepath)
            if resp is not None:
                for r in resp:
                    if r[1] is not None:
                        # succeed
                        return
            # if failed, try to open it with OS
            open_file_with_default_app(filepath)

    def open_in_finder(self, items):
        for item in items:
            filepath = self.GetItemPath(item)
            show_file_in_finder(filepath)

    def SendDirEvent(self, event, path, **kwargs):
        """send the property event to the parent"""
        # prepare the event
        if isinstance(event, DirEvent):
            evt = event
        elif isinstance(event, int):
            evt = DirEvent(event, path, **kwargs)
        else:
            raise ValueError()

        evt.SetId(self.GetId())
        eventObject = self.GetParent()
        evt.SetEventObject(eventObject)
        evtHandler = eventObject.GetEventHandler()

        evtHandler.ProcessEvent(evt)
        return not evt.GetVeto()

    def LoadConfig(self):
        pass

    def SaveConfig(self):
        pass

# bytes pretty-printing
UNITS_MAPPING = [
    (1<<50, ' PB'),
    (1<<40, ' TB'),
    (1<<30, ' GB'),
    (1<<20, ' MB'),
    (1<<10, ' KB'),
    (1, (' byte', ' bytes')),
]


def pretty_size(byte, units=None):
    """Get human-readable file sizes.
    simplified version of https://pypi.python.org/pypi/hurry.filesize/
    """
    if units is None:
        units = UNITS_MAPPING
    factor = None
    suffix = None
    for factor, suffix in units:
        if byte >= factor:
            break
    if factor is None or suffix is None:
        return str(byte) + ' byte'
    amount = int(byte / factor)

    if isinstance(suffix, tuple):
        singular, multiple = suffix
        if amount == 1:
            suffix = singular
        else:
            suffix = multiple
    return str(amount) + suffix

class DirWithColumnsMixin(DirMixin):
    ID_AUTO_COL_SIZE = wx.NewIdRef()
    ID_AUTO_COL_SIZE_ALL = wx.NewIdRef()

    columns = [
                {'name': 'Name', 'visible': True, 'id': wx.NewIdRef(), 'optional': False, 'min_width': 200, 'align': 'left'},
                {'name': 'Data modified', 'visible': True, 'id': wx.NewIdRef(), 'optional': True, 'min_width': 100, 'align': 'left'},
                {'name': 'Data created', 'visible': False, 'id': wx.NewIdRef(), 'optional': True, 'min_width': 100, 'align': 'left'},
                {'name': 'Type', 'visible': False, 'id': wx.NewIdRef(), 'optional': True, 'min_width': 60, 'align': 'left'},
                {'name': 'Size', 'visible': True, 'id': wx.NewIdRef(), 'optional': True, 'min_width': 80, 'align': 'right'}
                ]

    def __init__(self):
        DirMixin.__init__(self)

        self.columns_shown = list(range(len(self.columns)))


    def OnColRightClick(self, event):
        menu = wx.Menu()

        menu.Append(self.ID_AUTO_COL_SIZE, 'Size columns to fit')
        menu.Append(self.ID_AUTO_COL_SIZE_ALL, 'Size all columns to fit')
        menu.AppendSeparator()
        for col in self.columns:
            item = menu.AppendCheckItem(col['id'], col['name'])
            item.Check(col['visible'])
            item.Enable(col['optional'])

        cmd = self.GetPopupMenuSelectionFromUser(menu)

        if cmd == wx.ID_NONE:
            return
        if cmd == self.ID_AUTO_COL_SIZE:
            self.AutoSizeColumns([event.GetColumn()])
        elif cmd == self.ID_AUTO_COL_SIZE_ALL:
            self.AutoSizeColumns()
        else:
            for col in self.columns:
                if cmd == col['id']:
                    col['visible'] = not col['visible']

            self.BuildColumns()

    @abc.abstractmethod
    def BuildColumns(self):
        pass

    @abc.abstractmethod
    def AutoSizeColumns(self, columns=None):
        pass

    def GetItemColumnText(self, item, column):
        column_name = self.columns[column]['name']
        if column_name in ['Data modified', 'Data created']:
            # modified/create time
            mtime = datetime.datetime.fromtimestamp(item[column])
            mtime = mtime.strftime("%m/%d/%Y %H:%M:%S")
            return mtime
        elif column_name == 'Size':
            # size:
            if item[-1] == self.FOLDER:
                # folder
                return ""
            size = item[column]
            return  pretty_size(size)
        return item[column]

    def GetPathInfo(self, filepath):
        info = super().GetPathInfo(filepath)
        p = Path(filepath)
        try:
            info.append(p.stat().st_mtime)
        except:
            info.append(0)
        try:
            info.append(p.stat().st_ctime)
        except:
            info.append(0)
        ext = ''
        try:
            ext = p.suffix
            if p.is_dir():
                ext = "Folder"
        except:
            pass
        info.append(ext)
        try:
            info.append(p.stat().st_size)
        except:
            info.append(0)
        return info

    def GetShownColumns(self):
        return self.columns_shown

    def SetShowColumns(self, cols):
        for idx, col in enumerate(self.columns):
            if not col['optional']:
                continue
            col['visible'] = idx in cols

        self.BuildColumns()

    def LoadConfig(self):
        super().LoadConfig()

        resp = dp.send('frame.get_config', group='dirlistctrl', key='columns_shown')
        if resp and resp[0][1] is not None:
            self.SetShowColumns(resp[0][1])

    def SaveConfig(self):
        super().SaveConfig()

        dp.send('frame.set_config', group='dirlistctrl', columns_shown=self.GetShownColumns())

class DirTreeMixin(DirMixin):

    def __init__(self):
        DirMixin.__init__(self)

        # option to delete node items from tree when node is collapsed
        self.delete_on_collapse = False

    def SetDeleteOnCollapse(self, selection):
        """Sets the tree option to delete leaf items when the node is
        collapsed. Will slow down the tree slightly but will probably save memory."""
        if isinstance(selection, bool):
            self.delete_on_collapse = selection

    def SetRootDir(self, directory, pattern=None, show_hidden=True):

        if not os.path.isdir(directory):
            raise ValueError(f"{directory} is not a valid directory")

        self.rootdir = directory
        self.pattern = pattern
        self.show_hidden = show_hidden

        # delete existing root, if any
        self.DeleteAllItems()

        # add directory as root
        root = self.AddRoot(directory)
        self.SetItemData(root, Directory(directory))
        self.SetItemImage(root, self.iconentries['directory'],
                          wx.TreeItemIcon_Normal)
        self.SetItemImage(root, self.iconentries['directory_open'],
                          wx.TreeItemIcon_Expanded)

        self.LoadDir(root, directory)

    def UpdateItem(self, item, d):
        pass

    def LoadDir(self, item, directory):

        if self.GetChildrenCount(item) > 0:
            # already loaded
            return

        data = self.LoadPath(directory)

        # process the file extension to build image list
        for d in data:
            # populate the tree
            if d[-1] == self.FOLDER:
                child = self.AppendItem(item, d[0])
                # directory
                self.SetItemImage(child, self.iconentries['directory'],
                                  which=wx.TreeItemIcon_Normal)
                self.SetItemImage(child, self.iconentries['directory_open'],
                                  which=wx.TreeItemIcon_Expanded)
                self.SetItemHasChildren(child, True)

                # save item path for expanding later
                self.SetItemData(child, Directory(os.path.join(directory, d[0])))
            else:
                # process the file extension to build image list
                child = self.AppendItem(item, d[0], image=d[-2])

            self.UpdateItem(child, d)

        return data

    def GetItemPath(self, item):
        if item == self.GetRootItem():
            d = self.GetItemData(item)
            if isinstance(d, Directory):
                return d.directory
            return None

        filename = self.GetItemText(item)
        parentItem = self.GetItemParent(item)
        d = self.GetItemData(parentItem)
        if isinstance(d, Directory):
            filepath = os.path.join(d.directory, filename)
        else:
            return None
        return filepath

    def TreeItemExpanding(self, event):
        """Called when a node is about to expand. Loads the node's
        files from the file system."""
        item = event.GetItem()

        # check if item has directory data
        if isinstance(self.GetItemData(item), Directory):
            d = self.GetItemData(item)
            self.LoadDir(item, d.directory)
        else:
            pass

        event.Skip()

    def TreeItemCollapsing(self, event):
        """Called when a node is about to collapse. Removes
        the children from the tree if self.delete_on_collapse is
        set - see L{SetDeleteOnCollapse}
        """
        item = event.GetItem()

        # delete the node's children if that tree option is set
        if self.delete_on_collapse:
            self.DeleteChildren(item)

        event.Skip()

    def UpdateFolder(self, item):
        # the folder name may be changed, update its corresponding data
        filepath = self.GetItemPath(item)
        self.SetItemData(item, Directory(filepath))

    def OnRename(self, event):

        # update the folder data
        item = event.GetItem()
        filepath = self.GetItemPath(item)
        if os.path.isdir(filepath):
            # call later to give it sometime for the 'label' to be updated
            wx.CallAfter(self.UpdateFolder, item)

        super().OnRename(event)


class DirTreeCtrl(wx.TreeCtrl, DirTreeMixin, FindTreeMixin):
    """
    A wx.TreeCtrl that is used for displaying directory structures.
    Virtually handles paths to help with memory management.
    """
    def __init__(self, parent, **kwargs):

        if 'style' not in kwargs:
            kwargs['style'] = (wx.TR_DEFAULT_STYLE
                                   | wx.TR_HAS_VARIABLE_ROW_HEIGHT
                                   | wx.TR_HIDE_ROOT
                                   | wx.TR_EDIT_LABELS)
        wx.TreeCtrl.__init__(self, parent, **kwargs)
        DirTreeMixin.__init__(self)
        FindTreeMixin.__init__(self)

        self.SetImageList(self.imagelist)


        self.Select = self.SelectItem
        # bind events
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.TreeItemExpanding)
        self.Bind(wx.EVT_TREE_ITEM_COLLAPSING, self.TreeItemCollapsing)

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self.Bind(wx.EVT_TREE_END_LABEL_EDIT, self.OnRename)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnItemActivated)

    def BuildAccelTable(self):
        accel = DirTreeMixin.BuildAccelTable(self)
        accel2 = FindTreeMixin.BuildAccelTable(self)
        return accel + accel2

    def HitTestItem(self, pos):
        item, _ = self.HitTest(self.ScreenToClient(pos))
        return item.IsOk(), item

    def HighlightPath(self, filename):
        root_item = self.GetRootItem()
        item, cookie = self.GetFirstChild(root_item)
        while item.IsOk():
            text = self.GetItemText(item)
            if text == filename:
                self.SelectItem(item)
                self.EnsureVisible(item)
                break
            item, cookie = self.GetNextChild(root_item, cookie)

    def GetNextItem(self, item):
        if not item.IsOk():
            return item
        if isinstance(self.GetItemData(item), Directory):
            d = self.GetItemData(item)
            self.LoadDir(item, d.directory)

        return super().GetNextItem(item)

    def GetPrevItem(self, item):
        if not item.IsOk():
            return item
        if isinstance(self.GetItemData(item), Directory):
            d = self.GetItemData(item)
            self.LoadDir(item, d.directory)

        return super().GetPrevItem(item)

class DirListCtrl(ListCtrlBase, DirWithColumnsMixin):
    """
    A wx.ListCtrl that is used for displaying directory structures.
    Virtually handles paths to help with memory management.
    """

    def __init__(self, parent, *args, **kwds):

        ListCtrlBase.__init__(self, parent, *args, **kwds)
        DirWithColumnsMixin.__init__(self)

        # disable last column auto width
        self.EnableAutoWidth(False)
        # disable alternate row colour
        self.EnableAlternateRowColours(False)
        self.ExtendRulesAndAlternateColour(False)

        self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)

        self.Bind(wx.EVT_LIST_COL_RIGHT_CLICK, self.OnColRightClick)
        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnRename)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated)

    def OnRightClick(self, event):
        # ignore the default context menu in ListCtrlBase
        pass

    def SetShowColumns(self, cols):
        super().SetShowColumns(cols)

        self.Fill(self.pattern)

    def OnColRightClick(self, event):
        super().OnColRightClick(event)

        self.Fill(self.pattern)

    def BuildColumns(self):
        self.DeleteAllColumns()
        self.columns_shown = []
        for idx, col in enumerate(self.columns):
            if not col['visible']:
                continue
            self.columns_shown.append(idx)
            fmt = wx.LIST_FORMAT_LEFT
            if col['align'] == 'right':
                fmt = wx.LIST_FORMAT_RIGHT
            elif col['align'] == 'center':
                fmt = wx.LIST_FORMAT_CENTER
            self.AppendColumn(col['name'], format=fmt, width=col['min_width'])

    def AutoSizeColumns(self, columns=None):
        if columns is None:
            columns = range(self.GetColumnCount())
        for col in columns:
            self.SetColumnWidth(col, wx.LIST_AUTOSIZE)
            column = self.columns_shown[col]
            if self.GetColumnWidth(col) < self.columns[column]['min_width']:
                self.SetColumnWidth(col, self.columns[column]['min_width'])

    def OnGetItemText(self, item, column):
        if column < self.data_start_column:
            return super().OnGetItemText()
        column = self.columns_shown[column]
        return self.GetItemColumnText(self.data_shown[item], column)

    def OnGetItemImage(self, item):
        return self.data_shown[item][-2]

    def GetItemFromEvent(self, event):
        return event.GetIndex()

    def FindText(self, start, end, text, flags=0):
        direction = 1 if end > start else -1
        for i in range(start, end+direction, direction):
            # press esc to quit find, in case the list is very large
            if wx.GetKeyState(wx.WXK_ESCAPE):
                break
            m = self.data_shown[i][0]
            if self.Search(m, text, flags):
                return i

        # not found
        return -1

    def SortBy(self, column, ascending):
        column = self.columns_shown[column]
        column_name = self.columns[column]['name']
        if column_name == "Name":
            self.data.sort(key=lambda x: str(x[column]).lower(), reverse=not ascending)
        else:
            self.data.sort(key=lambda x: x[column], reverse=not ascending)

        self.data.sort(key=lambda x: str(x[-1]).lower())

    def GetItemPath(self, item):
        if isinstance(item, wx.ListItem):
            item = item.GetId()
        rootdir = self.GetRootDir()
        if item == self.GetRootItem():
            return rootdir
        filename = self.GetItemText(item)
        return os.path.join(rootdir, filename)

    def LoadPath(self, directory):
        # check if directory exists and is a directory
        self.data = super().LoadPath(directory)
        self.Fill(self.pattern)

        self.AutoSizeColumns()
        return self.data

    def Delete(self, item):
        if isinstance(item, wx.ListItem):
            item = item.GetId()

        self.data.pop(item)
        self.Fill(self.pattern)

    def OnRename(self, event):
        DirWithColumnsMixin.OnRename(self, event)

        label = event.GetLabel()
        item = self.GetItemFromEvent(event)
        self.UpdateData(item, label)

    def UpdateData(self, index, name):
        self.data_shown[index][0] = name

    def HitTestItem(self, pos):
        item, _ = self.HitTest(self.ScreenToClient(pos))
        return item >= 0, item

    def LoadConfig(self):
        DirWithColumnsMixin.LoadConfig(self)

        resp = dp.send('frame.get_config', group='dirlistctrl', key='columns_order')
        if resp and resp[0][1] is not None:
            self.SetColumnsOrder(resp[0][1])

        sort_column = None
        resp = dp.send('frame.get_config', group='dirlistctrl', key='sort_column')
        if resp and resp[0][1] is not None:
            sort_column = resp[0][1]

        sort_order = None
        resp = dp.send('frame.get_config', group='dirlistctrl', key='sort_order')
        if resp and resp[0][1] is not None:
            sort_order = resp[0][1]

        if sort_column is not None and sort_order is not None:
            if 0 <= sort_column < self.GetColumnCount():
                self.ShowSortIndicator(sort_column, sort_order)

    def SaveConfig(self):
        DirWithColumnsMixin.LoadConfig(self)
        dp.send('frame.set_config', group='dirlistctrl', columns_order=self.GetColumnsOrder())

        col = self.GetSortIndicator()
        ascending = self.IsAscendingSortIndicator()
        dp.send('frame.set_config', group='dirlistctrl', sort_column=col, sort_order=ascending)

    def HighlightPath(self, filename):
        for item in range(self.GetItemCount()):
            text = self.GetItemText(item)
            if os.path.normpath(text) == os.path.normpath(filename):
                self.Select(item)
                self.EnsureVisible(item)
                break

    def GetRootItem(self):
        return -1


class DirTreeList(HTL.HyperTreeList, DirWithColumnsMixin, DirTreeMixin, FindTreeMixin):
    """
    A HTL.HyperTreeList that is used for displaying directory structures.
    Virtually handles paths to help with memory management.
    """


    def __init__(self, parent, **kwargs):

        if 'agwStyle' not in kwargs:
            # default agwStyle
            kwargs['agwStyle'] = (HTL.TR_DEFAULT_STYLE
                                   | HTL.TR_HAS_VARIABLE_ROW_HEIGHT
                                   | HTL.TR_HIDE_ROOT
                                   | HTL.TR_EDIT_LABELS)

        if platform.system() == 'Windows':
            # the default button on windows is too small
            HTL._BTNHEIGHT = 13
            HTL._BTNWIDTH = 13

        HTL.HyperTreeList.__init__(self, parent, **kwargs)
        DirWithColumnsMixin.__init__(self)
        DirTreeMixin.__init__(self)
        FindTreeMixin.__init__(self)

        self.sort_col = (None, True) # col, ascending

        self.SetImageList(self.imagelist)

        self.SetItemData = self.SetItemPyData
        self.GetItemData = self.GetItemPyData
        self.BuildColumns()

        self.Select = self.SelectItem
        # bind events
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.TreeItemExpanding)
        self.Bind(wx.EVT_TREE_ITEM_COLLAPSING, self.TreeItemCollapsing)

        self.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnRightClickItem2)
        self.Bind(wx.EVT_TREE_END_LABEL_EDIT, self.OnRename)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnItemActivated)
        self.Bind(wx.EVT_LIST_COL_RIGHT_CLICK, self.OnColRightClick)
        self.Bind(wx.EVT_LIST_COL_CLICK, self.OnColClick)

    def BuildAccelTable(self):
        accel = DirTreeMixin.BuildAccelTable(self)
        accel2 = FindTreeMixin.BuildAccelTable(self)
        return accel + accel2

    def ShowSortIndicator(self, col, ascending):
        col_prev, _ = self.sort_col
        if col_prev is not None and col_prev != col:
            self.GetHeaderWindow().SetSortIcon(col, wx.HDR_SORT_ICON_NONE)

        flag = wx.HDR_SORT_ICON_UP if ascending else wx.HDR_SORT_ICON_DOWN
        self.sort_col = (col, ascending)
        self.GetHeaderWindow().SetSortIcon(col, flag)

    def OnColClick(self, event):
        col= event.GetColumn()
        if col == -1:
            return # clicked outside any column.
        col_prev, ascending = self.sort_col
        if col_prev == col:
            ascending = not ascending
        elif col_prev is not None and col_prev != col:
            ascending = True

        self.ShowSortIndicator(col, ascending)

        self.SetRootDir(self.rootdir, self.pattern, self.show_hidden)

    def BuildColumns(self):
        if self.GetColumnCount() == 0:
            for idx, col in enumerate(self.columns):
                flag = wx.ALIGN_LEFT
                if col['align'] == 'right':
                    flag = wx.ALIGN_RIGHT
                elif col['align'] == 'center':
                    flag= wx.ALIGN_CENTER
                self.AddColumn(col['name'], flag=flag, width=col['min_width'])

        self.columns_shown = []
        for idx, col in enumerate(self.columns):
            self.SetColumnShown(idx, col['visible'])
            if not col['visible']:
                continue
            self.columns_shown.append(idx)

    def OnRightClickItem2(self, event):
        self.OnRightClickItem(event.GetItem())

    def UpdateItem(self, item, d):
        for col in range(len(self.columns)):
            self.SetItemText(item, self.GetItemColumnText(d, col), col)

    def SortBy(self, data, column, ascending):
        column_name = self.columns[column]['name']
        if column_name == 'Name':
            data.sort(key=lambda x: str(x[column]).lower(), reverse=not ascending)
        else:
            data.sort(key=lambda x: x[column], reverse=not ascending)

        data.sort(key=lambda x: x[-1])

    def LoadPath(self, directory):
        data = DirWithColumnsMixin.LoadPath(self, directory)
        col, ascending = self.sort_col
        if col is not None:
            self.SortBy(data, col, ascending)
        return data

    def LoadDir(self, item, directory):
        DirTreeMixin.LoadDir(self, item, directory)

        # Give the TreeList control sometime to update the best column width
        # not perfect on Windows
        wx.CallAfter(self.AutoSizeColumns)

    def HitTestItem(self, pos):
        item = self.HitTest(self.ScreenToClient(pos))
        return item.IsOk(), item

    def HighlightPath(self, filename):
        root_item = self.GetRootItem()
        item, cookie = self.GetFirstChild(root_item)
        while item.IsOk():
            text = self.GetItemText(item)
            if text == filename:
                self.SelectItem(item)
                self.EnsureVisible(item)
                break
            item, cookie = self.GetNextChild(root_item, cookie)

    def AutoSizeColumns(self, columns=None):
        if columns is None:
            columns = range(self.GetColumnCount())
        for col in columns:
            self.SetColumnWidth(col, self.GetMainWindow().GetBestColumnWidth(col)+10)
            if self.GetColumnWidth(col) < self.columns[col]['min_width']:
                self.SetColumnWidth(col, self.columns[col]['min_width'])

    def OnRename(self, event):
        DirTreeMixin.OnRename(self, event)

    def GetNextItem(self, item):
        if not item.IsOk():
            return item
        if isinstance(self.GetItemData(item), Directory):
            d = self.GetItemData(item)
            self.LoadDir(item, d.directory)

        return super().GetNextItem(item)

    def GetPrevItem(self, item):
        if not item.IsOk():
            return item
        if isinstance(self.GetItemData(item), Directory):
            d = self.GetItemData(item)
            self.LoadDir(item, d.directory)

        return super().GetPrevItem(item)

    def LoadConfig(self):
        super().LoadConfig()

        sort_column = None
        resp = dp.send('frame.get_config', group='dirlistctrl', key='sort_column')
        if resp and resp[0][1] is not None:
            sort_column = resp[0][1]

        sort_order = None
        resp = dp.send('frame.get_config', group='dirlistctrl', key='sort_order')
        if resp and resp[0][1] is not None:
            sort_order = resp[0][1]

        if sort_column is not None and sort_order is not None:
            if 0 <= sort_column < self.GetColumnCount():
                self.ShowSortIndicator(sort_column, sort_order)

    def SaveConfig(self):
        super().SaveConfig()

        dp.send('frame.set_config', group='dirlistctrl', sort_column=self.sort_col[0],
                sort_order=self.sort_col[1])
