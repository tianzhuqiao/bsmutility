import wx
from wx import stc
import wx.py.dispatcher as dp

class FindMixin:
    ID_FIND_REPLACE = wx.NewIdRef()
    ID_FIND_NEXT = wx.NewIdRef()
    ID_FIND_PREV = wx.NewIdRef()
    def __init__(self, replace=False):
        self.SetupFind(replace)

        self.index_column = 0

        self._copy_columns = None
        self.wrapped = 0

    def BuildAccelTable(self):
        accel = [
            (wx.ACCEL_CTRL, ord('F'), wx.ID_FIND),
            (wx.ACCEL_SHIFT, wx.WXK_F3, self.ID_FIND_PREV),
            (wx.ACCEL_CTRL, ord('H'), self.ID_FIND_REPLACE),
            (wx.ACCEL_RAW_CTRL, ord('H'), self.ID_FIND_REPLACE),
        ]
        return accel

    def SetupFind(self, replace=False):
        # find & replace dialog
        self.findDialog = None
        self.findStr = ""
        self.replaceStr = ""
        self.findFlags = 1
        self.wrapped = 0

        self.Bind(wx.EVT_TOOL, self.OnShowFind, id=wx.ID_FIND)
        if replace:
            # Support find & replace dialog
            self.Bind(wx.EVT_TOOL, self.OnShowFindReplace, id=self.ID_FIND_REPLACE)
        self.Bind(wx.EVT_TOOL, self.OnFindNext, id=self.ID_FIND_NEXT)
        self.Bind(wx.EVT_TOOL, self.OnFindPrev, id=self.ID_FIND_PREV)

    def OnShowFind(self, event):
        self.ShowFindReplace()

    def OnShowFindReplace(self, event):
        """Find and Replace dialog and action."""
        self.ShowFindReplace(style=wx.FR_REPLACEDIALOG)

    def ShowFindReplace(self, findStr="", style=0):
        # find string
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
        if style & wx.FR_REPLACEDIALOG:
            title = 'Find & Replace'

        self.findDialog = wx.FindReplaceDialog(
            self, data, title, style)
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

    def doFind(self, strFind, forward=True):
        """search the string"""
        return -1

    def OnFind(self, event):
        """search the string"""
        self.findStr = event.GetFindString()
        self.findFlags = event.GetFlags()
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


class FindListMixin(FindMixin):

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

        # deselect all
        while True:
            sel = self.GetFirstSelected()
            if sel == -1:
                break
            self.Select(sel, False)
        # select the one found
        self.EnsureVisible(position)
        self.Select(position)
        return position

class FindTreeMixin(FindMixin):

    def GetNextItem(self, item):
        if (item is None) or not item.IsOk():
            return item

        if self.ItemHasChildren(item):
            item_next, _ = self.GetFirstChild(item)
            if item_next is not None and item_next.IsOk():
                return item_next
        item_next = self.GetNextSibling(item)
        if item_next is not None and item_next.IsOk():
            return item_next

        item_next = self.GetItemParent(item)
        while (item_next is not None) and item_next.IsOk():
            if item_next == self.GetRootItem():
                # reach the root, no more item to try
                return None
            else:
                # try parent's sibling
                sibling = self.GetNextSibling(item_next)
                if (sibling is not None) and sibling.IsOk():
                    # parent has sibling, visit it
                    item_next = sibling
                    break
                else:
                    # parent doesn't have sibling, try parent's parent
                    item_next = self.GetItemParent(item_next)
        return item_next

    def GetPrevItem(self, item):
        if (item is None) or not item.IsOk():
            return item

        item_prev = self.GetPrevSibling(item)
        if item_prev is not None and item_prev.IsOk():
            # find the "last" children of item_prev
            while self.ItemHasChildren(item_prev):
                child = self.GetLastChild(item_prev)
                if (child is None) or not child.IsOk():
                    break
                item_prev = child

            return item_prev

        item_prev = self.GetItemParent(item)
        if item_prev == self.GetRootItem():
            return None
        return item_prev

    def FindText(self, item, text, flags=0):
        return self.Search(self.GetItemText(item), text, flags)

    def doFind(self, strFind, forward=True):
        item_found = None
        item = self.GetFocusedItem()
        if forward:
            item = self.GetNextItem(item)
            while (item is not None) and item.IsOk():
                if wx.GetKeyState(wx.WXK_ESCAPE):
                    # use escape to quit "find", in case there are a lot of
                    # items
                    item_found = item
                    break
                if self.FindText(item, strFind, self.findFlags):
                    item_found = item
                    break
                item = self.GetNextItem(item)

            if item_found is None:
                # wrap around
                self.wrapped += 1
                item, _ = self.GetFirstChild(self.GetRootItem())
                while (item is not None) and item.IsOk():
                    if wx.GetKeyState(wx.WXK_ESCAPE):
                        item_found = item
                        break
                    if self.FindText(item, strFind, self.findFlags):
                        item_found = item
                        break
                    item = self.GetNextItem(item)
        else:
            item = self.GetPrevItem(item)
            while (item is not None) and item.IsOk():
                if wx.GetKeyState(wx.WXK_ESCAPE):
                    item_found = item
                    break
                if self.FindText(item, strFind, self.findFlags):
                    item_found = item
                    break
                item = self.GetPrevItem(item)

            if item_found is None:
                # wrap around
                self.wrapped += 1
                item = self.GetLastChild(self.GetRootItem())
                while (item is not None) and item.IsOk():
                    if wx.GetKeyState(wx.WXK_ESCAPE):
                        item_found = item
                        break
                    if self.FindText(item, strFind, self.findFlags):
                        item_found = item
                        break
                    item = self.GetPrevItem(item)

        # not found the target, do not change the current position
        if item_found is None:
            self.message("'%s' not found!" % strFind)
            strFind = """"""
            item_found = self.GetFocusedItem()

        if self.GetWindowStyle() & wx.TR_MULTIPLE:
            for item in self.GetSelections():
                self.SelectItem(item, False)

        if (self.GetWindowStyle() & wx.TR_MULTIPLE) and hasattr(self, "SetFocusedItem"):
            # on Windows, when "wx.TR_MULTIPLE" style is set, without this line
            # the focused item will not be set to "item_found" with SelectItem;
            # and when "wx.TR_MULTIPLE" style is not set, call this line will
            # not highlight item_found with SelectItem
            self.SetFocusedItem(item_found)

        self.EnsureVisible(item_found)
        self.SelectItem(item_found)
        return item_found


class FindEditorMixin(FindMixin):

    def OnShowFind(self, event):
        findStr = self.GetSelectedText()
        self.ShowFindReplace(findStr, style=0)

    def OnShowFindReplace(self, event):
        # find string
        findStr = self.GetSelectedText()
        self.ShowFindReplace(findStr, style=wx.FR_REPLACEDIALOG)

    def _find_text(self, minPos, maxPos, text, flags=0):
        position = self.FindText(minPos, maxPos, text, flags)
        if isinstance(position, tuple):
            position = position[0] # wx ver 4.1.0 returns (start, end)
        return position

    def doFind(self, strFind, forward=True):
        """search the string"""
        current = self.GetCurrentPos()
        position = -1

        stcFindFlags = 0
        if wx.FR_WHOLEWORD & self.findFlags:
            stcFindFlags |= stc.STC_FIND_WHOLEWORD
        if wx.FR_MATCHCASE & self.findFlags:
            stcFindFlags |= stc.STC_FIND_MATCHCASE

        if forward:
            position = self._find_text(current, len(self.GetText()),
                                       strFind, stcFindFlags)
            if position == -1:
                # wrap around
                self.wrapped += 1
                position = self._find_text(0, current + len(strFind), strFind,
                                           stcFindFlags)
        else:
            position = self._find_text(current - len(strFind), 0, strFind,
                                       stcFindFlags)
            if position == -1:
                # wrap around
                self.wrapped += 1
                position = self._find_text(len(self.GetText()), current,
                                           strFind, stcFindFlags)

        # not found the target, do not change the current position
        if position == -1:
            self.message("'%s' not found!" % strFind)
            position = current
            strFind = """"""
        self.GotoPos(position)
        self.SetSelection(position, position + len(strFind))
        return position
