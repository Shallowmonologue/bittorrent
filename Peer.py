import socket
import struct

from Config import SETTINGS
from TorrentWriter import TorrentWriter


class Peer:
    def __init__(self, ip, port, torrent):
        self.ip = ip
        self.port = port
        self.torrent = torrent
        self.sock = socket.socket()
        self.processed_block = None
        self.is_available = True
        self.peer_choking = True
        self.peer_interested = False
        self.im_choking = True
        self.im_interested = False
        self.buffer = b''
        self.available_pieces_map = None
        self.is_running = False

        self._init_connection()

    def _init_connection(self):
        """
        对peer的连接进行初始化, 步骤包含了:
        1. 通过包含timeout的TCP连接peer
        2. 传递握手信息
        3. 处理握手信息的回复
        4. 发送interested信息
        :return: None
        """
        try:
            # 开始执行TCP连接, 包含timeout信息
            self.sock.settimeout(SETTINGS['timeout_for_peer'])
            self.sock.connect((self.ip, self.port))
            # 发送握手信息
            self._send_handshake(self.torrent.metainfo.info_hash)
            # 处理来自peer的握手信息回复
            self._handle_handshake()
            # 发送interested信息
            self._send_msg(msg_id=2)
            # 检查回复
            self._check_buffer()
        except Exception:
            # 如果发生错误就关闭连接, 并标记该peer
            self.is_available = False
            self.sock.close()

    def _check_buffer(self):
        """
        更新并处理缓存
        :return: None
        """
        self._update_buffer()
        self._handle_buffer()
        # 循环检查缓存
        if self.buffer_length != 0:
            self._check_buffer()

    def _handle_buffer(self):
        """
        处理缓冲区数据，若存在足够数据则进行解析
        :return: None
        """
        # 若缓存中存在数据则进行解析
        while self.buffer_length:
            # 若缓存数据小于4字节无法解析, 所以直接返回
            if self.buffer_length < 4:
                return
            # 获取该条报文的长度offset
            prefix_len = struct.unpack('!L', self.buffer[:4])[0]
            offset = 4
            if prefix_len + offset > self.buffer_length:
                return
            if prefix_len == 0:
                pass
            else:
                self._decode_msg(self.buffer[offset: offset + prefix_len])
                offset += prefix_len
            # 更新buffer中数据
            self.buffer = self.buffer[offset:]

    def _send_msg(self, msg_id, **args):
        """
        设定发送信息的choke和interested属性
        :param msg_id: 信息类型
        :param args: 关键字参数
        :return: None
        """
        if msg_id == 0:  # choke
            self.im_choking = True
        elif msg_id == 1:  # unchoke
            self.im_choking = False
        elif msg_id == 2:  # interested
            self.im_interested = True
        elif msg_id == 3:  # not_interested
            self.im_interested = False
        msg = self.build_msg(msg_id, **args)
        self.sock.send(msg)

    def _handle_handshake(self):
        """
        处理peer通信的握手信息
        :return: None
        """
        # 握手信息格式: <pstrlen><pstr><reserved><info_hash><peer_id>
        # 握手信息长度: 49(fixed) + pstrlen(variable)
        self._update_buffer()
        pstrlen = self.buffer[0]  # 第一个字节为pstrlen
        # 循环读取知道收到完整的握手信息
        while self.buffer_length < 49 + pstrlen:
            self._update_buffer()
        # 跳过pstrlen, 解析整个握手信息
        handshake_data = self.buffer[1: 49 + pstrlen]
        # 解析pstr
        pstr = handshake_data[:pstrlen]
        # 如果pstr与协议名不匹配, 则忽略掉此次握手信息
        if pstr != SETTINGS['protocol_name']:
            raise UnexpectedProtocolType(pstr.decode())
        # 将握手以外的数据保留在缓冲区中
        self.buffer = self.buffer[49 + pstrlen:]

    def get_data_from_socket(self):
        """
        返回TCP socket从的数据
        :return: 字节类型数据
        """
        return self.sock.recv(SETTINGS['max_ans_size'])

    def _update_buffer(self):
        """
        从TCP socket读取数据并更新buffer
        :return: None
        """
        data = self.get_data_from_socket()
        if not data:
            raise Exception('Received empty data!')
        self.buffer += data

    def _send_handshake(self, info_hash):
        """
        使用给定的info_hash构建并发送握手消息
        :param info_hash: info的哈希值
        :return: None
        """
        self.sock.send(self.build_handshake(info_hash))

    @property
    def buffer_length(self):
        """
        :return: 缓冲区的数据长度
        """
        return len(self.buffer)

    @property
    def name(self):
        """
        :return: 以<ip>:<port>形式定义的peer
        """
        return '{}:{}'.format(self.ip, self.port)

    def run_download(self):
        """
        从peer中下载对应block
        :return: None
        """
        # 设定该peer正在下载中
        self.is_running = True
        # 若peer可用则进行下载
        while self.is_available:
            # 获取piece索引以及对应的block索引
            piece_idx, block_idx = self.torrent.get_pbi_for_peer(self)
            # 若piece索引丢失则关闭该连接
            if piece_idx is None:
                self._close()
                break
            # 若block索引丢失则跳进下次循环
            if block_idx is None:
                continue
            try:
                # 请求下载该block
                self.request_block(piece_idx, block_idx)
            except Exception:
                # 若peer没有可供下载的pieces, 则标记该peer并关闭连接
                peer_is_bad = False
                if self.available_pieces_map is None:
                    peer_is_bad = True
                self._close(peer_is_bad)

    def request_block(self, piece_idx, block_idx):
        """
        给定piece索引与block索引, 下载对应block
        :param piece_idx: piece索引
        :param block_idx: block索引
        :return: None
        """
        # 标记该请求的block
        self.processed_block = (piece_idx, block_idx)
        # 如果peer处于choke状态
        if self.peer_choking:
            # 发送interested消息
            self._send_msg(msg_id=2)
            # 检查peer消息回应
            self._check_buffer()
            # 如果仍不回应则关闭此次连接
            if self.peer_choking:
                self._close()
                return
        # 获取该block所在piece的长度
        piece_len = self.torrent.metainfo.get_piece_len_at(piece_idx)
        # 计算block长度的offset
        offset = block_idx * SETTINGS['int_block_len']
        # 进而计算剩余block的长度
        block_len = min(piece_len - offset, SETTINGS['int_block_len'])
        # 通过指定piece索引, block长度, offset
        self._send_msg(msg_id=6,
                       piece_idx=piece_idx, block_len=block_len, offset=offset)
        # 检查peer消息回复
        self._check_buffer()
        # 处理不正确的block信息
        if self.processed_block is not None:
            self.torrent.handle_incorrect_pbi(*self.processed_block)
            self.processed_block = None

    def have_piece(self, piece_idx):
        """
        检查指定索引对应的piece是否存在
        :param piece_idx: piece索引
        :return: 若存在则返回True
        """
        if self.available_pieces_map is not None:
            return self.available_pieces_map[piece_idx]
        return True

    def _decode_msg(self, msg):
        """
        解码消息的字节编码并更新对应的bitfield
        :param msg: 每条消息的字节编码
        :return: None
        """
        # 获取消息id
        msg_id = msg[0]
        # choke
        if msg_id == 0:
            self.peer_choking = True
        # unchoke
        elif msg_id == 1:
            self.peer_choking = False
        # interested
        elif msg_id == 2:
            self.peer_interested = True
        # not_interested
        elif msg_id == 3:
            self.peer_interested = False
        # 消息格式: <len=0005><id=4><piece index>
        elif msg_id == 4:
            # 获取消息对应的piece索引
            idx = struct.unpack('!L', msg[1:5])[0]
            # 标记该piece可用
            if self.available_pieces_map is not None:
                self.available_pieces_map[idx] = True
        # bitfield格式: <len=0001+X><id=5><bitfield>
        elif msg_id == 5:
            # 从helper方法获取bitfield
            cur_map = TorrentWriter.get_info_about_pieced_from_bytes(msg[1:])
            # 计算可用的piece
            pieces_count = len(self.torrent.metainfo.pieces)
            # 根据bitfield更新piece_map
            self.available_pieces_map = cur_map[:pieces_count]
        # 请求消息
        elif msg_id == 6:
            pass
        # piece格式: <len=0009+X><id=7><index><begin><block>
        elif msg_id == 7:
            # 获取索引
            piece_idx = struct.unpack('!L', msg[1:5])[0]
            # 获取offect
            offset = struct.unpack('!L', msg[5:9])[0]
            # 获取block
            block = msg[9:]
            # 处理该block
            self.torrent.handle_block(
                piece_idx, offset // SETTINGS['int_block_len'], block)
            # 处理结束后清楚该block
            self.processed_block = None
        # 退出该消息
        elif msg_id == 8:
            pass
        # 端口消息
        elif msg_id == 9:
            pass
        else:
            raise UnknownMessageType('msg_id = {}'.format(msg_id))

    def _close(self, peer_is_bad=False):
        """
        关闭该peer的TCP连接
        :param peer_is_bad: 若该peer无法连接则为True
        :return: None
        """
        # 处理不正确的block
        if self.processed_block is not None:
            self.torrent.handle_incorrect_pbi(*self.processed_block)
        # 处理peer退出连接事件
        self.torrent.handle_peer_disconnect(self, peer_is_bad=peer_is_bad)
        # 标记该peer不可用
        self.is_available = False
        # 标记该peer不再执行
        self.is_running = False
        # 关闭TCP连接
        self.sock.close()

    @staticmethod
    def build_msg(msg_id, **args):
        """
        给定msg_id进行消息创建
        :param msg_id: message类型
        :param args: 0或关键字信息
        :return: 字节编码消息
        """
        # choke, unchoke, interested, not_interested的信息长度为1, 且payload为空
        if msg_id in {0, 1, 2, 3}:
            msg_len = b'\x00\x00\x00\x01'
            payload = b''
        # id为4时的payload格式: <len=0005><id=4><piece index>
        elif msg_id == 4:
            msg_len = b'\x00\x00\x00\x05'
            payload = struct.pack('!L', args['piece_idx'])
        # id为6时的payload格式: <len=0013><id=6><index><begin><length>
        elif msg_id == 6:
            msg_len = b'\x00\x00\x00\x0d'
            payload = (struct.pack('!L', args['piece_idx']) +
                       struct.pack('!L', args['offset']) +
                       struct.pack('!L', args['block_len']))
        # bitfield, piece, cancel, port类型
        elif msg_id in {5, 7, 8, 9}:
            raise NotImplementedError()
        # 空消息类型
        elif msg_id == -1:
            return b'\x00\x00\x00\x00'
        else:
            raise UnknownMessageType()
        msg_id_bytes = struct.pack('!B', msg_id)
        return msg_len + msg_id_bytes + payload

    @staticmethod
    def build_handshake(info_hash):
        """
        从metainfo中创建并返回握手信息
        :param info_hash: info哈希值
        :return: 字节编码类型的握手信息
        """
        """
        握手信息格式: <pstrlen><pstr><reserved><info_hash><peer_id>
        pstrlen: <pstr>类型的长度 (0x13)
        pstr: 协议名称(字符串类型'BitTorrent protocol')
        reserved: 全0的8字节
        info_hash: 20字节的SHA1哈希值
        peer_id: 20字节
        """
        return (b'\x13' + SETTINGS['protocol_name'] +
                b'\x00' * 8 + info_hash + SETTINGS['peer_id'])


class UnexpectedProtocolType(Exception):
    pass


class UnknownMessageType(Exception):
    pass
