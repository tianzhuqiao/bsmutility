"""
    DirTreeCtrl

    @summary: A tree control for use in displaying directories
    @author: Collin Green aka Keeyai
    @url: http://keeyai.com
    @license: public domain -- use it how you will, but a link back would be nice
    @version: 0.9.0
    @note:
        behaves just like a TreeCtrl

        Usage:
            set your default and directory images using addIcon -- see the commented
            last two lines of __init__

            initialze the tree then call SetRootDir(directory) with the root
            directory you want the tree to use

        use SetDeleteOnCollapse(bool) to make the tree delete a node's children
        when the node is collapsed. Will (probably) save memory at the cost of
        a bit o' speed

        use addIcon to use your own icons for the given file extensions


    @todo:
        extract ico from exes found in directory
"""

import os
import platform
import stat
from pathlib import Path
import traceback
import datetime
import fnmatch
import wx
from .findlistctrl import ListCtrlBase


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
    def __init__(self):

        self.rootdir = ""

        # some hack-ish code here to deal with imagelists
        self.iconentries = {}
        self.imagelist = wx.ImageList(16, 16)

        # blank default
        self.iconentries['default'] = -1
        self.iconentries['directory'] = -1
        self.iconentries['directoryopen'] = -1
        scale = 1
        if not wx.Platform == '__WXMSW__':
            # looks like Windows doesn't support high DPI image (wx 4.2.2)
            scale = self.GetDPIScaleFactor()
        bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (int(16*scale), int(16*scale)))
        bmp.SetScaleFactor(scale)
        self.addBitmap(bmp, 'directory')
        bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER_OPEN, wx.ART_OTHER, (int(16*scale), int(16*scale)))
        bmp.SetScaleFactor(scale)
        self.addBitmap(bmp, 'directoryopen')
        bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (int(16*scale), int(16*scale)))
        bmp.SetScaleFactor(scale)
        self.addBitmap(bmp, 'default')

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

        self.rootdir = directory
        self.LoadPath(directory, pattern=pattern, show_hidden=show_hidden)

    def GetPathInfo(self, filepath):
        name = os.path.basename(filepath)
        return [name]

    def LoadPath(self, directory, pattern=None, show_hidden=True):
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
        if pattern:
            files_all = fnmatch.filter(files_all, pattern)
        if not show_hidden:
            folders_all = [f for f in folders_all if not is_hidden(f)]
            files_all = [f for f in files_all if not is_hidden(f)]

        data = []
        folders_all.sort(key=lambda y: y.lower())
        files_all.sort(key=lambda y: y.lower())
        for f in folders_all:
            info = self.GetPathInfo(os.path.join(directory, f))
            data.append(info + [self.iconentries['directory'], 0])

        # add file nodes to tree
        for f in files_all:
            # process the file extension to build image list
            imagekey = self.processFileExtension(os.path.join(
                directory, f))

            info = self.GetPathInfo(os.path.join(directory, f))
            data.append(info + [imagekey, 1])
        return data

    def getFileExtension(self, filename):
        """Helper function for getting a file's extension"""
        # check if directory
        if not os.path.isdir(filename):
            # search for the last period
            index = filename.rfind('.')
            if index > -1:
                return filename[index:]
            return ''
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
                try:
                    # use mimemanager to get filetype and icon
                    # lookup extension
                    filetype = wx.TheMimeTypesManager.GetFileTypeFromExtension(
                        ext)

                    if hasattr(filetype, 'GetIconInfo'):
                        info = filetype.GetIconInfo()

                        if info is not None:
                            icon = info[0]
                            if not icon.IsOk():
                                icon = wx.Icon()
                                icon.LoadFile(info[1], type=wx.BITMAP_TYPE_ICON)
                            if icon.IsOk():
                                bitmap = wx.Bitmap()
                                bitmap.CopyFromIcon(icon)
                                image = bitmap.ConvertToImage()
                                scale = 1
                                if not wx.Platform == '__WXMSW__':
                                    scale = self.GetDPIScaleFactor()
                                image = image.Scale(int(16*scale), int(16*scale), wx.IMAGE_QUALITY_HIGH)
                                bitmap = image.ConvertToBitmap()
                                bitmap.SetScaleFactor(scale)

                                # add to imagelist and store returned key
                                iconkey = self.imagelist.Add(bitmap)
                                self.iconentries[ext] = iconkey
                                # update tree with new imagelist - inefficient
                                self.SetImageList(self.imagelist)

                                # return new key
                                return iconkey
                    return self.iconentries['default']
                except:
                    return self.iconentries['default']

            # already have icon, return key
            else:
                return self.iconentries[ext]

        # if exe, get first icon out of it
        elif ext == '.exe':
            #TODO: get icon out of exe withOUT using weird winpy BS
            pass

        # if ico just use it
        elif ext == '.ico':
            try:
                icon = wx.Icon(filename, wx.BITMAP_TYPE_ICO)
                if icon.IsOk():
                    return self.imagelist.AddIcon(icon)

            except:
                traceback.print_exc()
                return self.iconentries['default']

        # if no key returned already, return default
        return self.iconentries['default']


class DirTreeCtrl(wx.TreeCtrl, DirMixin):
    """A wx.TreeCtrl that is used for displaying directory structures.
    Virtually handles paths to help with memory management.
    """
    def __init__(self, parent, *args, **kwds):
        """Initializes the tree and binds some events we need for
        making this dynamically load its data."""
        wx.TreeCtrl.__init__(self, parent, *args, **kwds)
        DirMixin.__init__(self)

        # bind events
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.TreeItemExpanding)
        self.Bind(wx.EVT_TREE_ITEM_COLLAPSING, self.TreeItemCollapsing)

        # option to delete node items from tree when node is collapsed
        self.DELETEONCOLLAPSE = False

    def SetDeleteOnCollapse(self, selection):
        """Sets the tree option to delete leaf items when the node is
        collapsed. Will slow down the tree slightly but will probably save memory."""
        if isinstance(selection, bool):
            self.DELETEONCOLLAPSE = selection

    def SetRootDir(self, directory, pattern=None, show_hidden=True):

        if not os.path.isdir(directory):
            raise ValueError(f"{directory} is not a valid directory")

        self.rootdir = directory
        # delete existing root, if any
        self.DeleteAllItems()

        # add directory as root
        root = self.AddRoot(directory)
        self.SetItemData(root, Directory(directory))
        self.SetItemImage(root, self.iconentries['directory'],
                          wx.TreeItemIcon_Normal)
        self.SetItemImage(root, self.iconentries['directoryopen'],
                          wx.TreeItemIcon_Expanded)

        self.LoadDir(root, directory, pattern, show_hidden)

    def LoadDir(self, item, directory, pattern=None, show_hidden=True):

        data = self.LoadPath(directory, pattern, show_hidden)

        # process the file extension to build image list
        for d in data:
            # populate the tree
            if d[-1] == 0:
                child = self.AppendItem(item, d[0])
                # directory
                self.SetItemImage(child, self.iconentries['directory'],
                                  wx.TreeItemIcon_Normal)
                self.SetItemImage(child, self.iconentries['directoryopen'],
                                  wx.TreeItemIcon_Expanded)
                self.SetItemHasChildren(child, True)

                # save item path for expanding later
                self.SetItemData(child, Directory(os.path.join(directory, d[0])))
            else:
                # process the file extension to build image list
                self.AppendItem(item, d[0], image=d[-2])

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
        the children from the tree if self.DELETEONCOLLAPSE is
        set - see L{SetDeleteOnCollapse}
        """
        item = event.GetItem()

        # delete the node's children if that tree option is set
        if self.DELETEONCOLLAPSE:
            self.DeleteChildren(item)

        event.Skip()

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

class DirListCtrl(ListCtrlBase, DirMixin):
    """
    A wx.ListCtrl that is used for displaying directory structures.
    Virtually handles paths to help with memory management.
    """

    def __init__(self, parent, *args, **kwds):
        """Initializes the tree and binds some events we need for
        making this dynamically load its data."""
        self.columns = [{'name': 'Name', 'visible': True, 'id': wx.NewIdRef(), 'optional': False, 'width': 400},
                {'name': 'Data modified', 'visible': True, 'id': wx.NewIdRef(), 'optional': True, 'width': 250},
                {'name': 'Data created', 'visible': False, 'id': wx.NewIdRef(), 'optional': True, 'width': 250},
                {'name': 'Type', 'visible': False, 'id': wx.NewIdRef(), 'optional': True, 'width': 200},
                {'name': 'Size', 'visible': True, 'id': wx.NewIdRef(), 'optional': True, 'width': 100}]
        self.columns_shown = list(range(len(self.columns)))

        ListCtrlBase.__init__(self, parent, *args, **kwds)
        DirMixin.__init__(self)

        if platform.system() == 'Windows':
            # Windows
            self.EnableAlternateRowColours(False)
            self.ExtendRulesAndAlternateColour(False)

        self.SetImageList(self.imagelist, wx.IMAGE_LIST_SMALL)
        self.Bind(wx.EVT_LIST_COL_RIGHT_CLICK, self.OnColRightClick)

    def GetShownColumns(self):
        return self.columns_shown

    def SetShowColumns(self, cols):
        for idx, col in enumerate(self.columns):
            if not col['optional']:
                continue
            col['visible'] = idx in cols

        self.BuildColumns()
        self.Fill(self.pattern)

    def OnColRightClick(self, event):
        menu = wx.Menu()
        for col in self.columns:
            item = menu.AppendCheckItem(col['id'], col['name'])
            item.Check(col['visible'])
            item.Enable(col['optional'])
        cmd = self.GetPopupMenuSelectionFromUser(menu)
        if cmd == wx.ID_NONE:
            return
        for col in self.columns:
            if cmd == col['id']:
                col['visible'] = not col['visible']

        self.BuildColumns()
        self.Fill(self.pattern)

    def BuildColumns(self):
        self.DeleteAllColumns()
        self.columns_shown = []
        for idx, col in enumerate(self.columns):
            if not col['visible']:
                continue
            self.columns_shown.append(idx)
            self.AppendColumn(col['name'], width=col['width'])

    def OnGetItemText(self, item, column):
        if column < self.data_start_column:
            return super().OnGetItemText()
        column = self.columns_shown[column]
        column_name = self.columns[column]['name']
        if column_name in ['Data modified', 'Data created']:
            # modified/create time
            mtime = datetime.datetime.fromtimestamp(self.data_shown[item][column])
            mtime = mtime.strftime("%m/%d/%Y %H:%M:%S")
            return mtime
        elif column_name == 'Size':
            # size:
            if self.data_shown[item][-1] == 0:
                # folder
                return ""
            size = self.data_shown[item][column]
            return  pretty_size(size)
        return self.data_shown[item][column]

    def OnGetItemImage(self, item):
        return self.data_shown[item][-2]

    def FindText(self, start, end, text, flags=0):
        direction = 1 if end > start else -1
        for i in range(start, end+direction, direction):
            m = self.data_shown[i][0]
            if self.Search(m, text, flags):
                return i

        # not found
        return -1

    def SortBy(self, column, ascending):
        column = self.columns_shown[column]
        self.data.sort(key=lambda x: x[column], reverse=not ascending)
        self.data.sort(key=lambda x: x[-1])

    def GetItemPath(self, item):
        if isinstance(item, wx.ListItem):
            item = item.GetId()
        rootdir = self.GetRootDir()
        if item == -1:
            return rootdir
        filename = self.GetItemText(item)
        return os.path.join(rootdir, filename)

    def GetPathInfo(self, filepath):
        info = super().GetPathInfo(filepath)
        p = Path(filepath)
        info.append(p.stat().st_mtime)
        info.append(p.stat().st_ctime)
        if p.is_dir():
            ext = "Folder"
        else:
            ext = p.suffix
        info.append(ext)
        info.append(p.stat().st_size)
        return info

    def LoadPath(self, directory, pattern=None, show_hidden=True):
        # check if directory exists and is a directory
        self.data = super().LoadPath(directory, pattern, show_hidden)
        self.Fill(self.pattern)

    def Delete(self, item):
        if isinstance(item, wx.ListItem):
            item = item.GetId()

        self.data.pop(item)
        self.Fill(self.pattern)

    def UpdateData(self, index, name):
        self.data[index][0] = name
        self.Fill(self.pattern)
