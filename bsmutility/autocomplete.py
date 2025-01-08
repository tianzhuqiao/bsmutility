# -*- coding: utf-8 -*-
__license__ = """Copyright (c) 2008-2010, Toni Ruža, All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice,
  this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 'AS IS'
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE."""

__author__ = u"Toni Ruža <gmr.gaf@gmail.com>"
__url__ = "http://bitbucket.org/raz/wxautocompletectrl"

import six
import wx
import wx.html


class SuggestionsPopup(wx.PopupTransientWindow):
    def __init__(self, parent):
        super().__init__(parent)
        self._suggestions = self._listbox(self)
        self._suggestions.SetItemCount(0)
        self._unformated_suggestions = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._suggestions, 1, wx.ALL|wx.EXPAND, 0)
        self.SetSizer(sizer)

    class _listbox(wx.html.HtmlListBox):
        items = None

        def OnGetItem(self, n):
            return self.items[n]

        def OnDrawSeparator(self, dc, rect, n):
            pass

        def OnDrawBackground(self, dc, rect, n):
            sel_bk_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            alt_row_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DFACE)
            pen_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_3DLIGHT)
            if self.IsCurrent(n):
                dc.SetBrush(wx.Brush(sel_bk_colour))
                dc.SetPen(wx.TRANSPARENT_PEN)
                dc.DrawRectangle(rect)
            elif n%2 == 0:
                dc.SetBrush(wx.Brush(alt_row_colour))
                dc.SetPen(wx.Pen(pen_colour))
                dc.DrawRectangle(rect)

    def SetSuggestions(self, suggestions, unformated_suggestions):
        self._suggestions.items = suggestions
        self._suggestions.SetItemCount(len(suggestions))
        self._suggestions.SetSelection(0)
        self._suggestions.Refresh()
        self._unformated_suggestions = unformated_suggestions

    def CursorUp(self):
        selection = self._suggestions.GetSelection()
        if selection > 0:
            self._suggestions.SetSelection(selection - 1)

    def CursorDown(self):
        selection = self._suggestions.GetSelection()
        last = self._suggestions.GetItemCount() - 1
        if selection < last:
            self._suggestions.SetSelection(selection + 1)

    def CursorHome(self):
        if self.IsShown():
            self._suggestions.SetSelection(0)

    def CursorEnd(self):
        if self.IsShown():
            self._suggestions.SetSelection(self._suggestions.GetItemCount() - 1)

    def GetSelectedSuggestion(self):
        return self._unformated_suggestions[self._suggestions.GetSelection()]

    def GetSuggestion(self, n):
        return self._unformated_suggestions[n]

    def HasSuggstion(self):
        return self._unformated_suggestions is not None and len(self._unformated_suggestions) > 0

class AutocompleteMixin():

    def __init__(self, height=300, frequency=250, value="", completer=None):
        self.completer = None
        self.queued_popup = False
        self.skip_event = False
        self._string = value
        self.height = height
        self.frequency = frequency
        if completer:
            self.set_completer(completer)

    def set_completer(self, completer):
        """
        Initializes the autocompletion. The 'completer' has to be a function
        with one argument (the current value of the control, i.e. the query)
        and it has to return two lists: formatted (html) and unformatted
        suggestions.
        """
        self.completer = completer

        self.popup = SuggestionsPopup(self.GetTopLevelParent())

        self.Bind(wx.EVT_TEXT, self.OnTextUpdate)
        self.Bind(wx.EVT_SIZE, self.OnSizeChange)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.popup._suggestions.Bind(wx.EVT_LEFT_DOWN,
                                     self.OnSuggestionClicked)
        self.popup._suggestions.Bind(wx.EVT_KEY_DOWN, self.OnSuggestionKeyDown)

    def adjust_popup_position(self):
        self.popup.SetPosition(self.ClientToScreen((0, self.GetSize().GetHeight())).Get())

    def OnTextUpdate(self, event):
        # only show the popup when the text has changed; so type in 'Enter'
        # will not bring the popup
        if event.GetString() != self._string:
            self._string = event.GetString()
            if self.skip_event:
                self.skip_event = False
            elif not self.queued_popup:
                if wx.Platform != '__WXGTK__':
                    if self.IsShownOnScreen():
                        wx.CallLater(self.frequency, self.auto_complete)
                        self.queued_popup = True
        event.Skip()

    def auto_complete(self, *args, **kwargs):
        self.queued_popup = False
        if self.Value != "" and self.IsShownOnScreen():
            self.show_popup()
        else:
            self.hide_popup()

    def OnSizeChange(self, event):
        self.hide_popup()
        self.popup.SetSize(self.GetSize()[0], self.height)
        event.Skip()

    def OnKeyDown(self, event):
        key = event.GetKeyCode()

        if key == wx.WXK_UP:
            self.popup.CursorUp()
            return

        elif key == wx.WXK_DOWN:
            self.popup.CursorDown()
            return

        elif key == wx.WXK_TAB:
            if not self.popup.IsShownOnScreen():
                self.show_popup()
                return

        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and self.popup.Shown:
            self.skip_event = True
            txt = self.popup.GetSelectedSuggestion()
            self.apply_suggestion(txt)
            self.hide_popup()
            event.Skip()
            return

        elif key == wx.WXK_HOME:
            self.popup.CursorHome()

        elif key == wx.WXK_END:
            self.popup.CursorEnd()

        elif event.ControlDown() and six.unichr(key).lower() == "a":
            self.SelectAll()

        elif key == wx.WXK_ESCAPE:
            self.hide_popup()
            return

        event.Skip()

    def apply_suggestion(self, text):
        start = end = self.GetLastPosition()
        if self.auto_comp_offset:
            start -= self.auto_comp_offset
        self.Replace(start, end, text)
        self.SetInsertionPointEnd()

    def OnSuggestionClicked(self, event):
        self.skip_event = True
        #n = event.GetInt()
        n = self.popup._suggestions.VirtualHitTest(event.Position.y)
        text = self.popup.GetSuggestion(n)
        self.apply_suggestion(text)
        self.hide_popup()
        wx.CallAfter(self.SetFocus)
        event.Skip()

    def OnSuggestionKeyDown(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.skip_event = True
            self.apply_suggestion(self.popup.GetSelectedSuggestion())
            self.hide_popup()
        elif key == wx.WXK_ESCAPE:
            self.hide_popup()
        event.Skip()

    def show_popup(self, show=True):
        if not show:
            if self.popup.IsShownOnScreen():
                self.popup.Dismiss()
        else:
            formated, unformated, offset = self.completer(self.Value)
            if formated:
                self.auto_comp_offset = offset
                self.popup.SetSuggestions(formated, unformated)
                self.adjust_popup_position()

                if not self.popup.IsShownOnScreen():
                    self.popup.Popup()
            else:
                self.popup.Dismiss()

    def hide_popup(self):
        self.show_popup(show=False)

class AutocompleteTextCtrl(wx.TextCtrl, AutocompleteMixin):
    def __init__(self,
                 parent,
                 height=300,
                 completer=None,
                 multiline=False,
                 frequency=250,
                 value=""):
        style = wx.TE_PROCESS_ENTER
        if multiline:
            style = style | wx.TE_MULTILINE
        wx.TextCtrl.__init__(self, parent, value=value, style=style)
        AutocompleteMixin.__init__(self, height, frequency, value, completer)


class AutocompleteComboBox(wx.ComboBox, AutocompleteMixin):
    def __init__(self,
                 parent,
                 height=300,
                 completer=None,
                 frequency=250,
                 value="",
                 style=wx.TE_PROCESS_ENTER):
        wx.ComboBox.__init__(self, parent, value=value, style=style)
        AutocompleteMixin.__init__(self, height, frequency, value, completer)

    def auto_complete(self, *args, **kwargs):
        super().auto_complete(*args, **kwargs)
        if self.popup.IsShownOnScreen():
            self.SetInsertionPointEnd()
