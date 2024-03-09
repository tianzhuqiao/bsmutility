"""define some utility functions"""
import os
import subprocess
import platform
import keyword
import re
import pickle
from pathlib import Path
from collections.abc import MutableMapping
import six
import pandas as pd
import wx
import wx.svg
import wx.py.dispatcher as dp

def MakeBitmap(red, green, blue, alpha=128, size=None, scale_factor=1):
    # Create the bitmap that we will stuff pixel values into using
    w, h = 16, 16
    if size is not None:
        w, h = size[0], size[1]
    w = int(round(w*scale_factor))
    h = int(round(h*scale_factor))
    # the raw bitmap access classes.
    bmp = wx.Bitmap(w, h, 32)
    bmp.SetScaleFactor(scale_factor)

    # Create an object that facilitates access to the bitmap's
    # pixel buffer
    pixelData = wx.AlphaPixelData(bmp)
    if not pixelData:
        raise RuntimeError("Failed to gain raw access to bitmap data.")

    # We have two ways to access each pixel, first we'll use an
    # iterator to set every pixel to the colour and alpha values
    # passed in.
    for pixel in pixelData:
        pixel.Set(red, green, blue, alpha)

    # Next we'll use the pixel accessor to set the border pixels
    # to be fully opaque
    pixels = pixelData.GetPixels()
    for x in six.moves.range(w):
        pixels.MoveTo(pixelData, x, 0)
        pixels.Set(red, green, blue, wx.ALPHA_OPAQUE)
        pixels.MoveTo(pixelData, x, w - 1)
        pixels.Set(red, green, blue, wx.ALPHA_OPAQUE)
    for y in six.moves.range(h):
        pixels.MoveTo(pixelData, 0, y)
        pixels.Set(red, green, blue, wx.ALPHA_OPAQUE)
        pixels.MoveTo(pixelData, h - 1, y)
        pixels.Set(red, green, blue, wx.ALPHA_OPAQUE)

    return bmp


class FastLoadTreeCtrl(wx.TreeCtrl):
    """
    When a treectrl tries to load a large amount of items, it will be slow.
    This class will not load the children item until the parent is expanded (
    e.g., by a click).
    """
    def __init__(self,
                 parent,
                 getchildren=None,
                 style=wx.TR_DEFAULT_STYLE,
                 sort=True):
        wx.TreeCtrl.__init__(self, parent, style=style)
        self._get_children = getchildren
        assert self._get_children
        self._sort_children = sort
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.OnTreeItemExpanding)

    def OnTreeItemExpanding(self, event):
        """expand the item with children"""
        item = event.GetItem()
        if not item.IsOk():
            return
        self.FillChildren(item)

    def FillChildren(self, item):
        """fill the node with children"""
        if not ((self.GetWindowStyle() & wx.TR_HIDE_ROOT)
                and item == self.GetRootItem()):
            child, _ = self.GetFirstChild(item)
            if not child.IsOk():
                return False
            if self.GetItemText(child) != "...":
                return False

        self.RefreshChildren(item)

    def RefreshChildren(self, item):
        # delete the '...'
        self.DeleteChildren(item)
        children = self._get_children(item)
        for obj in children:
            # fill all the children
            child = self.AppendItem(item, obj['label'], obj['img'],
                                    obj['imgsel'], obj['data'])
            # add the place holder for children
            if obj['is_folder']:
                self.AppendItem(child, '...', -1, -1, None)
            clr = obj.get('color', None)
            if clr:
                self.SetItemTextColour(child, wx.Colour(100, 174, 100))
        if self._sort_children:
            self.SortChildren(item)
        return True

def svg_to_bitmap(svg, size=None, win=None):
    if size is None:
        if wx.Platform == '__WXMSW__':
            size = (24, 24)
        else:
            size = (16, 16)
    bmp = wx.svg.SVGimage.CreateFromBytes(str.encode(svg))
    bmp = bmp.ConvertToScaledBitmap(size, win)
    if win:
        bmp.SetScaleFactor(win.GetContentScaleFactor())
    return bmp


def open_file_with_default_app(filepath):
    if platform.system() == 'Darwin':       # macOS
        subprocess.call(('open', filepath))
    elif platform.system() == 'Windows':    # Windows
        os.startfile(filepath)
    else:                                   # linux variants
        subprocess.call(('xdg-open', filepath))

def get_file_finder_name():

    if platform.system() == 'Darwin':       # macOS
        manager = 'Finder'
    elif platform.system() == 'Windows':    # Windows
        manager = 'Explorer'
    else:                         # linux variants
        manager = 'File Explorer'
    return manager

def show_file_in_finder(filepath):
    if platform.system() == 'Darwin':       # macOS
        subprocess.call(('open', '-R', filepath))
    elif platform.system() == 'Windows':    # Windows
        subprocess.Popen( f'explorer /select,"{filepath}"' )
    else:                                   # linux variants
        subprocess.call(('nautilus', '-s', filepath))

def build_menu_from_list(items, menu=None):
    # for each item in items
    # {'type': ITEM_SEPARATOR}
    # {'type': ITEM_NORMAL, 'id': , 'label': , 'enable':}
    # {'type': ITEM_CHECK, 'id': , 'label': , 'enable':, 'check'}
    # {'type': ITEM_RADIO, 'id': , 'label': , 'enable':, 'check'}
    # {'type': ITEM_DROPDOWN, 'label':, 'items': []]
    if menu is None:
        menu = wx.Menu()
    for m in items:
        mtype = m.get('type', wx.ITEM_NORMAL)
        if mtype == wx.ITEM_SEPARATOR:
            item = menu.AppendSeparator()
        elif mtype == wx.ITEM_DROPDOWN:
            child = build_menu_from_list(m['items'])
            menu.AppendSubMenu(child, m['label'])
        elif mtype == wx.ITEM_NORMAL:
            item = menu.Append(m['id'], m['label'])
            item.Enable(m.get('enable', True))
        elif mtype == wx.ITEM_CHECK:
            item = menu.AppendCheckItem(m['id'], m['label'])
            item.Check(m.get('check', True))
            item.Enable(m.get('enable', True))
        elif mtype == wx.ITEM_RADIO:
            item = menu.AppendRadioItem(m['id'], m['label'])
            item.Check(m.get('check', True))
            item.Enable(m.get('enable', True))
    return menu

def get_temp_file(filename):
    path = Path(os.path.join(wx.StandardPaths.Get().GetTempDir(), filename))
    return path.as_posix()

def send_data_to_shell(name, data):
    if not name.isidentifier():
        return False

    # add the data directly to shell's locals
    dp.send('shell.update_locals', **{name: data})
    dp.send('shell.run',
            command=f'{name}',
            prompt=True,
            verbose=True,
            history=False)

def get_variable_name(text, default='_data'):
    def _get(text):
        # array[0] -> array0
        # a->b -> a_b
        # a.b -> a_b
        # [1] -> None
        name = text.replace('[', '').replace(']', '')
        name = name.replace('(', '').replace(')', '')
        name = name.replace('{', '').replace('}', '')
        name = name.replace('.', '_').replace('->', '_').replace('~', '_')
        if keyword.iskeyword(name):
            name = f'{name}_'
        if not name.isidentifier():
            return None
        return name
    if isinstance(text, str):
        text = [text]
    name = ""
    for t in reversed(text):
        name = t + name
        var = _get(name)
        if var:
            return var
    return default

def get_tree_item_path(name, sep='.', has_array=True):
    # get the tree path from name
    # 'a.b.c[5]' -> ['a', 'b', 'c', '[5]']
    path = []
    for p in name.split(sep):
        if has_array:
            x = re.search(r'(\[\d+\])+', p)
            if x and x.group() != p:
                # array[0] -> ['array', '[0]']
                signal = [p[:x.start(0)], x.group(0), p[x.end(0):]]
                path += [s for s in signal if s]
                continue
        path.append(p)
    return path

def get_tree_item_name(path, sep='.', has_array=True):
    # get the name from tree path
    # ['a', 'b', 'c', '[5]'] -> 'a.b.c[5]'
    if not path:
        return ""
    name = path[0]
    for p in path[1:]:
        if has_array:
            x = re.search(r'(\[\d+\])+', p)
            if x and x.group() == p:
                name += p
                continue
        name += sep + p
    return name

def build_tree(data, sep='.', dataframe=False):
    tree = dict(data)
    for k in list(tree.keys()):
        signal = get_tree_item_path(k, sep=sep)
        d = tree
        if len(signal) > 1:
            for i in range(len(signal)-1):
                if not signal[i] in d:
                    d[signal[i]] = {}
                d = d[signal[i]]
            d[signal[-1]] = tree.pop(k)
        if isinstance(d[signal[-1]], MutableMapping):
            d[signal[-1]] = build_tree(d[signal[-1]])
        if dataframe and isinstance(d[signal[-1]], pd.DataFrame):
            df_tree = {c: d[signal[-1]][c].to_numpy() for c in d[signal[-1]]}
            d[signal[-1]] = build_tree(df_tree)
    return tree

def flatten_tree(dictionary, parent_key='', sep='.'):
    items = []
    for key, value in dictionary.items():
        separator = sep
        if re.match(r'(\[\d+\])+', key):
            separator = ''
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(flatten_tree(value, new_key, sep=sep).items())
        else:
            items.append((new_key, value))
    return dict(items)

class _dict(dict):
    """dict like object that exposes keys as attributes"""
    def __getattr__(self, key):
        ret = self.get(key, None)
        if ret is None or key.startswith("__"):
            raise AttributeError()
        return ret
    def __setattr__(self, key, value):
        self[key] = value
    def __getstate__(self):
        return self
    def __setstate__(self, d):
        self.update(d)
    def update(self, d=None, **kwargs):
        """update and return self -- the missing dict feature in python"""
        if d:
            super().update(d)
        if kwargs:
            super().update(kwargs)
        return self

    def copy(self):
        return _dict(dict(self).copy())
