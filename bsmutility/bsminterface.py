import wx
import wx.py.dispatcher as dp

class Interface:
    frame = None

    @classmethod
    def initialize(cls, frame, **kwargs):
        if cls.frame is not None:
            # already initialized
            return
        cls.frame = frame

        dp.connect(receiver=cls.initialized, signal='frame.initialized')
        dp.connect(receiver=cls.uninitializing, signal='frame.exiting')
        dp.connect(receiver=cls.uninitialized, signal='frame.exit')

    @classmethod
    def initialized(cls):
        # add interface to the shell
        pass

    @classmethod
    def uninitializing(cls):
        # before save perspective
        pass

    @classmethod
    def uninitialized(cls):
        # after save perspective
        dp.disconnect(receiver=cls.initialized, signal='frame.initialized')
        dp.disconnect(receiver=cls.uninitializing, signal='frame.exiting')
        dp.disconnect(receiver=cls.uninitialized, signal='frame.exit')


class InterfaceRename(Interface):
    ID_PANE_RENAME = wx.NewIdRef()

    @classmethod
    def RenamePane(cls, pane):
        if not pane:
            return
        name = pane.caption
        name_new = wx.GetTextFromUser("Enter the new name:", "Input Name", name,
                                  cls.frame)
        # if user click 'cancel', name will be empty, ignore it.
        if name_new and name_new != name:
            dp.send('frame.set_panel_title', pane=pane.window, title=name_new)
