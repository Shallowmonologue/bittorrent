import time
import os
from threading import Lock
from threading import Thread

from Torrent import Torrent
from TorrentMetainfo import TorrentMetainfo


class Client:
    max_name_len = 28

    def __init__(self, path):
        self.is_available = True
        self.print_lock = Lock()
        self.torrent_name = path
        metainfo = TorrentMetainfo(path)
        self.torrent = Torrent(metainfo)

    @staticmethod
    # 进度条清屏
    def cls():
        os.system('cls' if os.name == 'nt' else 'clear')

    # 多线程并发
    def run(self):
        t1 = Thread(target=self.print_torrents_table_always,
                    args=(), daemon=True)
        t2 = Thread(target=self.torrent.run_download,
                    args=(), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    # 设定下载进度条格式
    def print_torrents_table_always(self):
        while True:
            time.sleep(.5)
            with self.print_lock:
                self.cls()
                print(self.get_torrents_table())

    def get_torrents_table(self):
        res = ['Name                         | '
               'Progress | Peers | Speed', '']

        cur_res = []
        full_torr_name = os.path.basename(self.torrent_name)
        short_torr_name = full_torr_name[:self.max_name_len]
        cur_res.append('{:<{max_len}}'.format(short_torr_name,
                                              max_len=self.max_name_len))
        torrent = self.torrent
        cur_progress = '{:.2%}'.format(torrent.progress)
        cur_peers_count = len(torrent.peers)
        cur_speed = torrent.download_speed
        cur_res.append('{:<8}'.format(cur_progress))
        cur_res.append('{:<5}'.format(cur_peers_count))
        cur_res.append('{:<11}'.format(cur_speed))
        res.append(' | '.join(cur_res))

        return '\n'.join(res)
