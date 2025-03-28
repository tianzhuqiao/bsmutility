import sys
import os
import traceback
import keyword
import pprint
import six
import numpy as np
import wx
from wx import stc
import wx.py.dispatcher as dp
import aui2 as aui
from .bsmxpm import open_svg, refresh_svg, save_svg, save_gray_svg, saveas_svg, \
                    play_svg, play_grey_svg, debug_svg, debug_grey_svg, more_svg, \
                    indent_inc_svg, indent_dec_svg, check_svg, check_grey_svg, search_svg
from .pymgr_helpers import Gcm
from .utility import svg_to_bitmap
from .editor_base import *
from .fileviewbase import PanelBase, FileViewBase


class BreakpointSettingsDlg(wx.Dialog):
    def __init__(self, parent, condition='', hitcount='', curhitcount=0):
        wx.Dialog.__init__(self,
                           parent,
                           title="Breakpoint Condition",
                           size=wx.DefaultSize,
                           style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        #self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)
        szAll = wx.BoxSizer(wx.VERTICAL)
        label = ('When the breakkpoint location is reached, the expression is '
                 'evaluated, and the breakpoint is hit only if the expression '
                 'is true.')
        self.stInfo = wx.StaticText(self, label=label)
        self.stInfo.SetMaxSize((420, -1))
        self.stInfo.Wrap(420)
        szAll.Add(self.stInfo, 0, wx.ALL|wx.EXPAND, 15)

        szCnd = wx.BoxSizer(wx.HORIZONTAL)
        szCnd.Add(20, 0, 0)

        szCond = wx.BoxSizer(wx.VERTICAL)
        self.cbCond = wx.CheckBox(self, label="Is true")
        szCond.Add(self.cbCond, 0, wx.ALL | wx.EXPAND, 5)

        self.tcCond = wx.TextCtrl(self, wx.ID_ANY)
        szCond.Add(self.tcCond, 0, wx.ALL | wx.EXPAND, 5)

        label = "Hit count (hit count: #; for example, #>10"
        self.cbHitCount = wx.CheckBox(self, label=label)
        szCond.Add(self.cbHitCount, 0, wx.ALL, 5)

        self.tcHitCount = wx.TextCtrl(self, wx.ID_ANY)
        szCond.Add(self.tcHitCount, 0, wx.ALL | wx.EXPAND, 5)
        label = "Current hit count: %d" % curhitcount
        self.stHtCount = wx.StaticText(self, label=label)
        szCond.Add(self.stHtCount, 0, wx.ALL | wx.EXPAND, 5)

        szCnd.Add(szCond, 1, wx.EXPAND, 5)
        szCnd.Add(20, 0, 0)
        szAll.Add(szCnd, 0, wx.EXPAND, 5)

        self.stLine = wx.StaticLine(self, style=wx.LI_HORIZONTAL)
        szAll.Add(self.stLine, 0, wx.EXPAND | wx.ALL, 5)

        btnsizer = wx.BoxSizer(wx.HORIZONTAL)
        btnsizer.AddStretchSpacer()
        self.btnCancel = wx.Button(self, wx.ID_CANCEL)
        btnsizer.Add(self.btnCancel, 0, wx.EXPAND | wx.ALL, 5)

        self.btnOK = wx.Button(self, wx.ID_OK)
        self.btnOK.SetDefault()
        btnsizer.Add(self.btnOK, 0, wx.EXPAND | wx.ALL, 5)

        szAll.Add(btnsizer, 0, wx.EXPAND | wx.ALL, 5)

        # initialize the controls
        self.condition = condition
        self.hitcount = hitcount
        self.SetSizer(szAll)
        self.Layout()
        szAll.Fit(self)

        if self.condition == '':
            self.cbCond.SetValue(False)
            self.tcCond.Disable()
        else:
            self.cbCond.SetValue(True)
        self.tcCond.SetValue(self.condition)
        if self.hitcount == '':
            self.cbHitCount.SetValue(False)
            self.tcHitCount.Disable()
        else:
            self.cbHitCount.SetValue(True)
        self.tcHitCount.SetValue(self.hitcount)
        # Connect Events
        self.cbCond.Bind(wx.EVT_CHECKBOX, self.OnRadioButton)
        self.cbHitCount.Bind(wx.EVT_CHECKBOX, self.OnRadioButton)
        self.btnOK.Bind(wx.EVT_BUTTON, self.OnBtnOK)

    def OnRadioButton(self, event):
        self.tcCond.Enable(self.cbCond.GetValue())
        self.tcHitCount.Enable(self.cbHitCount.GetValue())
        event.Skip()

    def OnBtnOK(self, event):
        # set condition to empty string to indicate the breakpoint will be
        # trigged when the value is changed
        if self.cbCond.GetValue():
            self.condition = self.tcCond.GetValue()
        else:
            self.condition = ''
        if self.cbHitCount.GetValue():
            self.hitcount = self.tcHitCount.GetValue()
        else:
            self.hitcount = ""
        event.Skip()

    def GetCondition(self):
        return (self.condition, self.hitcount)


class PyEditor(EditorBase):
    ID_COMMENT = wx.NewIdRef()
    ID_UNCOMMENT = wx.NewIdRef()
    ID_EDIT_BREAKPOINT = wx.NewIdRef()
    ID_DELETE_BREAKPOINT = wx.NewIdRef()
    ID_CLEAR_BREAKPOINT = wx.NewIdRef()
    ID_WORD_WRAP = wx.NewIdRef()
    ID_INDENT_INC = wx.NewIdRef()
    ID_INDENT_DEC = wx.NewIdRef()
    ID_RUN_LINE = wx.NewIdRef()

    def __init__(self, parent):
        super().__init__(parent)

        self.break_point_candidate = None

        self.breakpointlist = {}

    def IsPythonScript(self):
        _, ext = os.path.splitext(self.filename)
        return ext == '.py'

    def OnMotion(self, event):
        super().OnMotion(event)
        event.Skip()

        if not self.IsPythonScript():
            return
        dc = wx.ClientDC(self)
        pos = event.GetLogicalPosition(dc)

        c, x, y = self.HitTest(pos)
        if self.break_point_candidate:
            self.MarkerDeleteHandle(self.break_point_candidate)
        if x == 0 and self.MarkerGet(y) & 2**0 == 0:
            style = self.GetStyleAt(self.XYToPosition(x, y))
            if style in [stc.STC_P_COMMENTLINE, stc.STC_P_COMMENTBLOCK]:
                return
            txt = self.GetLine(y)
            txt = txt.strip()
            if txt and txt[0] != '#':
                self.break_point_candidate = self.MarkerAdd(y, MARKER_BP_CANDIDATE)

    def ClearBreakpoint(self):
        """clear all the breakpoint"""
        for key in list(self.breakpointlist):
            ids = self.breakpointlist[key]['id']
            dp.send('debugger.clear_breakpoint', id=ids)

    def findBreakPoint(self, line):
        for key in self.breakpointlist:
            if line == self.MarkerLineFromHandle(key):
                return self.breakpointlist[key]
        return None

    def comment(self):
        """Comment section"""
        self.prepandText('##')

    def uncomment(self):
        """Uncomment section"""
        self.deprepandText('##')

    def GetContextMenu(self):
        """
            Create and return a context menu for the shell.
            This is used instead of the scintilla default menu
            in order to correctly respect our immutable buffer.
        """
        menu = super().GetContextMenu()

        menu.AppendSeparator()
        menu.Append(self.ID_COMMENT, 'Comment')
        menu.Append(self.ID_UNCOMMENT, 'Uncomment')
        menu.AppendSeparator()
        item = menu.Append(self.ID_INDENT_INC, 'Increase indent')
        if wx.Platform != '__WXMAC__':
            item.SetBitmap(svg_to_bitmap(indent_inc_svg, win=self))
        item = menu.Append(self.ID_INDENT_DEC, 'Decrease indent')
        if wx.Platform != '__WXMAC__':
            item.SetBitmap(svg_to_bitmap(indent_dec_svg, win=self))
        menu.AppendSeparator()
        if self.IsPythonScript():
            cmd = self.GetSelectedText()
            menu.Append(self.ID_RUN_LINE, 'Run selection' if cmd else 'Run current line')
            menu.AppendSeparator()
        menu.AppendCheckItem(self.ID_WORD_WRAP, 'Word wrap')
        menu.Check(self.ID_WORD_WRAP, self.GetWrapMode() != wx.stc.STC_WRAP_NONE)
        return menu

    def ToggleWrapMode(self):
        if self.GetWrapMode() == wx.stc.STC_WRAP_NONE:
            self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        else:
            self.SetWrapMode(wx.stc.STC_WRAP_NONE)

    def OnContextMenu(self, evt):
        p = self.ScreenToClient(evt.GetPosition())
        m = self.GetMarginWidth(0) + self.GetMarginWidth(1)
        if p.x > m:
            # show edit menu when the mouse is in editable area
            menu = self.GetContextMenu()
            self.PopupMenu(menu)
        elif p.x > self.GetMarginWidth(0):
            # in breakpoint area
            cline = self.LineFromPosition(self.PositionFromPoint(p))
            for key in self.breakpointlist:
                line = self.MarkerLineFromHandle(key)
                if line == cline:
                    self.GotoLine(line)
                    break
            else:
                return
            menu = wx.Menu()
            menu.Append(self.ID_DELETE_BREAKPOINT, 'Delete Breakpoint')
            menu.AppendSeparator()
            menu.Append(self.ID_EDIT_BREAKPOINT, 'Condition...')
            menu.AppendSeparator()
            menu.Append(self.ID_CLEAR_BREAKPOINT, 'Delete All Breakpoints')
            self.PopupMenu(menu)

    def SetupEditor(self):
        """
        This method carries out the work of setting up the demo editor.
        It's separate so as not to clutter up the init code.
        """
        super().SetupEditor()

        # key binding
        self.CmdKeyAssign(ord('R'), stc.STC_SCMOD_CTRL, stc.STC_CMD_REDO)
        if wx.Platform == '__WXMAC__':
            self.CmdKeyAssign(ord('R'), wx.stc.STC_SCMOD_META, wx.stc.STC_CMD_REDO)

        self.SetLexer(stc.STC_LEX_PYTHON)
        self.SetWordChars('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
        keywords = list(keyword.kwlist)
        for key in ['None', 'True', 'False']:
            if key in keywords:
                keywords.remove(key)
        self.SetKeyWords(0, ' '.join(keywords))
        self.SetKeyWords(1, ' '.join(['None', 'True', 'False']))

        # Set up the numbers in the margin for margin #1
        self.SetMarginType(NUM_MARGIN, stc.STC_MARGIN_NUMBER)
        # Reasonable value for, say, 4-5 digits using a mono font (40 pix)
        self.SetMarginWidth(0, 50)

        # Margin #1 - breakpoint symbols
        self.SetMarginType(MARK_MARGIN, stc.STC_MARGIN_SYMBOL)
        # do not show fold symbols
        self.SetMarginMask(MARK_MARGIN, ~stc.STC_MASK_FOLDERS)
        self.SetMarginSensitive(MARK_MARGIN, True)
        self.SetMarginWidth(MARK_MARGIN, 12)

        # Setup a margin to hold fold markers
        self.SetMarginType(FOLD_MARGIN, stc.STC_MARGIN_SYMBOL)
        self.SetMarginMask(FOLD_MARGIN, stc.STC_MASK_FOLDERS)
        self.SetMarginSensitive(FOLD_MARGIN, True)
        self.SetMarginWidth(FOLD_MARGIN, 12)

        self.SetCaretLineBackAlpha(64)
        self.SetCaretLineVisible(True)
        self.SetCaretLineVisibleAlways(True)

        theme = 'solarized-dark'
        resp = dp.send('frame.get_config', group='editor', key='theme')
        if resp and resp[0][1] is not None:
            theme = resp[0][1]

        self.SetupColor(theme)
        self.SetupColorPython(theme)

    def OnMarginClick(self, evt):
        """left mouse button click on margin"""
        margin = evt.GetMargin()
        ctrldown = evt.GetControl()
        # set/edit/delete a breakpoint
        if margin in [NUM_MARGIN, MARK_MARGIN]:
            lineClicked = self.LineFromPosition(evt.GetPosition())
            txt = self.GetLine(lineClicked)
            txt = txt.strip()
            if not txt or txt[0] == '#':
                return
            # check if a breakpoint marker is at this line
            bpset = self.MarkerGet(lineClicked) & 1
            bpdata = None
            resp = dp.send('debugger.get_breakpoint',
                           filename=self.filename,
                           lineno=lineClicked + 1)
            if resp:
                bpdata = resp[0][1]
            if not bpdata:
                # No breakpoint at this line, add one
                # bpdata =  {id, filename, lineno, condition, ignore_count, trigger_count}
                bp = {'filename': self.filename, 'lineno': lineClicked + 1}
                dp.send('debugger.set_breakpoint', bpdata=bp)
            else:
                if ctrldown:
                    condition = """"""
                    if bpdata['condition']:
                        condition = bpdata['condition']
                    dlg = wx.TextEntryDialog(self,
                                             caption='Breakpoint Condition:',
                                             message='Condition',
                                             defaultValue="""""",
                                             style=wx.OK)
                    if dlg.ShowModal() == wx.ID_OK:
                        dp.send('debugger.edit_breakpoint',
                                id=bpdata['id'],
                                condition=dlg.GetValue())
                else:
                    dp.send('debugger.clear_breakpoint', id=bpdata['id'])
        # fold and unfold as needed
        if evt.GetMargin() == FOLD_MARGIN:
            if evt.GetShift() and evt.GetControl():
                self.FoldAll()
            else:
                lineClicked = self.LineFromPosition(evt.GetPosition())
                level = self.GetFoldLevel(lineClicked)
                if level & stc.STC_FOLDLEVELHEADERFLAG:
                    if evt.GetShift():
                        # expand node and all subnodes
                        self.SetFoldExpanded(lineClicked, True)
                        self.Expand(lineClicked, True, True, 100, level)
                    elif evt.GetControl():
                        if self.GetFoldExpanded(lineClicked):
                            # collapse all subnodes
                            self.SetFoldExpanded(lineClicked, False)
                            self.Expand(lineClicked, False, True, 0, level)
                        else:
                            # expand all subnodes
                            self.SetFoldExpanded(lineClicked, True)
                            self.Expand(lineClicked, True, True, 100, level)
                    else:
                        self.ToggleFold(lineClicked)

    def OnMouseDwellStart(self, event):
        resp = dp.send(signal='debugger.get_status')
        if not resp or not resp[0][1]:
            return

        pos = event.GetPosition()
        if pos == -1:
            return
        wordchars = self.GetWordChars()

        # add '.' to wordchars, to detect 'a.b'
        if '.' not in wordchars:
            self.SetWordChars(wordchars + '.')
        WordStart = self.WordStartPosition(pos, True)
        WordEnd = self.WordEndPosition(pos, True)
        text = self.GetTextRange(WordStart, WordEnd)
        self.SetWordChars(wordchars)
        try:
            status = resp[0][1]
            frames = status['frames']
            level = status['active_scope']
            frame = frames[level]
            f_globals = frame.f_globals
            f_locals = frame.f_locals

            tip = pprint.pformat(eval(text, f_globals, f_locals))
            self.CallTipShow(pos, "%s = %s" % (text, tip))
        except:
            #traceback.print_exc(file=sys.stdout)
            pass

    def OnMouseDwellEnd(self, event):
        if self.CallTipActive():
            self.CallTipCancel()

    def FoldAll(self):
        """open all margin folders"""
        line_count = self.GetLineCount()
        expanding = True
        # find out if we are folding or unfolding
        for line_num in six.moves.range(line_count):
            if self.GetFoldLevel(line_num) & wx.stc.STC_FOLDLEVELHEADERFLAG:
                expanding = not self.GetFoldExpanded(line_num)
                break
        line_number = 0

        while line_number < line_count:
            level = self.GetFoldLevel(line_number)
            if level & stc.STC_FOLDLEVELHEADERFLAG and \
               (level & stc.STC_FOLDLEVELNUMBERMASK) == stc.STC_FOLDLEVELBASE:

                if expanding:
                    self.SetFoldExpanded(line_number, True)
                    line_number = self.Expand(line_number, True)
                    line_number = line_number - 1
                else:
                    lastChild = self.GetLastChild(line_number, -1)
                    self.SetFoldExpanded(line_number, False)

                    if lastChild > line_number:
                        self.HideLines(line_number + 1, lastChild)

            line_number = line_number + 1

    def Expand(self, line, do_expand, force=False, vis_levels=0, level=-1):
        """open the margin folder"""
        last_child = self.GetLastChild(line, level)
        line = line + 1

        while line <= last_child:
            if force:
                if vis_levels > 0:
                    self.ShowLines(line, line)
                else:
                    self.HideLines(line, line)
            else:
                if do_expand:
                    self.ShowLines(line, line)

            if level == -1:
                level = self.GetFoldLevel(line)

            if level & wx.stc.STC_FOLDLEVELHEADERFLAG:
                if force:
                    self.SetFoldExpanded(line, vis_levels > 1)
                    line = self.Expand(line, do_expand, force, vis_levels - 1)
                else:
                    if do_expand:
                        if self.GetFoldExpanded(line):
                            self.SetFoldExpanded(line, True)
                    line = self.Expand(line, do_expand, force, vis_levels - 1)
            else:
                line = line + 1
        return line

    def OnProcessEvent(self, evt):
        """process the menu command"""
        eid = evt.GetId()
        super().OnProcessEvent(evt)

        if eid == self.ID_COMMENT:
            self.comment()
        elif eid == self.ID_UNCOMMENT:
            self.uncomment()
        elif eid == self.ID_INDENT_INC:
            self.indented()
        elif eid == self.ID_INDENT_DEC:
            self.unindented()
        elif eid == self.ID_DELETE_BREAKPOINT:
            bp = self.findBreakPoint(self.GetCurrentLine())
            if bp:
                dp.send('debugger.clear_breakpoint', id=bp['id'])
        elif eid == self.ID_CLEAR_BREAKPOINT:
            self.ClearBreakpoint()
        elif eid == self.ID_EDIT_BREAKPOINT:
            bp = self.findBreakPoint(self.GetCurrentLine())
            if bp:
                dlg = BreakpointSettingsDlg(self,
                                            bp['condition'], bp['hitcount'],
                                            bp.get('tcount', 0))
                if dlg.ShowModal() == wx.ID_OK:
                    cond = dlg.GetCondition()
                    dp.send('debugger.edit_breakpoint',
                            id=bp['id'],
                            condition=cond[0],
                            hitcount=cond[1])
        elif eid == self.ID_WORD_WRAP:
            self.ToggleWrapMode()
        elif eid == self.ID_RUN_LINE:
            cmd = self.GetSelectedText()
            if not cmd or cmd == """""":
                (cmd, _) = self.GetCurLine()
                cmd = cmd.rstrip()
            dp.send('shell.run', command=cmd, prompt=True, verbose=True,
                    debug=False, history=False)

    def LoadFile(self, filename):
        """load file into editor"""
        self.ClearBreakpoint()
        if super().LoadFile(filename):
            digits = np.max([np.ceil(np.log10(self.GetLineCount())), 1])
            width = self.GetCharWidth() + 1
            self.SetMarginWidth(0, int(25+digits*width))
            return True
        return False

class PyEditorPanel(PanelBase):
    Gcc = Gcm()
    ID_RUN_SCRIPT = wx.NewIdRef()
    ID_DEBUG_SCRIPT = wx.NewIdRef()
    ID_CHECK_SCRIPT = wx.NewIdRef()
    ID_FIND_REPLACE = wx.NewIdRef()
    ID_SETCURFOLDER = wx.NewIdRef()
    ID_TIDY_SOURCE = wx.NewIdRef()
    ID_SPLIT_VERT = wx.NewIdRef()
    ID_SPLIT_HORZ = wx.NewIdRef()
    ID_DBG_RUN = wx.NewIdRef()
    ID_DBG_STOP = wx.NewIdRef()
    ID_DBG_STEP = wx.NewIdRef()
    ID_DBG_STEP_INTO = wx.NewIdRef()
    ID_DBG_STEP_OUT = wx.NewIdRef()
    ID_MORE = wx.NewIdRef()

    frame = None

    def init(self):

        self.splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        self.editor = PyEditor(self.splitter)
        self.editor2 = None
        self.splitter.Initialize(self.editor)
        self.Bind(stc.EVT_STC_CHANGE, self.OnCodeModified)
        item = (
            (wx.ID_OPEN, 'Open', open_svg, None, 'Open Python script'),
            (None, None, None, None, None),
            (wx.ID_REFRESH, 'Reload', refresh_svg, None, 'Reload script'),
            (wx.ID_SAVE, 'Save', save_svg, save_gray_svg, 'Save script (Ctrl+S)'),
            (wx.ID_SAVEAS, 'Save As', saveas_svg, None, 'Save script as'),
            (None, None, None, None, None),
            (self.ID_RUN_SCRIPT, 'Execute', play_svg, play_grey_svg,
             'Execute the script'),
            (None, None, None, None, None),
            (self.ID_CHECK_SCRIPT, 'Check', check_svg, check_grey_svg, 'Check the script'),
            (self.ID_DEBUG_SCRIPT, 'Debug', debug_svg, debug_grey_svg, 'Debug the script'),
            (None, None, None, None, "stretch"),
            (self.ID_MORE, 'More', more_svg, None, 'More'),
        )

        self.tb = aui.AuiToolBar(self, agwStyle=aui.AUI_TB_OVERFLOW)
        for (eid, label, img, img_gray, tooltip) in item:
            if eid is None:
                if tooltip == "stretch":
                    self.tb.AddStretchSpacer()
                else:
                    self.tb.AddSeparator()
                continue
            bmp = svg_to_bitmap(img, win=self)
            bmp_gray = wx.NullBitmap
            if img_gray:
                bmp_gray = svg_to_bitmap(img_gray, win=self)
            if label in ['Split Vert', 'Split Horz']:
                self.tb.AddCheckTool(eid, label, bmp, bmp_gray, tooltip)
            else:
                self.tb.AddTool(eid, label, bmp, bmp_gray, kind=wx.ITEM_NORMAL,
                                short_help_string=tooltip)

        self.tb.Realize()
        self.box = wx.BoxSizer(wx.VERTICAL)
        self.box.Add(self.tb, 0, wx.EXPAND, 5)
        #self.box.Add(wx.StaticLine(self), 0, wx.EXPAND)
        self.box.Add(self.splitter, 1, wx.EXPAND)
        self.box.Fit(self)
        self.SetSizer(self.box)

        # Connect Events
        self.Bind(wx.EVT_TOOL, self.OnBtnOpen, id=wx.ID_OPEN)
        self.Bind(wx.EVT_TOOL, self.OnBtnReload, id=wx.ID_REFRESH)
        self.Bind(wx.EVT_TOOL, self.OnBtnSave, id=wx.ID_SAVE)
        self.Bind(wx.EVT_TOOL, self.OnBtnSaveAs, id=wx.ID_SAVEAS)
        self.tb.Bind(wx.EVT_UPDATE_UI, self.OnUpdateBtn)
        self.Bind(wx.EVT_TOOL, self.OnShowFindReplace, id=self.ID_FIND_REPLACE)
        self.Bind(wx.EVT_TOOL, self.OnBtnCheck, id=self.ID_CHECK_SCRIPT)
        self.Bind(wx.EVT_TOOL, self.OnBtnRunScript, id=self.ID_RUN_SCRIPT)
        self.Bind(wx.EVT_TOOL, self.OnBtnDebugScript, id=self.ID_DEBUG_SCRIPT)
        #self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateBtn, id=self.ID_DEBUG_SCRIPT)
        self.Bind(wx.EVT_TOOL, self.OnSetCurFolder, id=self.ID_SETCURFOLDER)
        self.Bind(wx.EVT_MENU, self.OnSplitVert, id=self.ID_SPLIT_VERT)
        self.Bind(wx.EVT_MENU, self.OnSplitHorz, id=self.ID_SPLIT_HORZ)
        self.Bind(wx.EVT_TOOL, self.OnMore, id=self.ID_MORE)

        accel = [
            (wx.ACCEL_CTRL, ord('S'), wx.ID_SAVE),
        ]
        self.accel = wx.AcceleratorTable(accel)
        self.SetAcceleratorTable(self.accel)
        #dp.connect(self.debug_paused, 'debugger.paused')
        dp.connect(self.debug_ended, 'debugger.ended')
        dp.connect(self.debug_bpadded, 'debugger.breakpoint_added')
        dp.connect(self.debug_bpcleared, 'debugger.breakpoint_cleared')
        self.debug_curline = None

        self.was_modified = False

    @classmethod
    def get_instances(cls):
        for inst in cls.Gcc.get_all_managers():
            yield inst

    def Destroy(self):
        """destroy the panel"""
        self.editor.ClearBreakpoint()
        return super().Destroy()

    def update_bp(self):
        """update the breakpoints"""
        for key in self.editor.breakpointlist:
            line = self.editor.MarkerLineFromHandle(key) + 1
            if line != self.editor.breakpointlist[key]['lineno']:
                ids = self.editor.breakpointlist[key]['id']
                dp.send('debugger.edit_breakpoint', id=ids, lineno=line)

    def debug_bpadded(self, bpdata):
        """the breakpoint is added"""
        if bpdata is None:
            return
        info = bpdata
        filename = info['filename']
        if filename != self.editor.filename:
            return
        for key in self.editor.breakpointlist:
            if self.editor.breakpointlist[key]['id'] == bpdata['id']:
                return
        lineno = info['lineno']
        handler = self.editor.MarkerAdd(lineno - 1, MARKER_BP)
        self.editor.breakpointlist[handler] = bpdata

    def debug_bpcleared(self, bpdata):
        """the breakpoint is cleared"""
        if bpdata is None:
            return
        info = bpdata
        filename = info['filename']
        if filename != self.editor.filename:
            return
        for key in self.editor.breakpointlist:
            if self.editor.breakpointlist[key]['id'] == bpdata['id']:
                self.editor.MarkerDeleteHandle(key)
                del self.editor.breakpointlist[key]
                break

    def debug_paused(self, status):
        """the debug is paused"""
        # delete the current line marker
        if self.debug_curline:
            self.editor.MarkerDeleteHandle(self.debug_curline)
            self.debug_curline = None
        if status is None:
            return False
        filename = status['filename']

        lineno = -1
        marker = -1
        active = False
        if filename == self.editor.filename:
            lineno = status['lineno']
            marker = MARKER_BP_PAUSED_CUR
            active = True
        else:
            frames = status['frames']
            if frames is not None:
                for frame in frames:
                    filename = frame.f_code.co_filename
                    if filename == self.filename:
                        lineno = frame.f_lineno
                        marker = MARKER_BP_PAUSED
                        break
        if lineno >= 0 and marker >= 0:
            self.debug_curline = self.editor.MarkerAdd(lineno - 1, marker)
            self.editor.EnsureVisibleEnforcePolicy(lineno - 1)
            #self.JumpToLine(lineno-1)
            #self.editor.GotoLine(lineno-1)
            #self.editor.EnsureVisible(lineno-1)
            #self.editor.EnsureCaretVisible()

            if active:
                show = self.IsShown()
                parent = self.GetParent()
                while show and parent:
                    show = parent.IsShown()
                    parent = parent.GetParent()
                if not show:
                    dp.send('frame.show_panel', panel=self)
            return True
        return False

    def debug_ended(self):
        """debugging finished"""
        if self.debug_curline:
            # hide the marker
            self.editor.MarkerDeleteHandle(self.debug_curline)
            self.debug_curline = None

    def OnWrap(self, event):
        """turn on/off the wrap mode"""
        if self.editor.GetWrapMode() == stc.STC_WRAP_NONE:
            self.editor.SetWrapMode(stc.STC_WRAP_WORD)
        else:
            self.editor.SetWrapMode(stc.STC_WRAP_NONE)

    def JumpToLine(self, lineno, highlight=False):
        """jump to the line and make sure it is visible"""
        if lineno < 1:
            return
        self.editor.GotoLine(lineno-1)
        self.editor.SetFocus()
        if highlight:
            self.editor.SelectLine(lineno-1)
        wx.CallLater(1, self.editor.EnsureCaretVisible)

    def GetCaption(self):
        caption = super().GetCaption()
        if self.editor.GetModify():
            caption = caption + '*'
        return caption

    def UpdateCaption(self):
        dp.send('frame.set_panel_title', pane=self, title=self.GetCaption(),
                tooltip=self.filename, name=self.filename, icon=self.GetIcon())

    def OnCodeModified(self, event):
        """called when the file is modified"""
        if self.was_modified == self.editor.GetModify():
            return
        self.was_modified = self.editor.GetModify()
        self.UpdateCaption()

    def Load(self, filename, add_to_history=True, data=None):
        """open file"""
        self.editor.LoadFile(filename)
        self.was_modified = False

        super().Load(filename, add_to_history=add_to_history)

        theme = 'solarized-dark'
        resp = dp.send('frame.get_config', group='editor', key='theme')
        if resp and resp[0][1] is not None:
            theme = resp[0][1]
        if self.editor.IsPythonScript():
            self.editor.SetupColor(theme)
            self.editor.SetupColorPython(theme)
            if self.editor2:
                self.editor2.SetupColor(theme)
                self.editor2.SetupColorPython(theme)
        else:
            theme = 'plain-dark' if 'dark' in theme else 'plain-light'
            self.editor.SetupColor(theme)
            if self.editor2:
                self.editor2.SetupColor(theme)

    def OnBtnOpen(self, event):
        """open the script"""
        defaultDir = os.path.dirname(self.filename)
        style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        dlg = wx.FileDialog(self,
                            'Open',
                            defaultDir=defaultDir,
                            wildcard=self.GetFileType(),
                            style=style)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPaths()[0]
            self.Load(path)
        dlg.Destroy()

    def OnBtnReload(self, event):
        """reload file"""
        if self.filename:
            self.Load(self.filename)

    def saveFile(self):
        if not self.filename:
            # use top level frame as parent, otherwise it may crash when
            # it is called in Destroy()
            style = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.FD_CHANGE_DIR
            dlg = wx.FileDialog(self.GetTopLevelParent(),
                                'Save As',
                                wildcard=self.GetFileType(),
                                style=style)
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                self.filename = path
            dlg.Destroy()
        if not self.filename:
            return
        self.editor.SaveFile(self.filename)
        self.UpdateCaption()
        self.was_modified = False
        self.update_bp()

    def OnBtnSave(self, event):
        """save the script"""
        self.saveFile()

    def OnBtnSaveAs(self, event):
        """save the script with different filename"""
        defaultDir = os.path.dirname(self.filename)
        style = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT | wx.FD_CHANGE_DIR
        dlg = wx.FileDialog(self,
                            'Save As',
                            defaultDir=defaultDir,
                            wildcard=self.GetFileType(),
                            style=style)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPaths()[0]
            self.filename = path
            dlg.Destroy()
        self.editor.SaveFile(self.filename)
        self.UpdateCaption()
        self.was_modified = False
        self.update_bp()

    def OnUpdateBtn(self, event):
        """update the toolbar button status"""
        eid = event.GetId()
        if eid == wx.ID_SAVE:
            event.Enable(self.editor.GetModify())
        elif eid == self.ID_DEBUG_SCRIPT and self.editor.IsPythonScript():
            resp = dp.send('debugger.debugging')
            if resp:
                event.Enable(not resp[0][1])
        elif eid == wx.ID_REFRESH:
            event.Enable(self.filename != "")
        elif eid in [self.ID_DEBUG_SCRIPT, self.ID_CHECK_SCRIPT, self.ID_RUN_SCRIPT]:
            event.Enable(self.editor.IsPythonScript())

    def OnShowFindReplace(self, event):
        """Find and Replace dialog and action."""
        # find string
        self.editor.OnShowFindReplace(event)

    def RunCommand(self, command, prompt=False, verbose=True, debug=False):
        """run command in shell"""
        dp.send('shell.run',
                command=command,
                prompt=prompt,
                verbose=verbose,
                debug=debug,
                history=False)

    def OnBtnRun(self, event):
        """execute the selection or current line"""
        cmd = self.editor.GetSelectedText()
        if not cmd or cmd == """""":
            (cmd, _) = self.editor.GetCurLine()
            cmd = cmd.rstrip()
        self.RunCommand(cmd, prompt=True, verbose=True)

    def CheckModified(self):
        """check whether it is modified"""
        if self.editor.GetModify():
            filename = self.GetFileName()
            msg = f'"{filename}" has been modified. Save it first?'
            # use top level frame as parent, otherwise it may crash when
            # it is called in Destroy()
            parent = self.GetTopLevelParent()
            dlg = wx.MessageDialog(parent, msg, parent.GetLabel(), wx.YES_NO)
            result = dlg.ShowModal() == wx.ID_YES
            dlg.Destroy()
            if result:
                self.saveFile()
        return self.editor.GetModify()

    def CheckModifiedForClosing(self):
        """check whether it is modified"""
        allow_close = True
        if self.editor.GetModify():
            filename = self.GetFileName()
            msg = f'"{filename}" has been modified. Save it first?'
            # use top level frame as parent, otherwise it may crash when
            # it is called in Destroy()
            parent = self.GetTopLevelParent()
            dlg = wx.MessageDialog(parent, msg, parent.GetLabel(), wx.YES_NO | wx.CANCEL)
            dlg.SetExtendedMessage("Your changes will be lost if you don't save them.")
            result = dlg.ShowModal()
            dlg.Destroy()
            if result == wx.ID_YES:
                self.saveFile()
                allow_close = not self.editor.GetModify()
            elif result == wx.ID_CANCEL:
                allow_close = not self.editor.GetModify()
            else:
                # close without save
                allow_close = True

        return allow_close

    def OnBtnCheck(self, event):
        """check the syntax"""
        if self.CheckModified():
            return
        if self.filename == """""":
            return
        self.RunCommand('import sys', verbose=False)
        self.RunCommand(f'_bsm_source = open(r"{self.filename}", "r").read()+"\\n"',
                        verbose=False)
        self.RunCommand(f'compile(_bsm_source, r"{self.filename}", "exec") and print(r"Check \'{self.filename}\' successfully.")',
                        prompt=True,
                        verbose=False)
        self.RunCommand('del _bsm_source', verbose=False)

    def OnBtnRunScript(self, event):
        """execute the script"""
        if self.CheckModified():
            return
        if not self.filename:
            return
        self.RunCommand('import six', verbose=False)
        cmd = "compile(open(r'{0}', 'rb').read(), r'{0}', 'exec')".format(
            self.filename)
        self.RunCommand('six.exec_(%s)' % cmd,
                        prompt=True,
                        verbose=False,
                        debug=False)

    def OnBtnDebugScript(self, event):
        """execute the script in debug mode"""
        if self.CheckModified():
            return
        if not self.filename:
            return
        self.RunCommand('import six', verbose=False)
        # disable the debugger button
        self.tb.EnableTool(self.ID_DEBUG_SCRIPT, False)

        cmd = "compile(open(r'{0}', 'rb').read(), r'{0}', 'exec')".format(
            self.filename)
        self.RunCommand('six.exec_(%s)' % cmd,
                        prompt=True,
                        verbose=False,
                        debug=True)

        #dp.send('debugger.ended')
        self.tb.EnableTool(self.ID_DEBUG_SCRIPT, True)

    def OnSetCurFolder(self, event):
        """set the current folder to the folder with the file"""
        if not self.filename:
            return
        path, _ = os.path.split(self.filename)
        self.RunCommand('import os', verbose=False)
        self.RunCommand('os.chdir(r\'%s\')' % path, verbose=False)

    def OnSplitVert(self, event):
        """show splitter window vertically"""
        show = not (self.splitter.IsSplit() and
                    self.splitter.GetSplitMode() == wx.SPLIT_VERTICAL)
        if not show:
            # hide the splitter window
            if self.editor2:
                if self.splitter.IsSplit():
                    self.splitter.Unsplit(self.editor2)
                self.editor2.Hide()
        else:
            # show splitter window
            if not self.editor2:
                # create the splitter window
                self.editor2 = PyEditor(self.splitter)
                self.editor2.SetDocPointer(self.editor.GetDocPointer())
            if self.editor2:
                if self.splitter.IsSplit():
                    self.splitter.Unsplit(self.editor2)
                self.splitter.SplitVertically(self.editor, self.editor2)
                self.editor2.filename = self.editor.filename

    def OnSplitHorz(self, event):
        """show splitter window horizontally"""
        show = not (self.splitter.IsSplit() and
                    self.splitter.GetSplitMode() == wx.SPLIT_HORIZONTAL)
        if not show:
            # hide the splitter window
            if self.editor2:
                if self.splitter.IsSplit():
                    self.splitter.Unsplit(self.editor2)
                self.editor2.Hide()
        else:
            # show splitter window
            if not self.editor2:
                # create the splitter window
                self.editor2 = PyEditor(self.splitter)
                self.editor2.SetDocPointer(self.editor.GetDocPointer())
            if self.editor2:
                if self.splitter.IsSplit():
                    self.splitter.Unsplit(self.editor2)
                self.splitter.SplitHorizontally(self.editor, self.editor2)
                self.editor2.filename = self.editor.filename

    def OnMore(self, event):
        menu = wx.Menu()
        menu.Append(self.ID_SETCURFOLDER, "Set as current folder")
        menu.AppendSeparator()
        item = menu.AppendCheckItem(self.ID_SPLIT_VERT, "Split editor right")
        item.Check(self.splitter.IsSplit() and
                   (self.splitter.GetSplitMode() == wx.SPLIT_VERTICAL))
        item = menu.AppendCheckItem(self.ID_SPLIT_HORZ, "Split editor down")
        item.Check(self.splitter.IsSplit() and
                   (self.splitter.GetSplitMode() == wx.SPLIT_HORIZONTAL))

        # line up our menu with the button
        tb = event.GetEventObject()
        tb.SetToolSticky(event.GetId(), True)
        rect = tb.GetToolRect(event.GetId())
        pt = tb.ClientToScreen(rect.GetBottomLeft())
        pt = self.ScreenToClient(pt)
        self.PopupMenu(menu)

        # make sure the button is "un-stuck"
        tb.SetToolSticky(event.GetId(), False)


    @classmethod
    def GetFileType(cls):
        return 'Python source (*.py)|*.py|Text (*.txt)|*.txt|All files (*.*)|*.*'


class Editor(FileViewBase):
    name = 'python'
    panel_type = PyEditorPanel
    target_pane = None

    ID_NEW = wx.NOT_FOUND

    @classmethod
    def ignore_file_ext(cls):
        return []

    @classmethod
    def check_filename(cls, filename):
        if filename is None:
            return True

        _, ext = os.path.splitext(filename)
        if ext in cls.ignore_file_ext():
            return False

        try:
            with open(filename, 'tr') as check_file:  # try open file in text mode
                check_file.read()
                return True
        except:  # if fail then file is non-text (binary)
            return False

        return (ext.lower() in ['.py', '.txt'])

    @classmethod
    def initialize(cls, frame, **kwargs):
        """initialize the module"""
        if cls.frame:
            # if it has already initialized, simply return
            return

        super().initialize(frame, **kwargs)

        dp.connect(cls.OnFrameClosing, 'frame.closing')
        dp.connect(cls.DebugPaused, 'debugger.paused')
        dp.connect(cls.DebugUpdateScope, 'debugger.update_scopes')
        dp.connect(cls.setting_theme_font, 'editor.theme.font')
        dp.connect(cls.setting_theme_color, 'editor.theme.color')
        dp.connect(cls.OnPerspectiveLoaded, 'frame.perspective_loaded')

    @classmethod
    def OnPerspectiveLoaded(cls):
        for panel in cls.panel_type.Gcc.get_all_managers():
            # update the panel caption, as it maybe changed by the perspective
            # for example, when close the app, the file 'a.py' is modified but
            # closed without saving, then its caption will be 'a.py*' in
            # perspective.
            panel.UpdateCaption()


    @classmethod
    def setting_theme_font(cls, **kwargs):
        resp = dp.send('frame.get_config', group='theme')
        if resp is None or resp[0][1] is None:
            return
        themes = resp[0][1]
        for k in kwargs:
            for t in themes:
                if 'font' in themes[t]:
                    if wx.Platform in themes[t]['font'] and k in themes[t]['font'][wx.Platform]:
                        themes[t]['font'][wx.Platform][k] = kwargs[k]
                    elif 'default' in themes[t]['font'] and k in themes[t]['font']['default']:
                        themes[t]['font']['default'][k] = kwargs[k]


        dp.send('frame.set_config', group='theme', **themes)

    @classmethod
    def setting_theme_color(cls, **kwargs):
        resp = dp.send('frame.get_config', group='theme')
        if resp is None or resp[0][1] is None:
            return
        themes = resp[0][1]
        for k in kwargs:
            for t in themes:
                if 'color' in themes[t] and k in themes[t]['color']:
                    themes[t]['color'][k] = kwargs[k]

        dp.send('frame.set_config', group='theme', **themes)

    @classmethod
    def get_menu(cls):
        menu = [['open', 'File:Open:Python script'],
                ['new', 'File:New:Python script\tCtrl+N']]
        return menu

    @classmethod
    def initialized(cls):
        resp = dp.send('frame.get_config', group='editor', key='opened')
        if resp and resp[0][1]:
            files = resp[0][1]
            if len(files[0]) == 2:
                files = [ f+[False] for f in files]
            for f, lineno, shown in files:
                editor = cls.open(f, add_to_history=False)
                if editor:
                    if lineno > 0:
                        editor.JumpToLine(lineno)

    @classmethod
    def uninitializing(cls):
        return

    @classmethod
    def uninitialized(cls):
        """unload the module"""
        files = []
        for panel in cls.panel_type.Gcc.get_all_managers():
            editor = panel.editor
            files.append([editor.filename, editor.GetCurrentLine(), panel.IsShownOnScreen()])

        dp.send('frame.set_config', group='editor', opened=files)

        dp.disconnect(cls.OnFrameClosing, 'frame.closing')
        dp.disconnect(cls.DebugPaused, 'debugger.paused')
        dp.disconnect(cls.DebugUpdateScope, 'debugger.update_scopes')
        # delete all editors
        super().uninitialized()

    @classmethod
    def findEditorByFileName(cls, filename):
        """
        find the editor by filename

        If the file is opened in multiple editors, return the first one.
        """
        for editor in PyEditorPanel.get_instances():
            if str(editor.editor.filename).lower() == filename.lower():
                return editor
        return None

    @classmethod
    def OpenScript(cls, filename, activated=True, lineno=0, add_to_history=True):
        """open the file"""
        if not filename:
            return None
        (_, fileExtension) = os.path.splitext(filename)
        if fileExtension.lower() != '.py':
            return None

        editor = cls.findEditorByFileName(filename)
        if editor is None:
            editor = cls.open(filename=filename, add_to_history=add_to_history)

        if editor and activated and not editor.IsShownOnScreen():
            dp.send('frame.show_panel', panel=editor, focus=True)
        if lineno > 0:
            editor.JumpToLine(lineno)
        return editor

    @classmethod
    def get(cls, num=None, filename=None, data_only=True):
        manager = cls.get_manager(num, filename)
        if num is None and filename is None and manager is None:
            manager = cls.panel_type.get_active()
        text = None
        if manager:
            text = manager.editor.GetText()
        elif filename:
            try:
                with open(filename, 'r') as fp:
                    text = fp.readlines()
            except:
                traceback.print_exc(file=sys.stdout)
        return text

    @classmethod
    def process_command(cls, command):
        """process the menu command"""
        if command == cls.IDS.get('new', None):
            cls.open()
        else :
            super().process_command(command)

    @classmethod
    def OnFrameClosePane(cls, event):
        """closing a pane"""
        pane = event.GetPane().window
        if isinstance(pane, aui.auibook.AuiNotebook):
            for i in range(pane.GetPageCount()):
                page = pane.GetPage(i)
                if isinstance(page, PyEditorPanel):
                    if not page.CheckModifiedForClosing() and page.filename is not None:
                        # the file has been modified, stop closing
                        event.Veto()
        elif isinstance(pane, PyEditorPanel):
            if not pane.CheckModifiedForClosing() and pane.filename is not None:
                # the file has been modified, stop closing
                event.Veto()

    @classmethod
    def OnFrameClosing(cls, event):
        """the frame is exiting"""
        for panel in cls.panel_type.get_all_managers():
            if not panel.CheckModifiedForClosing():
                # the file has been modified, stop closing
                event.Veto()
                break

    @classmethod
    def DebugPaused(cls):
        """the debugger has paused, update the editor margin marker"""
        resp = dp.send('debugger.get_status')
        if not resp or not resp[0][1]:
            return
        status = resp[0][1]
        filename = status['filename']
        # open the file if necessary
        editor = cls.OpenScript(filename)
        if editor:
            editor.debug_paused(status)
        for editor2 in PyEditorPanel.get_instances():
            if editor != editor2:
                editor2.debug_paused(status)

    @classmethod
    def DebugUpdateScope(cls):
        """
        the debugger scope has been changed, update the editor margin marker
        """
        resp = dp.send('debugger.get_status')
        if not resp or not resp[0][1]:
            return
        status = resp[0][1]
        for editor in PyEditorPanel.get_instances():
            editor.debug_paused(status)

