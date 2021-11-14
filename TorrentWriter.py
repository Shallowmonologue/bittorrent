import os


class TorrentWriter:
    def __init__(self, metainfo):
        self.metainfo = metainfo
        self._downloads_dir = os.path.join(os.getcwd(), 'downloads')
        self.check_place_to_download()

    @property
    def downloads_dir(self):
        """
        Get the download directory for the torrent.
        :return: downloads directory
        """
        return self._downloads_dir

    def get_uncompleted_piece_indexes(self):
        """
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
        Get the bits from the bytes and then get which pieces are available,
        1 indicates that the piece is available.
        :param data: data in bytes
        :return: list of bits from the bytes data
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
        Check if the downloads directory exists; otherwise create it.
        :return: None
        """
        path_to_place = os.path.join(self.downloads_dir, self.metainfo.name)
        if not os.path.exists(path_to_place):
            self.create_place_to_download()

    def write_piece(self, piece_idx, piece):
        """
        Write the piece to the file with the given piece index and piece data.
        :param piece_idx: piece index
        :param piece: piece data in bytes
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
    def _write_data_in_single_file(
            file_path, offset_in_file, offset_in_piece, data_len, piece):
        with open(file_path, 'r+b') as f:
            f.seek(offset_in_file)
            f.write(piece[offset_in_piece: offset_in_piece + data_len])

    def create_place_to_download(self):
        """
        Create a single empty file single-file torrent; otherwise create multiple
        empty files in the base directory.
        :return: None
        """
        if self.metainfo.is_single_file:
            self._create_single_empty_file(file_path=self.metainfo.name,
                                           length=self.metainfo.length)
        else:
            self._create_empty_files()

    def _create_single_empty_file(self, file_path, length):
        """
        Create the single empty file with given file_path and the length.
        :param file_path: file path
        :param length: file length
        :return: None
        """
        full_path = os.path.join(self.downloads_dir, file_path)
        dirs_path, _ = os.path.split(full_path)
        os.makedirs(dirs_path, exist_ok=True)
        self._create_empty_file(full_path, length)

    def _create_empty_files(self):
        """
        Create multiple empty files in the base directory given in metainfo.
        :return: None
        """
        base_dir = self.metainfo.name
        # traverse files from metainfo and create empty files
        for file_dict in self.metainfo.files:
            # create the file path by appending the base directory
            file_path = os.path.join(base_dir, file_dict['path'])
            # create the single file
            self._create_single_empty_file(file_path, file_dict['length'])

    @staticmethod
    def _create_empty_file(file_path, length):
        """
        Create empty file of the given length at the given file path.
        :param file_path: file path
        :param length: file length
        :return: None
        """
        # open file in binary mode for writing
        with open(file_path, 'wb') as f:
            # seek to the end of the file
            f.seek(length - 1)
            # write byte with value=0
            f.write(b'\x00')
