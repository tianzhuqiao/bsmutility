import wx
from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin
from .findmixin import FindListMixin

class FindListCtrl(wx.ListCtrl, FindListMixin):
    ID_COPY_NO_INDEX = wx.NewIdRef()
    ID_COPY_SEL_COLS = wx.NewIdRef()
    def __init__(self, *args, **kwargs):
        wx.ListCtrl.__init__(self, *args, **kwargs)
        FindListMixin.__init__(self)

        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.OnRightClick)
        self.Bind(wx.EVT_TOOL, self.OnBtnSelectAll, id=wx.ID_SELECTALL)
        self.Bind(wx.EVT_TOOL, self.OnBtnCopy, id=wx.ID_COPY)
        self.Bind(wx.EVT_TOOL, self.OnBtnCopy, id=self.ID_COPY_NO_INDEX)
        self.Bind(wx.EVT_TOOL, self.OnBtnCopy, id=self.ID_COPY_SEL_COLS)

        accel = self.BuildAccelTable()
        self.accel = wx.AcceleratorTable(accel)
        self.SetAcceleratorTable(self.accel)

    def BuildAccelTable(self):
        accel = [
            (wx.ACCEL_CTRL, ord('A'), wx.ID_SELECTALL),
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('C'), self.ID_COPY_NO_INDEX),
        ]
        return accel + FindListMixin.BuildAccelTable(self)

    def OnRightClick(self, event):

        if self.GetItemCount() <= 0:
            return

        menu = wx.Menu()
        menu.Append(wx.ID_SELECTALL, "&Select all\tCtrl+A")
        if self.GetSelectedItemCount() > 0:
            menu.AppendSeparator()
            menu.Append(wx.ID_COPY, "&Copy \tCtrl+C")
            if 0 <= self.index_column < self.GetColumnCount():
                menu.Append(self.ID_COPY_NO_INDEX, "C&opy without index \tCtrl+Shift+C")
            if self.GetColumnCount() > 1:
                menu.Append(self.ID_COPY_SEL_COLS, "Copy &selected columns")

        self.PopupMenu(menu)

    def OnBtnSelectAll(self, event):
        for i in range(self.GetItemCount()):
            self.Select(i)

    def OnBtnCopy(self, event):
        cmd = event.GetId()
        columns = list(range(self.GetColumnCount()))
        if cmd == self.ID_COPY_NO_INDEX:
            columns.remove(self.index_column)
        elif cmd == self.ID_COPY_SEL_COLS:
            lst = [self.GetColumn(c).GetText() for c in range(self.GetColumnCount())]
            dlg = wx.MultiChoiceDialog(self, "Select column(s):","Copy ...", lst)
            if self._copy_columns is None:
                # default all columns
                self._copy_columns = range(len(lst))
            dlg.SetSelections(self._copy_columns)
            if dlg.ShowModal() == wx.ID_OK:
                columns = dlg.GetSelections()
                self._copy_columns = columns

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


class ListCtrlAutoWidthMixin2(ListCtrlAutoWidthMixin):

    def __init__(self):
        super().__init__()
        self.enable_auto_width = True

    def EnableAutoWidth(self, enable):
        self.enable_auto_width = enable

    def IsEnableAutoWidth(self):
        return self.enable_auto_width

    def _doResize(self):
        """ Resize the last column as appropriate.

            If the list's columns are too wide to fit within the window, we use
            a horizontal scrollbar.  Otherwise, we expand the right-most column
            to take up the remaining free space in the list.

            We remember the current size of the last column, before resizing,
            as the preferred minimum width if we haven't previously been given
            or calculated a minimum width.  This ensure that repeated calls to
            _doResize() don't cause the last column to size itself too large.
        """

        if not self or not self.IsEnableAutoWidth():  # avoid a PyDeadObject error
            return

        if self.GetSize().height < 32:
            return  # avoid an endless update bug when the height is small.

        numCols = self.GetColumnCount()
        if numCols == 0: return # Nothing to resize.

        # on windows, user can reorder the columns (e.g., by dragging), so
        # make sure the resizeCol is the one currently at that location
        if(self._resizeColStyle == "LAST"):
            resizeCol = self.GetColumnsOrder()[-1] + 1
        else:
            resizeCol = self.GetColumnsOrder()[self._resizeCol-1] + 1

        resizeCol = max(1, resizeCol)

        if self._resizeColMinWidth is None:
            self._resizeColMinWidth = self.GetColumnWidth(resizeCol - 1)

        # Get total width
        listWidth = self.GetClientSize().width

        totColWidth = 0 # Width of all columns except last one.
        for col in range(numCols):
            if col != (resizeCol-1):
                totColWidth = totColWidth + self.GetColumnWidth(col)

        resizeColWidth = self.GetColumnWidth(resizeCol - 1)

        if totColWidth + self._resizeColMinWidth > listWidth:
            # We haven't got the width to show the last column at its minimum
            # width -> set it to its minimum width and allow the horizontal
            # scrollbar to show.
            self.SetColumnWidth(resizeCol-1, self._resizeColMinWidth)
            return

        # Resize the last column to take up the remaining available space.

        self.SetColumnWidth(resizeCol-1, listWidth - totColWidth)


class ListCtrlBase(FindListCtrl, ListCtrlAutoWidthMixin2):
    def __init__(self, parent, style=wx.LC_REPORT|wx.LC_VIRTUAL):
        FindListCtrl.__init__(self, parent, style=style)
        ListCtrlAutoWidthMixin2.__init__(self)
        self.EnableAlternateRowColours()
        self.ExtendRulesAndAlternateColour()

        self.data_start_column = 0
        self.BuildColumns()

        self.data = None
        self.pattern = None
        self.data_shown = []

        self.Bind(wx.EVT_LIST_COL_CLICK, self.OnColClick)

    def BuildColumns(self):
        self.InsertColumn(0, "#", width=60)
        self.data_start_column = 1

    def OnGetItemText(self, item, column):
        if self.data_start_column > 0 and column == 0:
            # index column
            return f"{item+1}"
        return ""

    def SortBy(self, column, ascending):
        return

    def OnColClick(self, event):
        col= event.GetColumn()
        if col == -1:
            return # clicked outside any column.
        ascending = self.GetUpdatedAscendingSortIndicator(col)
        self.ShowSortIndicator(col, ascending)
        self.Fill(self.pattern)

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

        self.Refresh()
        if self.data is None:
            self.SetItemCount(0)
            return
        # sort by column
        col = self.GetSortIndicator()
        ascending = self.IsAscendingSortIndicator()
        self.SortBy(col, ascending)

        self.ApplyPattern()
        self.SetItemCount(len(self.data_shown))

    def GetSelections(self):
        item = self.GetFirstSelected()
        if item < 0:
            return []
        active_items = [item]
        item = self.GetNextSelected(item)
        while item >= 0:
            active_items.append(item)
            item = self.GetNextSelected(item)
        return active_items

    def GetColumnOrder(self, col):
        if self.HasColumnOrderSupport():
            return super().GetColumnOrder(col)
        return col

    def GetColumnIndexFromOrder(self, pos):
        if self.HasColumnOrderSupport():
            return super().GetColumnIndexFromOrder(pos)
        return pos

    def GetColumnsOrder(self):
        if self.HasColumnOrderSupport():
            return super().GetColumnsOrder()
        return list(range(self.GetColumnCount()))

    def SetColumnsOrder(self, orders):
        if self.HasColumnOrderSupport():
            return super().SetColumnsOrder(orders)
        return False
