import hashlib
import os
import Bencode


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

    def get_piece_len_at(self, piece_idx):
        """
        获取给定piece的长度
        :param piece_idx: piece索引
        :return: piece长度
        """
        return (self.piece_length if piece_idx < len(self.pieces) - 1
                else self.length - (len(self.pieces) - 1) * self.piece_length)

    def _parse_torrent_file(self, filename):
        """
        解析torrent文件并初始化metainfo.
        :param filename: 文件名
        :return: None
        """
        # 读取并解码bencode
        meta_info = Bencode.readfile(open(filename,'rb'))
        # 获取info
        info = Bencode.encode(meta_info[b"info"])
        # 计算info的哈希值
        sha1_hash = hashlib.sha1(info)
        # 储存info的哈希值
        self.info_hash = sha1_hash.digest()
        self.info_hash2str = sha1_hash.hexdigest()
        # 获取并更新announce_list
        self.announce_list.append(meta_info[b'announce'].decode())
        # 如果metainfo中存在多个announce, 则逐个添加announce
        if b'announce-list' in meta_info:
            self._add_announces(meta_info[b'announce-list'])
        self._decode_info(meta_info[b'info'])

    def _add_announces(self, announces):
        """
        添加新的announce至announce-list
        :param announces: torrent文件中的announces-list
        :return: None
        """
        # 获取announce-list中所有的并完成添加
        for cur_ann_list in announces:
            for bin_announce in cur_ann_list:
                str_announce = bin_announce.decode()
                # 避免重复添加相同的announce
                if self.announce_list[0] != str_announce:
                    self.announce_list.append(str_announce)

    def _decode_info(self, meta_info):
        """
        对meatainfo解码并初始化bitfields
        :param meta_info: metainfo
        :return: None
        """
        # 设定待下载的文件名
        self.name = meta_info[b'name'].decode()
        # 设定piece长度
        self.piece_length = meta_info[b"piece length"]
        # 依照每个pieces20字节长度进行切片
        pieces = meta_info[b'pieces']
        self.pieces = [pieces[i:i + 20] for i in range(0, len(pieces), 20)]

        # 如果该torrent文件拥有多个文件
        if b'files' in meta_info:
            # 改变is_single_file的bool值
            self.is_single_file = False
            # 设定文件list
            self.files = []
            '''
            遍历torrent中所有文件, 并使用dict类型储存:
            [
                {length: <length of file in integer>, path: [path_seg1, path_seg2, ..., path_segn, filename.ext]},
                ...
            ]
            '''
            for file in meta_info[b'files']:
                # 创建多文件的总路径
                path_segments = [v.decode('utf-8') for v in file[b'path']]
                # 更新多文件长度与路径
                self.files.append({
                    'length': file[b'length'],
                    'path': os.path.join(*path_segments)
                })
            # 设定所有文件的总长度和
            self.length = sum(file['length'] for file in self.files)
        else:
            # 若为单个文件, 则仅设定其文件长度
            self.length = meta_info[b'length']
