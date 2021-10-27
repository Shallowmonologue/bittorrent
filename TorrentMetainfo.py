import hashlib
import os
import bencodepy


class TorrentMetainfo:
    def __init__(self, filename):
        self.info_hash = None
        self.info_hash2str = None
        self.name = None
        self.length = None
        self.announce_list = []
        self.piece_length = None
        self.pieces = None
        self.is_single_file = True
        self.files = None
        self._parse_torrent_file(filename)

    def __str__(self):
        res = f"info_hash: {self.info_hash2str}\n" \
              f"name: {self.name}\n" \
              f"announce-list: {self.announce_list}\n" \
              f"length: {self.length}\n" \
              f"piece_length: {self.piece_length}\n" \
              f"is_single_file: {self.is_single_file}\n" \
              f"files:\n"
        for file in self.files:
            res += str(file) + "\n"
        return res

    def _parse_torrent_file(self, filename):
        if not TorrentMetainfo.is_valid_torrent_file(filename):
            return
        # read and decode bencoded file
        meta_info = bencodepy.bread(open(filename, 'rb'))
        # get the info
        info = bencodepy.encode(meta_info[b"info"])
        # compute sha1 hash of info
        sha1_hash = hashlib.sha1(info)
        # store the info hash
        self.info_hash = sha1_hash.digest()
        self.info_hash2str = sha1_hash.hexdigest()
        # update announce_list from meta_info
        self.announce_list.append(meta_info[b'announce'].decode())
        # in case has announce-list
        if b'announce-list' in meta_info:
            self._add_announces(meta_info[b'announce-list'])
        self._decode_info(meta_info[b'info'])

    @staticmethod
    def is_valid_torrent_file(filename):
        # check if the given file is a valid torrent file
        try:
            if not os.path.isfile(filename):
                raise RuntimeError(f"Exception: \"{filename}\" doesn't exist.")

            elif not filename.endswith(".torrent"):
                raise RuntimeError(f"Exception: \"{filename}\" is not a valid torrent file.")
        except RuntimeError as e:
            return False

        return True

    def _add_announces(self, announces):
        # get all announces from announce-list and add to announce_list
        for cur_ann_list in announces:
            for bin_announce in cur_ann_list:
                str_announce = bin_announce.decode()
                # ensure that the current announce is not same as the base announce
                if self.announce_list[0] != str_announce:
                    self.announce_list.append(str_announce)

    def _decode_info(self, meta_info):
        # set name from the meta_info
        self.name = meta_info[b'name'].decode()
        # set piece_length
        self.piece_length = meta_info[b"piece length"]
        # get the pieces and slice into 20-byte pieces
        pieces = meta_info[b'pieces']
        self.pieces = [pieces[i:i + 20] for i in range(0, len(pieces), 20)]

        # in case torrent has multiple files
        if b'files' in meta_info:
            # disable single file
            self.is_single_file = False
            # list of files in the torrent
            self.files = []
            # traverse all the files in the torrent
            '''
            files: list of dictionaries like:
            [
                {length: <length of file in integer>, path: <path of the file>},
                ...
            ]
            '''
            for file in meta_info[b'files']:
                # create a list of all relative paths of the file
                path_segments = [v.decode('utf-8') for v in file[b'path']]
                # update the file length and the path
                self.files.append({
                    'length': file[b'length'],
                    'path': os.path.join(*path_segments)
                })
            # set the length as the sum of all files in the torrent
            self.length = sum(file['length'] for file in self.files)
        else:
            # if this is a single file torrent
            self.length = meta_info[b'length']
