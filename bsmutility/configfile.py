import os
import json
from pathlib import Path
import wx

class MultiDimensionalArrayEncoder(json.JSONEncoder):
    def encode(self, o):
        def hint_tuples(item):
            if isinstance(item, tuple):
                return {'__tuple__': True, 'items': item}
            if isinstance(item, list):
                return [hint_tuples(e) for e in item]
            if isinstance(item, dict):
                return {key: hint_tuples(value) for key, value in item.items()}
            else:
                return item

        return super().encode(hint_tuples(o))

def hinted_tuple_hook(obj):
    if '__tuple__' in obj:
        return tuple(obj['items'])
    else:
        return obj


class ConfigFile:
    def __init__(self, filename, foler='bsmutility'):
        # create folder
        s = wx.StandardPaths.Get()
        cfg = os.path.join(s.GetUserConfigDir(), foler)
        Path(cfg).mkdir(parents=True, exist_ok=True)

        self.config = wx.FileConfig(localFilename=os.path.join(cfg, filename))

    def SetConfig(self, group, flush=True, **kwargs):
        if not group.startswith('/'):
            group = '/' + group
        for key, value in kwargs.items():
            if not isinstance(value, str):
                # add sign to indicate that the value needs to be deserialize
                enc = MultiDimensionalArrayEncoder()
                value = '__bsm__' + enc.encode(value)
            self.config.SetPath(group)
            self.config.Write(key, value)
        if flush:
            self.Flush()

    def GetConfig(self, group, key=None):
        if not group.startswith('/'):
            group = '/' + group
        if self.config.HasGroup(group):
            self.config.SetPath(group)
            if key is None:
                rst = {}
                more, k, index = self.config.GetFirstEntry()
                while more:
                    value = self.config.Read(k)
                    if value.startswith('__bsm__'):
                        value = json.loads(value[7:], object_hook=hinted_tuple_hook)
                    rst[k] = value
                    more, k, index = self.config.GetNextEntry(index)
                return rst

            if self.config.HasEntry(key):
                value = self.config.Read(key)
                if value.startswith('__bsm__'):
                    value = json.loads(value[7:], object_hook=hinted_tuple_hook)
                return value
        return None

    def Flush(self):
        self.config.Flush()
