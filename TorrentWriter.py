import os


class TorrentWriter:
    def __init__(self, metainfo):
        self.metainfo = metainfo
        self._downloads_dir = os.path.join(os.getcwd(), 'downloads')
        self.check_place_to_download()

    @property
    def downloads_dir(self):
        """
        指定下载内容的储存路径
        :return: 下载路径
        """
        return self._downloads_dir

    def get_uncompleted_piece_indexes(self):
        """
        使用列表metainfo来储存不完整的pieces的索引
        Get the list of incomplete piece indices using metainfo.
        :return: list of incomplete piece indices
        """
        res = []
        for i in range(len(self.metainfo.pieces)):
            res.append(i)
        return res

    @staticmethod
    def get_info_about_pieced_from_bytes(data):
        """
        从bitfield信息查看可获取的pieces，其中1代表着该pieces可获取
        :param data: 字节类型的数据
        :return: 比特类型的数据（从字节类型转化的）
        """
        def bits_in_byte(cur_byte):
            str_byte = bin(cur_byte)[2:]
            str_byte = '0' * (8 - len(str_byte)) + str_byte
            for str_bit in str_byte:
                yield str_bit == '1'

        res = []
        for byte in data:
            for bit in bits_in_byte(byte):
                res.append(bit)
        return res

    def check_place_to_download(self):
        """
        若指定的下载路径不存在，则创建该路径
        :return: None
        """
        path_to_place = os.path.join(self.downloads_dir, self.metainfo.name)
        if not os.path.exists(path_to_place):
            self.create_place_to_download()

    def write_piece(self, piece_idx, piece):
        """
        对于可获取的piece进行写入
        :param piece_idx: piece的索引
        :param piece: piece数据（字节类型）
        :return: None
        """
        piece_offset_in_data = piece_idx * self.metainfo.piece_length
        if self.metainfo.is_single_file:
            self._write_data_in_single_file(
                os.path.join(self.downloads_dir, self.metainfo.name),
                piece_offset_in_data, 0, len(piece), piece)
        else:
            file_offset_in_data = 0
            file_idx = -1
            next_offset = 0
            while next_offset <= piece_offset_in_data:
                file_idx += 1
                file_offset_in_data = next_offset
                next_offset += self.metainfo.files[file_idx]['length']

            offset_in_piece = 0
            while offset_in_piece != len(piece):
                offset_in_file = 0
                file_len = self.metainfo.files[file_idx]['length']
                file_path = self.metainfo.files[file_idx]['path']
                full_path = os.path.join(
                    self.downloads_dir, self.metainfo.name, file_path)
                if file_offset_in_data < piece_offset_in_data:
                    offset_in_file = piece_offset_in_data - file_offset_in_data
                    data_len = min(len(piece), file_len - offset_in_file)
                else:
                    data_len = min(file_len, len(piece) - offset_in_piece)

                self._write_data_in_single_file(
                    full_path, offset_in_file, offset_in_piece,
                    data_len, piece)
                offset_in_piece += data_len
                file_offset_in_data += file_len
                file_idx += 1

    @staticmethod
    def _write_data_in_single_file(file_path, offset_in_file, offset_in_piece, data_len, piece):
        '''
        依据路径写入对应数据
        :param offset_in_file: 写入数据位于文件中的位置
        :param offset_in_piece: 写入数据位于piece中的位置
        :return: None
        '''
        with open(file_path, 'r+b') as f:
            f.seek(offset_in_file)
            f.write(piece[offset_in_piece: offset_in_piece + data_len])

    def create_place_to_download(self):
        """
        对单个bittorrent文件创建单个空文件,多个bittorrent文件则创建多个空文件
        :return: None
        """
        if self.metainfo.is_single_file:
            self._create_single_empty_file(file_path=self.metainfo.name,
                                           length=self.metainfo.length)
        else:
            self._create_empty_files()

    def _create_single_empty_file(self, file_path, length):
        """
        对于单个空文件定义其路径与长度
        :param file_path: 文件路径
        :param length: 文件长度
        :return: None
        """
        full_path = os.path.join(self.downloads_dir, file_path)
        dirs_path, _ = os.path.split(full_path)
        os.makedirs(dirs_path, exist_ok=True)
        self._create_empty_file(full_path, length)

    def _create_empty_files(self):
        """
        对于多个空文件则根据meataifo完成创建
        :return: None
        """
        base_dir = self.metainfo.name
        # 从metainfo遍历文件再创建空文件
        for file_dict in self.metainfo.files:
            # 指定创建文件目录
            file_path = os.path.join(base_dir, file_dict['path'])
            # 调用单个空文件创建函数
            self._create_single_empty_file(file_path, file_dict['length'])

    @staticmethod
    def _create_empty_file(file_path, length):
        """
        空文件创建.使用\x00覆盖
        """
        # 创建用于写入的二进制文件
        with open(file_path, 'wb') as f:
            # 文件末尾
            f.seek(length - 1)
            # 用0值覆盖
            f.write(b'\x00')  
