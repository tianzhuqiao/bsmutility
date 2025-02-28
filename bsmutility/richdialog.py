import wx

class RichNumberEntryDialog(wx.Dialog):

    def __init__(self, parent, message, prompt, checkText, caption, value, min, max, pos=wx.DefaultPosition):
        super().__init__(parent, title=caption, pos=pos)

        sizeAll = wx.BoxSizer(wx.VERTICAL)
        sizeAll.Add(self.CreateTextSizer(message), wx.SizerFlags().DoubleBorder())

        inputSizer = wx.BoxSizer(wx.HORIZONTAL)
        inputSizer.Add(self.CreateTextSizer(prompt), wx.SizerFlags().Center().DoubleBorder(wx.LEFT))
        self.spinctrl = wx.SpinCtrl(self, value=f"{value}", min=min, max=max, initial=value)
        inputSizer.Add(self.spinctrl, wx.SizerFlags(1).Center().DoubleBorder(wx.LEFT | wx.RIGHT))

        sizeAll.Add(inputSizer, wx.SizerFlags().Expand().Border(wx.LEFT | wx.RIGHT))
        self.checkbox = wx.CheckBox(self, label=checkText)
        sizeAll.Add(self.checkbox, wx.SizerFlags().Expand().DoubleBorder(wx.LEFT | wx.RIGHT | wx.TOP))

        sizeAll.Add(self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL),
                    wx.SizerFlags().Expand().DoubleBorder())

        self.SetSizer(sizeAll)

        sizeAll.SetSizeHints(self)

        self.Centre(wx.BOTH)

        self.spinctrl.SetSelection(-1, -1)
        self.spinctrl.SetFocus()

    def GetValue(self):
        return self.spinctrl.GetValue()

    def IsCheckBoxChecked(self):
        return self.checkbox.GetValue()


