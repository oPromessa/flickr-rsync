from __future__ import print_function
import time
import random
from storage import Storage
from file_info import FileInfo
from folder_info import FolderInfo

class FakeStorage(Storage):

    def __init__(self, config):
        self._config = config

    def list_folders(self):
        folder_count = 5
        for i in range(folder_count):
            name = '{} Folder'.format(self._get_char(i, folder_count))
            yield self._intense_calculation(FolderInfo(id=i, name=name))

    def list_files(self, folder):
        file_count = 5
        for i in range(file_count):
            name = '{} File'.format(self._get_char(i, file_count))
            yield self._intense_calculation(FileInfo(id=i, name=name))

    def _get_char(self, num, max_num):
        return str(unichr((64 + max_num) - num))

    def _intense_calculation(self, value):
        # sleep for a random short duration between 0.5 to 2.0 seconds to simulate a long-running calculation
        time.sleep(random.randint(1, 2) * .1)
        return value


