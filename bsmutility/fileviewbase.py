import sys
import os
import traceback
import json
from collections.abc import MutableMapping
import wx
import wx.py.dispatcher as dp
from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
import matplotlib.pyplot as plt
import aui2 as aui
from propgrid import PropText, PropSeparator, PropCheckBox
from .bsmxpm import open_svg, refresh_svg, more_svg
from .utility import FastLoadTreeCtrl, _dict, send_data_to_shell, get_variable_name
from .utility import svg_to_bitmap, build_tree, flatten_tree
from .utility import get_file_finder_name, show_file_in_finder, \
                     get_tree_item_path, get_tree_item_name
from .autocomplete import AutocompleteTextCtrl
from .bsminterface import Interface
from .signalselsettingdlg import SignalSelSettingDlg, PropSettingDlg, ConvertSettingDlg
from .quaternion import Quaternion
from .configfile import ConfigFile

class FindListCtrl(wx.ListCtrl):
    ID_FIND_REPLACE = wx.NewIdRef()
    ID_FIND_NEXT = wx.NewIdRef()
    ID_FIND_PREV = wx.NewIdRef()
    ID_COPY_NO_INDEX = wx.NewIdRef()
    def __init__(self, *args, **kwargs):
        wx.ListCtrl.__init__(self, *args, **kwargs)
        self.SetupFind()

        self.index_column = 0
        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnRightClick)
        self.Bind(wx.EVT_TOOL, self.OnBtnCopy, id=wx.ID_COPY)
        self.Bind(wx.EVT_TOOL, self.OnBtnCopy, id=self.ID_COPY_NO_INDEX)

        accel = [
            (wx.ACCEL_CTRL, ord('F'), self.ID_FIND_REPLACE),
            (wx.ACCEL_SHIFT, wx.WXK_F3, self.ID_FIND_PREV),
            (wx.ACCEL_CTRL, ord('H'), self.ID_FIND_REPLACE),
            (wx.ACCEL_RAW_CTRL, ord('H'), self.ID_FIND_REPLACE),
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('C'), self.ID_COPY_NO_INDEX),
        ]
        self.accel = wx.AcceleratorTable(accel)
        self.SetAcceleratorTable(self.accel)

    def OnRightClick(self, event):

        if self.GetSelectedItemCount() <= 0:
            return

        menu = wx.Menu()
        menu.Append(wx.ID_COPY, "&Copy \tCtrl+C")
        if 0 <= self.index_column < self.GetColumnCount():
            menu.Append(self.ID_COPY_NO_INDEX, "C&opy without index \tCtrl+Shift+C")
        self.PopupMenu(menu)

    def OnBtnCopy(self, event):
        cmd = event.GetId()
        columns = list(range(self.GetColumnCount()))
        if cmd == self.ID_COPY_NO_INDEX:
            columns.remove(self.index_column)
        if wx.TheClipboard.Open():
            item = self.GetFirstSelected()
            text = []
            while item != -1:
                tmp = []
                for c in columns:
                    tmp.append(self.GetItemText(item, c))
                text.append(" ".join(tmp))
                item = self.GetNextSelected(item)
            wx.TheClipboard.SetData(wx.TextDataObject("\n".join(text)))
            wx.TheClipboard.Close()

    def SetupFind(self):
        # find & replace dialog
        self.findDialog = None
        self.findStr = ""
        self.replaceStr = ""
        self.findFlags = 1
        self.stcFindFlags = 0
        self.findDialogStyle = 0 #wx.FR_REPLACEDIALOG
        self.wrapped = 0

        self.Bind(wx.EVT_TOOL, self.OnShowFindReplace, id=self.ID_FIND_REPLACE)
        self.Bind(wx.EVT_TOOL, self.OnFindNext, id=self.ID_FIND_NEXT)
        self.Bind(wx.EVT_TOOL, self.OnFindPrev, id=self.ID_FIND_PREV)

    def OnShowFindReplace(self, event):
        """Find and Replace dialog and action."""
        # find string
        findStr = ""#self.GetSelectedText()
        if findStr and self.findDialog:
            self.findDialog.Destroy()
            self.findDialog = None
        # dialog already open, if yes give focus
        if self.findDialog:
            self.findDialog.Show(1)
            self.findDialog.Raise()
            return
        if not findStr:
            findStr = self.findStr
        # find data
        data = wx.FindReplaceData(self.findFlags)
        data.SetFindString(findStr)
        data.SetReplaceString(self.replaceStr)
        # dialog
        title = 'Find'
        if self.findDialogStyle & wx.FR_REPLACEDIALOG:
            title = 'Find & Replace'

        self.findDialog = wx.FindReplaceDialog(
            self, data, title, self.findDialogStyle)
        # bind the event to the dialog, see the example in wxPython demo
        self.findDialog.Bind(wx.EVT_FIND, self.OnFind)
        self.findDialog.Bind(wx.EVT_FIND_NEXT, self.OnFind)
        self.findDialog.Bind(wx.EVT_FIND_REPLACE, self.OnReplace)
        self.findDialog.Bind(wx.EVT_FIND_REPLACE_ALL, self.OnReplaceAll)
        self.findDialog.Bind(wx.EVT_FIND_CLOSE, self.OnFindClose)
        self.findDialog.Show(1)
        self.findDialog.data = data  # save a reference to it...

    def message(self, text):
        """show the message on statusbar"""
        dp.send('frame.show_status_text', text=text)

    def FindText(self, start, end, text, flags=0):
        # not found
        return -1

    def doFind(self, strFind, forward=True):
        """search the string"""
        current = self.GetFirstSelected()
        if current == -1:
            current = 0
        position = -1
        if forward:
            if current < self.GetItemCount() - 1:
                position = self.FindText(current+1, self.GetItemCount()-1,
                                         strFind, self.findFlags)
            if position == -1:
                # wrap around
                self.wrapped += 1
                position = self.FindText(0, current, strFind, self.findFlags)
        else:
            if current > 0:
                position = self.FindText(current-1, 0, strFind, self.findFlags)
            if position == -1:
                # wrap around
                self.wrapped += 1
                position = self.FindText(self.GetItemCount()-1, current,
                                         strFind, self.findFlags)

        # not found the target, do not change the current position
        if position == -1:
            self.message("'%s' not found!" % strFind)
            position = current
            strFind = """"""
        #self.GotoPos(position)
        #self.SetSelection(position, position + len(strFind))
        while True:
            sel = self.GetFirstSelected()
            if sel == -1:
                break
            self.Select(sel, False)
        self.EnsureVisible(position)
        self.Select(position)
        return position

    def OnFind(self, event):
        """search the string"""
        self.findStr = event.GetFindString()
        self.findFlags = event.GetFlags()
        flags = 0
        #if wx.FR_WHOLEWORD & self.findFlags:
        #    flags |= stc.STC_FIND_WHOLEWORD
        #if wx.FR_MATCHCASE & self.findFlags:
        #    flags |= stc.STC_FIND_MATCHCASE
        #self.stcFindFlags = flags
        return self.doFind(self.findStr, wx.FR_DOWN & self.findFlags)

    def OnFindClose(self, event):
        """close find & replace dialog"""
        event.GetDialog().Destroy()

    def OnReplace(self, event):
        """replace"""
        # Next line avoid infinite loop
        findStr = event.GetFindString()
        self.replaceStr = event.GetReplaceString()

        source = self
        selection = source.GetSelectedText()
        if not event.GetFlags() & wx.FR_MATCHCASE:
            findStr = findStr.lower()
            selection = selection.lower()

        if selection == findStr:
            position = source.GetSelectionStart()
            source.ReplaceSelection(self.replaceStr)
            source.SetSelection(position, position + len(self.replaceStr))
        # jump to next instance
        position = self.OnFind(event)
        return position

    def OnReplaceAll(self, event):
        """replace all the instances"""
        source = self
        count = 0
        self.wrapped = 0
        position = start = source.GetCurrentPos()
        while position > -1 and (not self.wrapped or position < start):
            position = self.OnReplace(event)
            if position != -1:
                count += 1
            if self.wrapped >= 2:
                break
        self.GotoPos(start)
        if not count:
            self.message("'%s' not found!" % event.GetFindString())

    def OnFindNext(self, event):
        """go the previous instance of search string"""
        findStr = self.GetSelectedText()
        if findStr:
            self.findStr = findStr
        if self.findStr:
            self.doFind(self.findStr)

    def OnFindPrev(self, event):
        """go the previous instance of search string"""
        findStr = self.GetSelectedText()
        if findStr:
            self.findStr = findStr
        if self.findStr:
            self.doFind(self.findStr, False)

    def Search(self, src, pattern, flags):
        if not (wx.FR_MATCHCASE & flags):
            pattern = pattern.lower()
            src = src.lower()

        if wx.FR_WHOLEWORD & flags:
            return pattern in src.split()

        return pattern in src

class ListCtrlBase(FindListCtrl, ListCtrlAutoWidthMixin):
    def __init__(self, parent):
        FindListCtrl.__init__(self, parent, style=wx.LC_REPORT|wx.LC_HRULES|wx.LC_VRULES|wx.LC_VIRTUAL)
        ListCtrlAutoWidthMixin.__init__(self)
        self.EnableAlternateRowColours()
        self.ExtendRulesAndAlternateColour()

        self.data_start_column = 0
        self.BuildColumns()

        self.data = None
        self.pattern = None
        self.data_shown = []

    def BuildColumns(self):
        self.InsertColumn(0, "#", width=60)
        self.data_start_column = 1

    def OnGetItemText(self, item, column):
        if self.data_start_column > 0 and column == 0:
            # index column
            return f"{item+1}"
        return ""

    def Load(self, data):
        self.data = data
        self.Fill(self.pattern)

    def ApplyPattern(self):
        self.data_shown = self.data

    def Fill(self, pattern):
        self.pattern = pattern
        if isinstance(self.pattern, str):
            self.pattern = self.pattern.lower()
            self.pattern.strip()

        if self.data is None:
            self.SetItemCount(0)
            self.Refresh()
            return

        self.ApplyPattern()
        self.SetItemCount(len(self.data_shown))
        self.Refresh()

class TreeCtrlBase(FastLoadTreeCtrl):
    """the tree control to show the hierarchy of the objects (dict)"""

    ID_EXPORT = wx.NewIdRef()
    ID_PLOT = wx.NewIdRef()
    ID_CONVERT = wx.NewIdRef()
    ID_CONVERT_CUSTOM = wx.NewIdRef()
    ID_CONVERT_MANAGE = wx.NewIdRef()
    ID_DELETE = wx.NewIdRef()
    IDS_CONVERT = {}

    def __init__(self, parent, style=wx.TR_DEFAULT_STYLE):
        style = style | wx.TR_HAS_VARIABLE_ROW_HEIGHT | wx.TR_HIDE_ROOT |\
                wx.TR_MULTIPLE | wx.TR_LINES_AT_ROOT
        super().__init__(parent, self.get_children, style=style)

        self.data = _dict()
        self.pattern = None
        self.expanded = {}
        self.exclude_keys = []
        self.common_convert = [{'label': 'Quaternion to Yaw/Pitch/Roll',
                                    'inputs': ['#w', '#x', '#y', '#z'],
                                    'outputs': '~yaw, ~pitch, ~roll',
                                    'equation': 'Quaternion(#w, #x, #y, #z).to_angle()',
                                    'force_select_signal': True},
                                {'label': 'Radian to degree',
                                    'inputs': ['#1'],
                                    'outputs': '#_deg',
                                    'equation': 'np.rad2deg(#1)',
                                    'force_select_signal': False},
                                {'label': 'Degree to radian',
                                    'inputs': ['#1'],
                                    'outputs': '#_rad',
                                    'equation': 'np.deg2rad(#1)',
                                    'force_select_signal': False}]
        self.customized_convert = []
        self._converted_item = {}
        self._convert_labels = {'label': 'Label',
                                'inputs': 'Input(s), separated by ","',
                                'equation': 'Equation',
                                'outputs': 'Output(s), separated by ","',
                                'force_select_signal': 'Always show the signal selecting dialog'}
        self.config_file = None
        self.filename = None

        self.graph_drop = False

        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnTreeItemActivated)
        self.Bind(wx.EVT_TREE_ITEM_MENU, self.OnTreeItemMenu)
        self.Bind(wx.EVT_TREE_BEGIN_DRAG, self.OnTreeBeginDrag)

        dp.connect(receiver=self.OnGraphDrop, signal='graph.drop')

    def GetConfigGroup(self):
        return  self.__class__.__name__

    def SetConfig(self, **kwargs):
        group = self.GetConfigGroup()
        if not group:
            return
        dp.send('frame.set_config', group=group, **kwargs)

    def LoadConfig(self, key):
        group = self.GetConfigGroup()
        if not group:
            return
        resp = dp.send('frame.get_config', group=group, key=key)
        if resp and resp[0][1] is not None:
            return resp[0][1]
        return None

    def GetItemExportData(self, item):
        output = self.GetItemData(item)
        name = self.GetItemText(item)
        output_name = get_variable_name(name)
        return output_name, output

    def OnProcessCommand(self, cmd, item):
        # process the command from OnTreeItemMenu
        if cmd in [self.ID_EXPORT]:
            output_name, output = self.GetItemExportData(item)
            if output is not None:
                send_data_to_shell(output_name, output)
        elif cmd == self.ID_DELETE:
            name = self.GetItemText(item)
            msg = f"Do you want to delete '{name}'?"
            parent = self.GetTopLevelParent()
            dlg = wx.MessageDialog(self, msg, parent.GetLabel(), wx.YES_NO)
            if dlg.ShowModal() != wx.ID_YES:
                return
            parent = self.GetItemParent(item)
            if parent.IsOk():
                if parent == self.GetRootItem():
                    d_parent = self.data
                else:
                    d_parent = self.GetItemData(parent)
                if name in d_parent:
                    if isinstance(d_parent, pd.DataFrame):
                        d_parent.drop(columns=[name], inplace=True)
                    elif isinstance(d_parent, MutableMapping):
                        d_parent.pop(name, None)
                    # delete it from the converted item
                    fullname = self.GetItemName(item)
                    if fullname in self._converted_item:
                        self._converted_item.pop(fullname, None)
                    if self.config_file:
                        self.config_file.SetConfig('conversion',
                                                   converted_item=self._converted_item)

                self.RefreshChildren(parent)
        elif cmd == self.ID_PLOT:
            self.PlotItem(item)
        elif cmd == self.ID_CONVERT:
            self.ConvertItems(item, self.GetSelections())
        elif cmd == self.ID_CONVERT_CUSTOM:
            self.AddCustomizedConvert()
        elif cmd == self.ID_CONVERT_MANAGE:
            self.ManageCustomizedConvert()
        elif cmd in self.IDS_CONVERT.values():
            # find the label of the custom conversion in dict
            label = list(self.IDS_CONVERT.keys())[list(self.IDS_CONVERT.values()).index(cmd)]
            converts = self.common_convert + self.GetCustomizedConvert()
            for c in converts:
                if c['label'] == label:
                    self.ConvertItems(item, self.GetSelections(), **c)
                    break

    def GetItemDragData(self, item):
        # get the drag data for leaf node
        if self.ItemHasChildren(item):
            return None

        x, y = self.GetItemPlotData(item)
        if y is None:
            return None
        df = pd.DataFrame()
        if x is not None:
            df['x'] = x
        name = self.GetItemText(item)
        df[name] = y
        return df

    def GetPlotXLabel(self):
        return ""

    def OnGraphDrop(self, axes, allowed):
        self.graph_drop = allowed

    def OnTreeBeginDrag(self, event):
        if not self.data:
            return

        ids = self.GetSelections()
        objs = []
        for item in ids:
            if item == self.GetRootItem() or self.ItemHasChildren(item):
                continue
            if not item.IsOk():
                break
            path = self.GetItemPath(item)
            objs.append('/'.join(path))

        # need to explicitly allow drag
        # start drag operation
        self.graph_drop = False
        data = wx.TextDataObject(json.dumps(objs))
        source = wx.DropSource(self)
        source.SetData(data)
        rtn = source.DoDragDrop(True)
        if rtn == wx.DragError:
            wx.LogError("An error occurred during drag and drop operation")
        else:
            if self.graph_drop:
                for item in ids:
                    if item == self.GetRootItem() or self.ItemHasChildren(item):
                        continue
                    if not item.IsOk():
                        break
                    self.PlotItem(item)

    def GetItemMenu(self, item):
        if not item.IsOk():
            return None
        menu = wx.Menu()
        menu.Append(self.ID_EXPORT, "Export to shell")
        menu.AppendSeparator()
        menu.Append(self.ID_PLOT, "Plot")
        menu.AppendSeparator()
        menu.Append(self.ID_DELETE, "Delete")
        menu.AppendSeparator()
        menu.Append(self.ID_CONVERT, "Convert to ...")
        for c in self.common_convert:
            if c['label'] not in self.IDS_CONVERT:
                self.IDS_CONVERT[c['label']] = wx.NewIdRef()
            menu.Append(self.IDS_CONVERT[c['label']], c['label'])

        menu_customize = wx.Menu()
        menu_customize.Append(self.ID_CONVERT_CUSTOM, "Add")
        menu_customize.Append(self.ID_CONVERT_MANAGE, "Manage")
        menu_customize.AppendSeparator()
        for c in self.GetCustomizedConvert():
            if c['label'] not in self.IDS_CONVERT:
                self.IDS_CONVERT[c['label']] = wx.NewIdRef()
            menu_customize.Append(self.IDS_CONVERT[c['label']], c['label'])
        menu.AppendSubMenu(menu_customize, "Customize ...")
        return menu

    def OnTreeItemMenu(self, event):
        item = event.GetItem()
        if not item.IsOk():
            return
        #self.UnselectAll()
        menu = self.GetItemMenu(item)
        if menu is None:
            return
        cmd = self.GetPopupMenuSelectionFromUser(menu)
        if cmd == wx.ID_NONE:
            return
        self.OnProcessCommand(cmd, item)

    def GetConvertItemProp(self, item, inputs, outputs):
        # the configuration props used to convert an item
        eqn_label = self._convert_labels.get('equation', 'Equation')
        out_label = self._convert_labels.get('outputs', 'Output(s)')
        props = [PropText().Label(eqn_label).Name('equation').Value('#1'),
                PropText().Label(out_label).Name('outputs').Value(f'~{outputs}')]
        return props

    def ConvertItems(self, item, items, equation=None, config=None,
                     force_select_signal=False, **kwargs):
        settings = kwargs
        settings['equation'] = equation
        outputs = kwargs.get('outputs', '~#')
        inputs = kwargs.get('inputs', None)
        N_IN = len(inputs) if inputs is not None else len(items)
        if inputs is None:
            inputs = [f'#{i+1}' for i in range(N_IN)]
        for i in range(min(N_IN, len(items))):
            if items[i] is not None:
                settings[f'{inputs[i]}'] = self.GetItemName(items[i])

        # the parent to have the converted item
        if item is not None:
            parent = self.GetItemParent(item)
        else:
            parent = self.GetRootItem()

        if equation is None or force_select_signal:
            # settings is none, get it from user
            start = ''
            if parent != self.GetRootItem():
                # limit the signal to be children of parent
                start = self.GetItemName(parent)
            values = {f'{inputs[i]}': settings.get(f'{inputs[i]}', '') for i in range(N_IN)}
            values['equation'] = equation
            values['outputs'] = outputs
            additional = self.GetConvertItemProp(item, inputs, outputs.split(','))
            df_in, settings = self.SelectSignal(items=inputs,
                                            values=values,
                                            config=config,
                                            additional=additional,
                                            start=start)
            if settings is None or df_in is None:
                return None, settings
            settings['inputs'] = inputs
            equation = settings.get('equation', None)
            outputs = settings.get('outputs', outputs)
        if not equation:
            return None, settings
        if item is not None:
            text = self.GetItemText(item)
            outputs = outputs or f'~{text}'
            outputs = outputs.replace('#', text)

        d = self.doConvertFromSetting(settings)

        if d is None:
            return None, settings

        # add the converted data to parent DataFrame (same level as item)
        dataset = self.GetItemData(parent)
        outputs = [n.strip() for n in outputs.split(',')]
        if len(outputs) == 1:
            dataset[outputs[0]] = d
        else:
            for i, n in enumerate(outputs):
                dataset[n] = d[i]
        self.RefreshChildren(parent)
        path = self.GetItemPath(parent)
        new_item = []
        for n in outputs:
            tmp = self.FindItemFromPath(path+[n])
            if tmp is not None:
                new_item.append(tmp)
        if len(new_item) > 0 and new_item[0].IsOk():
            self.UnselectAll()
            self.EnsureVisible(new_item[0])
            self.SelectItem(new_item[0])
            self.SetFocusedItem(new_item[0])

        # save the converted item
        for idx in range(0, len(new_item)):
            name = self.GetItemName(new_item[idx])
            self._converted_item[name] = [(len(new_item), idx), settings]
        if self.config_file:
            self.config_file.SetConfig('conversion', converted_item=self._converted_item)

        return new_item, settings

    def ConvertItem(self, item, equation=None, name=None, **kwargs):
        return self.ConvertItems(item, [item], equation=equation, name=name,
                force_select_signal=False, **kwargs)

    def AddConvert(self, p, idx, settings):
        d = self.doConvertFromSetting(settings)
        if d is None:
            return False
        if idx[0] > 1:
            d = d[idx[1]]
        self.SetData(p, d)
        self._converted_item[p] = [idx, settings]
        return True

    def doConvertFromSetting(self, settings):
        inputs = settings.get('inputs', ['x'])
        equation = settings.get('equation', None)
        if inputs is None or equation is None:
            return None
        N_IN = len(inputs)
        paths = []
        for i in range(N_IN):
            signal = settings.get(inputs[i], None)
            if N_IN == 1 and not signal:
                signal = settings.get('#', None)
            if signal is None:
                return None
            paths.append(get_tree_item_path(f'{signal}'))
            # replace input name (e.g., #w) with input index (e.g., #1)
            equation = equation.replace(f'#{inputs[i].lstrip("#")}', f'#{i+1}')
        return self.doConvert(paths, equation)

    def doConvert(self, paths, equation):
        # calculate equation(paths)
        # paths are path of input items
        # and equation may look like foo(#1, #2, #3, ...), e.g., where #1 will
        # be replaced with data from paths[0], etc.

        data = []
        for path in paths:
            d = self.GetItemDataFromPath(path)
            if d is None:
                print(f'Invalid inputs {get_tree_item_name(path)}')
                return None
            data.append(d)

        for i in range(len(paths)):
            equation = equation.replace(f'#{i+1}', f'data[{i}]')

        # or '#' for first input
        equation = equation.replace('#', 'data[0]')

        try:
            # get the locals from shell, to reuse the functions/modules
            resp = dp.send('shell.get_locals')
            if resp:
                local = resp[0][1]
                local.update(locals())
            else:
                local = locals()
            d = eval(equation, globals(), local)
            return d
        except:
            traceback.print_exc(file=sys.stdout)

        return None

    def GetCustomizedConvertProp(self):
        # the configuration props used to convert an item
        label = 'my conversion'
        labels = [c['label'] for c in self.common_convert + self.GetCustomizedConvert()]
        i = 1
        while f'{label} {i}' in labels:
            i += 1
        label = f'{label} {i}'
        in_size =  max(1, len(self.GetSelections()))
        inputs = ', '.join([f'#{i+1}' for i in range(in_size)])
        props = [PropText().Name('label').Value(label),
                 PropText().Name('inputs').Value(inputs),
                 PropText().Name('equation').Value('#1'),
                 PropCheckBox().Name('force_select_signal').Value(in_size>1),
                 PropText().Name('outputs').Value('~#')]
        for p in props:
            name = p.GetName()
            label = self._convert_labels.get(name, name.capitalize())
            p.Label(label)
        return props

    def AddCustomizedConvert(self):
        settings = None
        # settings is none, get it from user
        props = self.GetCustomizedConvertProp()
        dlg = PropSettingDlg(self, props=props, config='')
        dlg.propgrid.GetArtProvider().SetTitleWidth(200)
        if dlg.ShowModal() == wx.ID_OK:
            settings = dlg.GetSettings()
            settings['inputs'] = [x.strip() for x in settings.get('inputs', '#1').split(',')]
            self.customized_convert.append(settings)
            self.SetConfig(convert=self.customized_convert)
        return settings

    def ManageCustomizedConvert(self):
        converts = self.GetCustomizedConvert()
        dlg = ConvertSettingDlg(self, converts, labels=self._convert_labels)
        if dlg.ShowModal() == wx.ID_OK:
            settings = dlg.GetSettings()
            for s in settings:
                s['inputs'] = [x.strip() for x in s.get('inputs', '#1').split(',')]
            self.customized_convert = settings
            self.SetConfig(convert=self.customized_convert)

    def GetCustomizedConvert(self):
        self.customized_convert = self.LoadConfig(key='convert') or []
        return self.customized_convert

    def GetItemPlotData(self, item):
        # get plot data for leaf node
        if self.ItemHasChildren(item):
            return None, None

        y = self.GetItemData(item)
        x = np.arange(0, len(y))
        return x, y

    def PlotItem(self, item, confirm=True):
        if self.ItemHasChildren(item):
            if confirm:
                text = self.GetItemText(item)
                msg = f"Do you want to plot all signals under '{text}'?"
                parent = self.GetTopLevelParent()
                dlg = wx.MessageDialog(self, msg, parent.GetLabel(), wx.YES_NO)
                if dlg.ShowModal() != wx.ID_YES:
                    return None

            child, cookie = self.GetFirstChild(item)
            while child.IsOk():
                self.PlotItem(child, confirm=False)
                child, cookie = self.GetNextChild(item, cookie)
        else:
            path = self.GetItemPath(item)
            x, y = self.GetItemPlotData(item)
            if x is not None and y is not None:
                return self.plot(x, y, "/".join(path))
        return None

    def OnTreeItemActivated(self, event):
        item = event.GetItem()
        if not item.IsOk():
            return
        self.PlotItem(item)

    def plot(self, x, y, label, step=False):
        if x is None or y is None or not is_numeric_dtype(y):
            print(f"{label} is not numeric, ignore plotting!")
            return None

        # plot
        label = label.lstrip('_')
        fig = plt.gcf()
        plt.show()
        ax = plt.gca()
        ls, ms = None, None
        if ax.lines:
            # match the line/marker style of the existing line
            line = ax.lines[0]
            ls, ms = line.get_linestyle(), line.get_marker()
        if step:
            line = ax.step(x, y, label=label, linestyle=ls, marker=ms)
        else:
            line = ax.plot(x, y, label=label, linestyle=ls, marker=ms)

        ax.legend()
        if ls is None:
            # 1st plot in axes
            ax.grid(True)
            xlabel = self.GetPlotXLabel()
            if xlabel:
                ax.set_xlabel(xlabel)
            if step:
                # hide the y-axis tick label
                ax.get_yaxis().set_ticklabels([])
        return line[0]

    def GetItemPath(self, item):
        path = []
        while item.IsOk() and item != self.GetRootItem():
            path.insert(0, self.GetItemText(item))
            item = self.GetItemParent(item)
        return path

    def GetItemName(self, item):
        return get_tree_item_name(self.GetItemPath(item))

    def GetItemData(self, item):
        if item == self.GetRootItem():
            return self.data

        path = self.GetItemPath(item)
        return self.GetItemDataFromPath(path)

    def GetItemDataFromPath(self, path):
        # path is an array, e.g., path = get_tree_item_path(name)
        d = self.data
        for i, p in enumerate(path):
            if p not in d:
                if isinstance(d, pd.DataFrame):
                    # the name in node DataFrame is not parsed, so try the
                    # combined name, e.g., if the column name is a[5],
                    # get_tree_item_path will return ['a', '[5]']
                    name = get_tree_item_name(path[i:])
                    if name in d:
                        return d[name]
                return None
            d = d[p]
        return d

    def SetData(self, path, data):
        if isinstance(path, str):
            path = get_tree_item_path(path)

        d = self.data
        for i, p in enumerate(path[:-1]):
            if p not in d:
                if isinstance(d, pd.DataFrame):
                    # the name in node DataFrame is not parsed, so try the
                    # combined name, e.g., if the column name is a[5],
                    # get_tree_item_path will return ['a', '[5]']
                    name = get_tree_item_name(path[i:])
                    d[name] = data
                return False
            d = d[p]
        d[path[-1]] = data
        return True

    def GetData(self, path):
        # get data from "path"
        if isinstance(path, str):
            path = get_tree_item_path(path)
        return self.GetItemDataFromPath(path)

    def UpdateData(self, data, refresh=True, activate=True):
        # set data to "path"
        if not data:
            return
        self.data.update(build_tree(data))
        if refresh:
            self.Fill(self.pattern)
        if activate:
            item = self.FindItemFromPath([list(data.keys())[0]])
            if item and item.IsOk():
                self.EnsureVisible(item)
                self.SelectItem(item)
                if self.ItemHasChildren(item):
                    self.Expand(item)

    def _has_pattern(self, d):
        # check if dict d has any children with self.pattern in key
        if not isinstance(d, MutableMapping):
            return False

        if any(self.pattern in k.lower() for k in d.keys()):
            return True
        for v in d.values():
            if self._has_pattern(v):
                return True
        return False

    def _is_folder(self, d):
        # check if the treectrl item corresponding to data d shall be a folder
        return isinstance(d, MutableMapping)

    def get_children(self, item):
        """ callback function to return the children of item """
        pattern = self.pattern
        data = self.GetItemData(item)

        in_path = False
        if pattern:
            path = self.GetItemPath(item)
            in_path = any(pattern in p for p in path)

        children = [[k, self._is_folder(v)]  for k, v in data.items() \
                     if not pattern or in_path or pattern in k.lower() \
                        or self._has_pattern(v)]
        children = [c for c in children if c[0] not in self.exclude_keys]
        if pattern:
            self.expanded = [c for c, _ in children if pattern not in c]
        if item == self.GetRootItem() and not self.expanded and children:
            self.expanded = [children[0][0]]

        children = [{'label': c, 'img':-1, 'imgsel':-1, 'data': None, 'is_folder': is_folder} for c, is_folder in children]
        return children

    def OnCompareItems(self, item1, item2):
        """compare the two items for sorting"""
        text1 = self.GetItemText(item1)
        text2 = self.GetItemText(item2)
        rtn = -1 # default item1 is first
        if text1 and text2:
            if text1.lower() == text2.lower():
                rtn = 0 # item1 is same as item2
            elif text1.lower() >= text2.lower():
                rtn = 1 # item2 is first
        return rtn

    def Load(self, data, filename=None):
        """load the dict data"""
        self.data = data
        if self.config_file:
            self.config_file.Flush()
        self.config_file = None
        self.filename = filename
        if filename:
            _, filename = os.path.split(self.filename)
            self.config_file = ConfigFile(f'{filename}.swp')
            converted_item = self.config_file.GetConfig('conversion', 'converted_item')
            if converted_item is not None and not wx.GetKeyState(wx.WXK_SHIFT):
                for p, c in converted_item.items():
                    idx, settings = c
                    self.AddConvert(p, idx, settings)

        self.Fill(self.pattern)

    def Fill(self, pattern=None):
        """fill the objects tree"""
        # clear the tree control
        self.expanded = {}
        self.DeleteAllItems()
        if not self.data:
            return

        # update the pattern
        self.pattern = pattern
        if isinstance(self.pattern, str):
            self.pattern = self.pattern.lower()
            self.pattern.strip()

        # add the root item
        item = self.AddRoot("root")
        # fill the top level item
        self.FillChildren(item)

        if not self.expanded:
            return
        # expand the child to show the items that match pattern
        child, cookie = self.GetFirstChild(item)
        while child.IsOk():
            name = self.GetItemText(child)
            if name in self.expanded:
                self.Expand(child)
                # only the 1st child, otherwise it may be too many items
                break
            child, cookie = self.GetNextChild(item, cookie)

    def FindItemFromPath(self, path):
        if not path:
            return None

        if isinstance(path, str):
            path = [path]

        item = self.GetRootItem()
        if not item.IsOk():
            return None
        for p in path:
            child, cookie = self.GetFirstChild(item)
            while child.IsOk():
                name = self.GetItemText(child)
                if name == p:
                    item = child
                    break
                child, cookie = self.GetNextChild(item, cookie)
            else:
                return None
        return item

    def SelectSignal(self, items, values, config, additional=None, start=''):
        data = self.data
        if start:
            data = self.GetData(start)
        # remove the "start" from values
        if start:
            for k, v in values.items():
                if not v or not v.startswith(start):
                    continue
                # remove '{start}.'
                values[k] = v[len(start):].lstrip('.')

        dlg = SignalSelSettingDlg(self.GetTopLevelParent(), data=data,
                                  items=items, values=values, config=config,
                                  additional=additional)
        if dlg.ShowModal() == wx.ID_OK:
            settings = dlg.GetSettings()
            df = pd.DataFrame()
            for item in items:
                signal = settings.get(item, '')
                if not signal:
                    print(f'Input "{item}" is missing!')
                    return None, settings
                if start:
                    signal = f'{start}.{signal}'
                d = self.GetData(signal)
                if d is None:
                    print(f'Invalid input "{item}({signal})"!')
                    return None, settings
                if len(df) > 0 and len(d) != len(df):
                    print(f'Input "{item}({signal})" has different length with others!')
                    return None, settings
                if hasattr(d, 'shape') and len(d.shape) > 1:
                    print(f'Input "{item}({signal})" is not 1-d!')
                    return None, settings
                df[item] = d
                # the full path with "start"
                settings[item] = signal
            return df, settings
        return None, None


class TreeCtrlWithTimeStamp(TreeCtrlBase):
    # the leaf node is a DataFrame

    ID_EXPORT_WITH_TIMESTAMP = wx.NewIdRef()
    timestamp_key = 'timestamp'

    def __init__(self, parent, style=wx.TR_DEFAULT_STYLE):
        super().__init__(parent, style=style)
        # hide the "timestamp"
        self.exclude_keys = [self.timestamp_key]

    def _has_pattern(self, d):
        if isinstance(d, pd.DataFrame):
            # check if pattern is in any column
            return any(self.pattern in k.lower() for k in d.columns)
        return super()._has_pattern(d)

    def _is_folder(self, d):
        return super()._is_folder(d) or isinstance(d, pd.DataFrame)

    def GetItemMenu(self, item):
        menu = super().GetItemMenu(item)
        if menu is None:
            return None
        has_child = self.ItemHasChildren(item)
        if not has_child:
            menu.Insert(1, self.ID_EXPORT_WITH_TIMESTAMP, "Export to shell with timestamp")
        return menu

    def GetItemExportData(self, item):
        path = self.GetItemPath(item)
        output = pd.DataFrame()
        if self.ItemHasChildren(item):
            output = self.GetItemDragData(item)
            output_name = get_variable_name(path)
        else:
            data = self.GetItemData(item)
            data_x = self.GetItemTimeStamp(item)
            output[path[-1]] = data

            selections = self.GetSelections()
            for sel in selections:
                y = self.GetItemData(sel)
                x = self.GetItemTimeStamp(sel)
                if hasattr(x, 'equals'):
                    if not x.equals(data_x):
                        continue
                elif len(y) != len(data):
                    # only combine the data in the same DataFrame
                    continue
                name = self.GetItemText(sel)
                output[name] = y

            if len(selections) <= 1:
                output_name = get_variable_name(path)
            else:
                output_name = get_variable_name(path[:-1])
        return output_name, output

    def OnProcessCommand(self, cmd, item):
        if cmd in [self.ID_EXPORT_WITH_TIMESTAMP]:
            output_name, output = self.GetItemExportData(item)
            if isinstance(output, pd.DataFrame):
                output.insert(0, column=self.timestamp_key, value=self.GetItemTimeStamp(item))

            send_data_to_shell(output_name, output)
        else:
            super().OnProcessCommand(cmd, item)

    def GetItemTimeStampFromPath(self, path):
        if isinstance(path, str):
            path = get_tree_item_path(path)
        # path is an array, e.g., path = get_tree_item_path(name)
        d = self.data
        for i, p in enumerate(path[:-1]):
            if p not in d:
                if isinstance(d, pd.DataFrame):
                    # the name in node DataFrame is not parsed, so try the
                    # combined name, e.g., if the column name is a[5],
                    # get_tree_item_path will return ['a', '[5]']
                    name = get_tree_item_name(path[i:])
                    if name in d and self.timestamp_key in d:
                        return d[self.timestamp_key]
                return None
            d = d[p]
        if isinstance(d, pd.DataFrame) and self.timestamp_key in d:
            return d[self.timestamp_key]
        return None

    def GetItemTimeStamp(self, item):
        path = self.GetItemPath(item)
        return self.GetItemTimeStampFromPath(path)

    def GetItemPlotData(self, item):
        if self.ItemHasChildren(item):
            return None, None
        y = self.GetItemData(item)
        x = self.GetItemTimeStamp(item)
        return x, y

    def FlattenTree(self, data):
        data = flatten_tree(data)
        data_size = [len(data[k]) for k in data]
        data_1d = [len(data[k].shape) <= 1 or sorted(data[k].shape)[-2] == 1 for k in data]
        if all(data_1d) and all(d == data_size[0] for d in data_size):
            df = pd.DataFrame()
            for name, val in data.items():
                if name == self.timestamp_key:
                    continue
                if isinstance(val, np.ndarray):
                    val = val.flatten()
                df[name] = val
            if self.timestamp_key in data:
                df.insert(0, column=self.timestamp_key, value=data[self.timestamp_key])
            data = df
        return data

    def GetItemDragData(self, item):
        if self.ItemHasChildren(item):
            return self.GetItemData(item)
        # leaf node, return the corresponding column and timestamp only
        x, y = self.GetItemPlotData(item)
        if x is None or y is None:
            return None
        df = pd.DataFrame()
        name = self.GetItemText(item)
        df[self.timestamp_key] = x
        df[name] = y
        return df

    def GetPlotXLabel(self):
        return "t"


class TreeCtrlNoTimeStamp(TreeCtrlBase):
    # the data doesn't have timestamp, so let the user selects the x-axis data
    XAXIS = 'xaxis'
    ID_SET_X = wx.NewIdRef()
    ID_EXPORT = wx.NewIdRef()
    ID_EXPORT_WITH_X = wx.NewIdRef()
    ID_PLOT = wx.NewIdRef()

    def __init__(self, *args, **kwargs):
        TreeCtrlBase.__init__(self, *args, **kwargs)
        self.x_path = None
        self._convert_labels[self.XAXIS] = 'Set as x-axis'

    def Load(self, data, filename=None):
        super().Load(data, filename)
        if self.x_path is not None:
            # check if x_path is still in the data, clear it if not
            x = self.GetItemDataFromPath(self.x_path)
            if x is None:
                self.x_path = None

    def AddConvert(self, p, idx, settings):
        rtn = super().AddConvert(p, idx, settings)
        if rtn and settings.get(self.XAXIS, False):
            self.SetXaxisPath(get_tree_item_path(p))
        return rtn

    def RefreshChildren(self, item):
        super().RefreshChildren(item)
        if self.x_path:
            item = self.FindItemFromPath(self.x_path)
            if item is not None and item.IsOk():
                self.SetItemBold(item, True)

    def GetConvertItemProp(self, item, inputs, outputs):
        # the configuration props used to convert an item
        props = super().GetConvertItemProp(item, inputs, outputs)
        if len(outputs) == 1:
            # for single output
            xaxis_label = self._convert_labels.get(self.XAXIS, 'Set as x-axis')
            props.append(PropCheckBox().Label(xaxis_label).Name(self.XAXIS).Value(False))
        return props

    def GetCustomizedConvertProp(self):
        # the configuration props used to convert an item
        props = super().GetCustomizedConvertProp()
        xaxis_label = self._convert_labels.get(self.XAXIS, 'Set as x-axis')
        props.append(PropCheckBox().Label(xaxis_label).Name(self.XAXIS).Value(False))
        return props

    def ConvertItems(self, item, items, equation=None, config=None,
                     force_select_signal=False, **kwargs):
        new_item, settings = super().ConvertItems(item, items, equation, config,
                                                  force_select_signal, **kwargs)
        if new_item and len(new_item) == 1 and new_item[0].IsOk():
            if settings is not None and settings.get(self.XAXIS, False):
                path = self.GetItemPath(new_item[0])
                self.SetXaxisPath(path)
        return new_item, settings

    def SetXaxisPath(self, path):
        if self.x_path == path:
            return
        if self.x_path:
            # clear the current x-axis data
            item = self.FindItemFromPath(self.x_path)
            if item is not None:
                self.SetItemBold(item, False)
        # select the new data as x-axis
        self.x_path = path
        if path:
            item = self.FindItemFromPath(path)
            if item is not None:
                self.SetItemBold(item, True)

    def GetItemPlotData(self, item):
        if self.ItemHasChildren(item):
            return None, None

        y = self.GetItemData(item)
        x = None
        if self.x_path is not None and self.GetItemPath(item) != self.x_path:
            x = self.GetItemDataFromPath(self.x_path)
            if len(x) != len(y):
                name = self.GetItemText(item)
                print(f"'{name}' and '{self.x_path[-1]}' have different length, ignore x-axis data!")
                x = None
        if x is None:
            x = np.arange(0, len(y))
        return x, y

    def GetItemMenu(self, item):
        if not item.IsOk():
            return None
        if self.ItemHasChildren(item):
            return None
        menu = super().GetItemMenu(item)
        if menu is None:
            return None
        selections = self.GetSelections()
        if not selections:
            selections = [item]
        path = self.GetItemPath(item)
        if len(selections) <= 1:
            # single item selection
            if self.x_path and self.x_path == path:
                mitem = menu.InsertCheckItem(0, self.ID_SET_X, "Unset as x-axis data")
                mitem.Check(True)
            else:
                menu.InsertCheckItem(0, self.ID_SET_X, "Set as x-axis data")
            menu.InsertSeparator(1)

        if self.x_path and (self.x_path != path or len(selections) > 1):
            menu.Insert(3, self.ID_EXPORT_WITH_X, "Export to shell with x-axis data")
        return menu

    def GetItemExportData(self, item):
        y = self.GetItemData(item)
        path = self.GetItemPath(item)
        name = self.GetItemText(item)
        data = [[name, y]]
        selections = self.GetSelections()
        for sel in selections:
            if self.ItemHasChildren(sel) and sel != item:
                continue
            y = self.GetItemData(sel)
            name = self.GetItemText(sel)
            data.append([name, y])
        data_size = [len(d[1]) for d in data]
        data_1d = [len(d[1].shape) <= 1 or sorted(d[1].shape)[-2] == 1  for d in data]
        if all(data_1d) and all(d == data_size[0] for d in data_size):
            # if all data has same size, convert it to DataFrame
            df = pd.DataFrame()
            for name, val in data:
                if isinstance(val, np.ndarray):
                    val = val.flatten()
                df[name] = val
            data = df

        if len(selections) <= 1:
            output_name = get_variable_name(path)
        else:
            output_name = "_data"
        return output_name, data

    def OnProcessCommand(self, cmd, item):
        path = self.GetItemPath(item)
        if not path:
            return
        if cmd in [self.ID_EXPORT_WITH_X]:
            output_name, data = self.GetItemExportData(item)
            x, y = self.GetItemPlotData(item)
            if x is not None:
                if isinstance(data, pd.DataFrame):
                    data.insert(0, column='x', value=x)
                else:
                    data.insert(0, ['x', x])
            send_data_to_shell(output_name, data)

        elif cmd == self.ID_SET_X:
            if self.x_path != path:
                # select the new data as x-axis
                self.SetXaxisPath(path)
            else:
                # clear the current x-axis
                self.SetXaxisPath(None)
        else:
            super().OnProcessCommand(cmd, item)


class PanelBase(wx.Panel):

    Gcc = None
    ID_OPEN = wx.NewIdRef()
    ID_REFRESH = wx.NewIdRef()
    def __init__(self, parent, filename=None, autohide=True, **kwargs):
        wx.Panel.__init__(self, parent, **kwargs)
        if autohide:
            # Hide the window for now, it will be shown when add to AUI manager
            self.Hide()

        self.init()

        self.filename = None
        if filename is not None:
            self.Load(filename)

        self.num = self.Gcc.get_next_num()
        self.Gcc.set_active(self)

    def init(self):
        self.Bind(wx.EVT_TOOL, self.OnProcessCommand)
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateCmdUI)

    def GetFileName(self):
        filename = 'untitled'
        if self.filename:
            (_, filename) = os.path.split(self.filename)
        return filename

    def GetCaption(self):
        return self.GetFileName()

    def Load(self, filename, add_to_history=True):
        """load the file"""
        self.filename = filename
        # add the filename to history
        if add_to_history:
            dp.send('frame.add_file_history', filename=filename)
        title = self.GetCaption()
        dp.send('frame.set_panel_title', pane=self, title=title)

    def Destroy(self):
        """
        Destroy the mat properly before close the pane.
        """
        self.Gcc.destroy(self.num)
        super().Destroy()

    @classmethod
    def GetFileType(cls):
        return "|All files (*.*)|*.*"

    @classmethod
    def get_all_managers(cls):
        return cls.Gcc.get_all_managers()

    @classmethod
    def get_active(cls):
        return cls.Gcc.get_active()

    @classmethod
    def set_active(cls, panel):
        return cls.Gcc.set_active(panel)

    @classmethod
    def get_manager(cls, num):
        return cls.Gcc.get_manager(num)

    def OnProcessCommand(self, event):
        """process the menu command"""
        eid = event.GetId()
        if eid == self.ID_OPEN:
            style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
            wildcard = self.GetFileType()
            dlg = wx.FileDialog(self, "Choose a file", "", "", wildcard, style)
            if dlg.ShowModal() == wx.ID_OK:
                filename = dlg.GetPath()
                self.Load(filename=filename)
                title = self.GetCaption()
                dp.send('frame.set_panel_title', pane=self, title=title)
            dlg.Destroy()
        elif eid == self.ID_REFRESH:
            if self.filename:
                self.Load(filename=self.filename)

    def OnUpdateCmdUI(self, event):
        eid = event.GetId()
        if eid == self.ID_REFRESH:
            event.Enable(self.filename is not None)

    def JumpToLine(self, lineno):
        return

class PanelNotebookBase(PanelBase):
    ID_MORE = wx.NewIdRef()
    ID_CONVERT_CUSTOM = wx.NewIdRef()
    ID_CONVERT_MANAGE = wx.NewIdRef()

    def init(self):
        self.tb = aui.AuiToolBar(self, -1, agwStyle=aui.AUI_TB_OVERFLOW)
        self.tb.SetToolBitmapSize(wx.Size(16, 16))

        self.init_toolbar()
        self.tb.Realize()

        self.notebook = aui.AuiNotebook(self, agwStyle=aui.AUI_NB_TOP | aui.AUI_NB_TAB_SPLIT | aui.AUI_NB_SCROLL_BUTTONS | wx.NO_BORDER)

        self.tree = None
        self.init_pages()

        self.box = wx.BoxSizer(wx.VERTICAL)
        self.box.Add(self.tb, 0, wx.EXPAND, 5)
        self.box.Add(self.notebook, 1, wx.EXPAND)

        #self.box.Fit(self)
        self.SetSizer(self.box)

        super().init()

    def init_toolbar(self):
        open_bmp = svg_to_bitmap(open_svg, win=self)
        self.tb.AddTool(self.ID_OPEN, "Open", open_bmp,
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        "Open file")
        self.tb.AddSeparator()
        refresh_bmp = svg_to_bitmap(refresh_svg, win=self)
        self.tb.AddTool(self.ID_REFRESH, "Refresh", refresh_bmp,
                        wx.NullBitmap, wx.ITEM_NORMAL,
                        "Refresh file")

        self.tb.AddStretchSpacer()
        self.tb.AddTool(self.ID_MORE, "More", svg_to_bitmap(more_svg, win=self),
                        wx.NullBitmap, wx.ITEM_NORMAL, "More")

    def init_pages(self):
        return

    def CreatePageWithSearch(self, PageClass):
        panel = wx.Panel(self.notebook)
        search = AutocompleteTextCtrl(panel)
        search.SetHint('searching ...')
        ctrl = PageClass(panel)
        szAll = wx.BoxSizer(wx.VERTICAL)
        szAll.Add(search, 0, wx.EXPAND|wx.ALL, 2)
        szAll.Add(ctrl, 1, wx.EXPAND)
        szAll.Fit(panel)
        panel.SetSizer(szAll)
        return panel, search, ctrl

    def OnProcessCommand(self, event):
        eid = event.GetId()
        if eid == self.ID_MORE:
            if isinstance(self.tree, TreeCtrlBase):
                menu = wx.Menu()
                menu.Append(self.ID_CONVERT_CUSTOM, "Add custom convert")
                menu.Append(self.ID_CONVERT_MANAGE, "Manage custom convert")
            self.PopupMenu(menu)
        elif eid == self.ID_CONVERT_CUSTOM:
            if isinstance(self.tree, TreeCtrlBase):
                self.tree.AddCustomizedConvert()
        elif eid == self.ID_CONVERT_MANAGE:
            if isinstance(self.tree, TreeCtrlBase):
                self.tree.ManageCustomizedConvert()
        else:
            super().OnProcessCommand(event)

    def OnUpdateCmdUI(self, event):
        eid = event.GetId()
        if eid == self.ID_CONVERT_MANAGE:
            if isinstance(self.tree, TreeCtrlBase):
                event.Enable(len(self.tree.GetCustomizedConvert()))
        else:
            super().OnUpdateCmdUI(event)

class FileViewBase(Interface):
    name = None
    panel_type = PanelBase
    target_pane = "History"

    ID_PANE_COPY_PATH = wx.NewIdRef()
    ID_PANE_COPY_PATH_REL = wx.NewIdRef()
    ID_PANE_SHOW_IN_FINDER = wx.NewIdRef()
    ID_PANE_SHOW_IN_BROWSING = wx.NewIdRef()
    ID_PANE_CLOSE = wx.NewIdRef()
    ID_PANE_CLOSE_OTHERS = wx.NewIdRef()
    ID_PANE_CLOSE_ALL = wx.NewIdRef()

    @classmethod
    def initialize(cls, frame, **kwargs):
        super().initialize(frame, **kwargs)

        cls.IDS = {}
        cls.init_menu()

        dp.connect(cls.process_command, signal=f'bsm.{cls.name}')
        dp.connect(receiver=cls.set_active, signal='frame.activate_panel')
        dp.connect(receiver=cls.open, signal='frame.file_drop')
        dp.connect(cls.PaneMenu, f'bsm.{cls.name}.pane_menu')

    @classmethod
    def get_menu(cls):
        return [['open', f'File:Open:{cls.name} file']]

    @classmethod
    def init_menu(cls):
        assert cls.name is not None
        for key, menu in cls.get_menu():
            resp = dp.send(signal='frame.add_menu',
                           path=menu,
                           rxsignal=f'bsm.{cls.name}')
            if resp:
                cls.IDS[key] = resp[0][1]

    @classmethod
    def set_active(cls, pane):
        if pane and isinstance(pane, cls.panel_type):
            if cls.panel_type.get_active() == pane:
                return
            cls.panel_type.set_active(pane)

    @classmethod
    def uninitializing(cls):
        super().uninitializing()
        # before save perspective
        for mgr in cls.panel_type.get_all_managers():
            dp.send('frame.delete_panel', panel=mgr)
        for key, menu in cls.get_menu():
            if key not in cls.IDS:
                continue
            dp.send('frame.delete_menu', path=menu, id=cls.IDS[key])

    @classmethod
    def process_command(cls, command):
        if command == cls.IDS.get('open', None):
            style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
            wildcard = cls.panel_type.GetFileType()
            dlg = wx.FileDialog(cls.frame, "Choose a file", "", "", wildcard, style)
            if dlg.ShowModal() == wx.ID_OK:
                filename = dlg.GetPath()
                cls.open(filename=filename, activate=True)
            dlg.Destroy()

    @classmethod
    def check_filename(cls, filename):
        raise NotImplementedError

    @classmethod
    def open(cls,
            filename=None,
            num=None,
            activate=True,
            add_to_history=True,
            lineno=None,
            **kwargs):
        """
        open an file

        If the file has already been opened, return its handler; otherwise, create it.
        """
        if not cls.check_filename(filename):
            return None

        manager = cls.get_manager(num, filename, active=False)
        if manager is None:
            manager = cls.panel_type(cls.frame)
            if filename:
                manager.Load(filename, add_to_history=add_to_history)
            title = manager.GetCaption()
            dp.send(signal="frame.add_panel",
                    panel=manager,
                    title=title,
                    target=cls.target_pane,
                    pane_menu={'rxsignal': f'bsm.{cls.name}.pane_menu',
                           'menu': [
                               {'id':cls.ID_PANE_CLOSE, 'label':'Close'},
                               {'id':cls.ID_PANE_CLOSE_OTHERS, 'label':'Close Others'},
                               {'id':cls.ID_PANE_CLOSE_ALL, 'label':'Close All'},
                               {'type': wx.ITEM_SEPARATOR},
                               {'id':cls.ID_PANE_COPY_PATH, 'label':'Copy Path'},
                               {'id':cls.ID_PANE_COPY_PATH_REL, 'label':'Copy Relative Path'},
                               {'type': wx.ITEM_SEPARATOR},
                               {'id': cls.ID_PANE_SHOW_IN_FINDER, 'label':f'Reveal in  {get_file_finder_name()}'},
                               {'id': cls.ID_PANE_SHOW_IN_BROWSING, 'label':'Reveal in Browsing panel'},
                               ]} )
            return manager
        # activate the manager
        if manager:
            if activate:
                dp.send(signal='frame.show_panel', panel=manager)
            if isinstance(lineno, int) and lineno > 0:
                manager.JumpToLine(lineno)
        return manager

    @classmethod
    def PaneMenu(cls, pane, command):
        if not pane or not isinstance(pane, cls.panel_type):
            return
        if command in [cls.ID_PANE_COPY_PATH, cls.ID_PANE_COPY_PATH_REL]:
            if wx.TheClipboard.Open():
                filepath = pane.filename
                if command == cls.ID_PANE_COPY_PATH_REL:
                    filepath = os.path.relpath(filepath, os.getcwd())
                wx.TheClipboard.SetData(wx.TextDataObject(filepath))
                wx.TheClipboard.Close()
        elif command == cls.ID_PANE_SHOW_IN_FINDER:
            show_file_in_finder(pane.filename)
        elif command == cls.ID_PANE_SHOW_IN_BROWSING:
            dp.send(signal='dirpanel.goto', filepath=pane.filename, show=True)
        elif command == cls.ID_PANE_CLOSE:
            dp.send(signal='frame.delete_panel', panel=pane)
        elif command == cls.ID_PANE_CLOSE_OTHERS:
            mgrs =  cls.panel_type.get_all_managers()
            for mgr in mgrs:
                if mgr == pane:
                    continue
                dp.send(signal='frame.delete_panel', panel=mgr)
        elif command == cls.ID_PANE_CLOSE_ALL:
            mgrs =  cls.panel_type.get_all_managers()
            for mgr in mgrs:
                dp.send(signal='frame.delete_panel', panel=mgr)

    @classmethod
    def get_manager(cls, num=None, filename=None, active=True):
        manager = None
        if num is None and filename is None and active:
            manager = cls.panel_type.get_active()
        if num is not None:
            manager = cls.panel_type.get_manager(num)
        if manager is None and isinstance(filename, str):
            abs_filename = os.path.abspath(filename).lower()
            for m in cls.panel_type.get_all_managers():
                if m.filename and abs_filename == os.path.abspath(m.filename).lower():
                    manager = m
                    break
        return manager

    @classmethod
    def get(cls, num=None, filename=None, data_only=True):
        # return the content of a file
        manager = cls.get_manager(num, filename)
        if num is None and filename is None and manager is None:
            manager = cls.panel_type.get_active()
        return manager
