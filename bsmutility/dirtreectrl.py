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
import traceback
import fnmatch
import wx


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


class DirTreeCtrl(wx.TreeCtrl):
    """A wx.TreeCtrl that is used for displaying directory structures.
    Virtually handles paths to help with memory management.
    """
    def __init__(self, parent, *args, **kwds):
        """Initializes the tree and binds some events we need for
        making this dynamically load its data."""
        wx.TreeCtrl.__init__(self, parent, *args, **kwds)

        # bind events
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.TreeItemExpanding)
        self.Bind(wx.EVT_TREE_ITEM_COLLAPSING, self.TreeItemCollapsing)

        # option to delete node items from tree when node is collapsed
        self.DELETEONCOLLAPSE = False

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
        self.SetImageList(self.imagelist)
        # # you should replace this with your own code or put the relevant
        # # images in the correct path # set directory image
        # self.addIcon('images/folder.png', wx.BITMAP_TYPE_PNG, 'directory')
        #
        # # set default image
        # self.addIcon('images/page.png', wx.BITMAP_TYPE_PNG, 'default')
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

    def SetDeleteOnCollapse(self, selection):
        """Sets the tree option to delete leaf items when the node is
        collapsed. Will slow down the tree slightly but will probably save memory."""
        if isinstance(selection, bool):
            self.DELETEONCOLLAPSE = selection

    def SetRootDir(self, directory, pattern=None, show_hidden=True):
        """Sets the root directory for the tree. Throws an exception
        if the directory is invalid.
        @param directory: directory to load
        """

        # check if directory exists and is a directory
        if not os.path.isdir(directory):
            raise Exception("%s is not a valid directory" % directory)

        # delete existing root, if any
        self.DeleteAllItems()

        # add directory as root
        root = self.AddRoot(directory)
        self.SetItemData(root, Directory(directory))
        self.SetItemImage(root, self.iconentries['directory'],
                          wx.TreeItemIcon_Normal)
        self.SetItemImage(root, self.iconentries['directoryopen'],
                          wx.TreeItemIcon_Expanded)
        #self.Expand(root)
        # load items
        self._loadDir(root, directory, pattern=pattern, show_hidden=show_hidden)

    def _loadDir(self, item, directory, pattern=None, show_hidden=True):
        """Private function that gets called to load the file list
        for the given directory and append the items to the tree.
        Throws an exception if the directory is invalid.

        @note: does not add items if the node already has children"""

        # check if directory exists and is a directory
        if not os.path.isdir(directory):
            raise Exception("%s is not a valid directory" % directory)

        # check if node already has children
        if self.GetChildrenCount(item) == 0:
            # get files in directory
            files = os.listdir(directory)
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

            folders_all.sort(key=lambda y: y.lower())
            files_all.sort(key=lambda y: y.lower())
            for f in folders_all:
                # process the file extension to build image list
                imagekey = self.processFileExtension(os.path.join(
                    directory, f))

                # add item to
                child = self.AppendItem(item, f)
                self.SetItemImage(child, self.iconentries['directory'],
                                  wx.TreeItemIcon_Normal)
                self.SetItemImage(child, self.iconentries['directoryopen'],
                                  wx.TreeItemIcon_Expanded)
                self.SetItemHasChildren(child, True)

                # save item path for expanding later
                self.SetItemData(child, Directory(os.path.join(directory, f)))

            # add file nodes to tree
            for f in files_all:
                # process the file extension to build image list
                imagekey = self.processFileExtension(os.path.join(
                    directory, f))
                self.AppendItem(item, f, image=imagekey)

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

    def TreeItemExpanding(self, event):
        """Called when a node is about to expand. Loads the node's
        files from the file system."""
        item = event.GetItem()

        # check if item has directory data
        if isinstance(self.GetItemData(item), Directory):
            d = self.GetItemData(item)
            self._loadDir(item, d.directory)
        else:
            # print 'no data found!'
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
