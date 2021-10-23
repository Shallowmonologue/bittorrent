# Step 1: Parse the torrent file

from collections import namedtuple
import bencodepy
import os
from hashlib import sha1

TorrentFile = namedtuple('TorrentFile', ['name', 'length'])


class Torrent:
    def __init__(self, torrent_file_path):
        self.torrent_file_path = torrent_file_path

        if self.is_valid_torrent_file():
            # parse the entire torrent file
            self.meta_info = bencodepy.bread(self.torrent_file_path)
            # get SHA-1 hash of the info
            info = bencodepy.encode(self.meta_info[b"info"])
            self.info_hash = sha1(info).digest()
            # get the details of the file in the torrent
            self.file = self.get_torrent_file()

    def __str__(self):
        return f'Filename: {self.file.name}\n' \
               f'File length: {self.total_length}\n' \
               f'Announce URL: {self.announce}\n' \
               f'Hash: {self.info_hash}'

    def is_valid_torrent_file(self):
        """
        Checks if the given file is a valid torrent file.
        """
        try:
            if not os.path.isfile(self.torrent_file_path):
                raise RuntimeError(f"Exception: \"{self.torrent_file_path}\" doesn't exist.")

            elif not self.torrent_file_path.endswith(".torrent"):
                raise RuntimeError(f"Exception: \"{self.torrent_file_path}\" is not a valid torrent file.")
        except RuntimeError as e:
            print(e)
            return False

        return True

    def get_torrent_file(self):
        """
        Returns the file present in the torrent.
        """
        if self.is_multi_file_torrent:
            raise RuntimeError("Torrent contains multiple files.")

        return TorrentFile(
            name=self.meta_info[b"info"][b"name"].decode("utf-8"),
            length=self.meta_info[b"info"][b"length"])

    @property
    def is_multi_file_torrent(self):
        """
        Checks if this is a multi-file torrent or not.
        """
        return b"files" in self.meta_info[b"info"]

    @property
    def announce(self):
        """
        Returns the tracker URL.
        """
        return self.meta_info[b"announce"].decode("utf-8")

    @property
    def piece_length(self):
        """
        Returns length of each piece in bytes.
        """
        return self.meta_info[b"info"][b"piece length"]

    @property
    def total_length(self):
        """
        Returns the total size of file in bytes.
        """
        if self.is_multi_file_torrent:
            raise RuntimeError("Torrent contains multiple files.")
        return self.file.length

    @property
    def pieces(self):
        """
        Returns a list containing the SHA1 (each 20 bytes long) of all the pieces.
        """
        data = self.meta_info[b"info"][b"pieces"]
        pieces, offset, length = [], 0, len(data)
        pieces = [data[offset:offset+20] for offset in range(0, length, 20)]
        return pieces

