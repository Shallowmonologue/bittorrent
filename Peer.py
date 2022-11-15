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
            # check for reply
            self._check_buffer()
        except Exception:
            # if an error occurs, mark the peer as unavailable and close the connection
            self.is_available = False
            self.sock.close()

    def _check_buffer(self):
        """
        Update and handle the buffer.
        :return: None
        """
        # update the buffer
        self._update_buffer()
        # handle the buffer
        self._handle_buffer()
        # keep checking the buffer
        if self.buffer_length != 0:
            self._check_buffer()

    def _handle_buffer(self):
        """
        Handle the buffer data i.e if there is sufficient data in the
        buffer then parse it in the buffer.
        :return: None
        """
        # keep parsing till there is any data in the buffer
        while self.buffer_length:
            # we need at least 4 bytes to identify the message
            if self.buffer_length < 4:
                return
            prefix_len = struct.unpack('!L', self.buffer[:4])[0]
            offset = 4
            if prefix_len + offset > self.buffer_length:
                return
            if prefix_len == 0:
                pass  # keep-alive msg
            else:
                self._decode_msg(self.buffer[offset: offset + prefix_len])
                offset += prefix_len
            self.buffer = self.buffer[offset:]

    def _send_msg(self, msg_id, **args):
        """
        Send appropriate message using message id and keyword arguments.
        :param msg_id: message id
        :param args: keyword arguments
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
        Handles the handshake message from the peer.
        :return: None
        """
        # msg format: <pstrlen><pstr><reserved><info_hash><peer_id>
        # Handshake length: 49(fixed) + pstrlen(variable)
        self._update_buffer()
        pstrlen = self.buffer[0]  # very first byte is pstrlen
        # keep reading from socket till we get complete handshake
        while self.buffer_length < 49 + pstrlen:
            self._update_buffer()
        # skip pstrlen and parse the entire handshake data
        handshake_data = self.buffer[1: 49 + pstrlen]
        # parse pstr
        pstr = handshake_data[:pstrlen]
        # if the pstr does not match, ignore such peer handshake
        if pstr != SETTINGS['protocol_name']:
            raise UnexpectedProtocolType(pstr.decode())
        # keep data other than handshake in the buffer
        self.buffer = self.buffer[49 + pstrlen:]

    def get_data_from_socket(self):
        """
        Reads new data from the TCP socket and return it.
        :return: bytes read from the TCP socket
        """
        return self.sock.recv(SETTINGS['max_ans_size'])

    def _update_buffer(self):
        """
        Reads new data from the TCP socket and updates the buffer.
        :return: None
        """
        data = self.get_data_from_socket()
        if not data:
            raise Exception('Received empty data!')
        self.buffer += data

    def _send_handshake(self, info_hash):
        """
        Builds and sends the handshake message using given info_hash
        :param info_hash: info_hash
        :return: None
        """
        self.sock.send(self.build_handshake(info_hash))

    @property
    def buffer_length(self):
        """
        :return: buffer length as int
        """
        return len(self.buffer)

    @property
    def name(self):
        """
        :return: peer name as <ip>:<port>
        """
        return '{}:{}'.format(self.ip, self.port)

    def run_download(self):
        """
        Download blocks from the peer.
        :return: None
        """
        # mark the download as running
        self.is_running = True
        # keep running download till the peer is available
        while self.is_available:
            # get the piece index and block index from the torrent
            piece_idx, block_idx = self.torrent.get_pbi_for_peer(self)
            # close the connection if the piece index is missing
            if piece_idx is None:
                self._close()
                break
            # if no block is present for the piece continue with the next
            if block_idx is None:
                continue
            try:
                # request the block
                self.request_block(piece_idx, block_idx)
            except Exception:
                # mark the peer bad and close the connection on error when no pieces are
                # available from the peer to download
                peer_is_bad = False
                if self.available_pieces_map is None:
                    peer_is_bad = True
                self._close(peer_is_bad)

    def request_block(self, piece_idx, block_idx):
        """
        Request the block of given piece index from the piece of given piece index.
        :param piece_idx: piece index
        :param block_idx: block index
        :return: None
        """
        # mark the processed block that is to be requested
        self.processed_block = (piece_idx, block_idx)
        # if peer is chocking then:
        if self.peer_choking:
            # send an interested message to the peer
            self._send_msg(msg_id=2)
            # check for the peer response
            self._check_buffer()
            # if peer keeps chocking close the connection with the peer and return
            if self.peer_choking:
                self._close()
                return
        # get the piece length with the given piece index from the torrent metainfo
        piece_len = self.torrent.metainfo.get_piece_len_at(piece_idx)
        # calculate the begin/offset
        offset = block_idx * SETTINGS['int_block_len']
        # calculate the block length
        block_len = min(piece_len - offset, SETTINGS['int_block_len'])
        # request for the block using index, begin/offset and length
        self._send_msg(msg_id=6,
                       piece_idx=piece_idx, block_len=block_len, offset=offset)
        # check for the peer response
        self._check_buffer()
        # handle incorrect <piece, block>
        if self.processed_block is not None:
            self.torrent.handle_incorrect_pbi(*self.processed_block)
            self.processed_block = None

    def have_piece(self, piece_idx):
        """
        Check if we have the given piece index.
        :param piece_idx: piece index
        :return: True if available_pieces_map is None or if we have the piece,
        otherwise False
        """
        if self.available_pieces_map is not None:
            return self.available_pieces_map[piece_idx]
        return True

    def _decode_msg(self, msg):
        """
        Decodes bytes encoded message and updates the peer fields accordingly.
        :param msg: bytes encoded peer message
        :return: None
        """
        # get message_id
        msg_id = msg[0]
        # choke message
        if msg_id == 0:
            self.peer_choking = True
        # unchoke message
        elif msg_id == 1:
            self.peer_choking = False
        # interested message
        elif msg_id == 2:
            self.peer_interested = True
        # not_interested message
        elif msg_id == 3:
            self.peer_interested = False
        # have message: <len=0005><id=4><piece index>
        elif msg_id == 4:
            # get the piece index from the message
            idx = struct.unpack('!L', msg[1:5])[0]
            # mark piece as available in the available_pieces_map
            if self.available_pieces_map is not None:
                self.available_pieces_map[idx] = True
        # bitfield message: <len=0001+X><id=5><bitfield>
        elif msg_id == 5:
            # get the bitfield bits from the helper method
            cur_map = TorrentWriter.get_info_about_pieced_from_bytes(msg[1:])
            # count of available pieces
            pieces_count = len(self.torrent.metainfo.pieces)
            # update the available_pieces_map according to bitfield bits
            self.available_pieces_map = cur_map[:pieces_count]
        # request message
        elif msg_id == 6:
            pass
        # piece message: <len=0009+X><id=7><index><begin><block>
        elif msg_id == 7:
            # get the index
            piece_idx = struct.unpack('!L', msg[1:5])[0]
            # get the begin/offset
            offset = struct.unpack('!L', msg[5:9])[0]
            # get the block
            block = msg[9:]
            # handle the block
            self.torrent.handle_block(
                piece_idx, offset // SETTINGS['int_block_len'], block)
            # clear the processed_block after processing the block
            self.processed_block = None
        # cancel message
        elif msg_id == 8:
            pass
        # port message
        elif msg_id == 9:
            pass
        else:
            raise UnknownMessageType('msg_id = {}'.format(msg_id))

    def _close(self, peer_is_bad=False):
        """
        Close the peer TCP connection.
        :param peer_is_bad: boolean value to identify if the peer is bad
        :return: None
        """
        # handle incorrect block (if any)
        if self.processed_block is not None:
            self.torrent.handle_incorrect_pbi(*self.processed_block)
        # handle the peer disconnect
        self.torrent.handle_peer_disconnect(self, peer_is_bad=peer_is_bad)
        # mark the peer unavailable
        self.is_available = False
        # mark that the download from the peer has stopped
        self.is_running = False
        # close the TCP connection
        self.sock.close()

    @staticmethod
    def build_msg(msg_id, **args):
        """
        Builds a message from the given message id and the args.
        :param msg_id: message id
        :param args: zero or more keyword arguments
        :return: bytes encoded message
        """
        # CHOKE, UNCHOKE, INTERESTED and NOT_INTERESTED don't have any payload and have msg_len=1
        if msg_id in {0, 1, 2, 3}:
            msg_len = b'\x00\x00\x00\x01'
            payload = b''
        # have: <len=0005><id=4><piece index>
        elif msg_id == 4:
            msg_len = b'\x00\x00\x00\x05'
            payload = struct.pack('!L', args['piece_idx'])
        # request: <len=0013><id=6><index><begin><length>
        elif msg_id == 6:
            msg_len = b'\x00\x00\x00\x0d'
            payload = (struct.pack('!L', args['piece_idx']) +
                       struct.pack('!L', args['offset']) +
                       struct.pack('!L', args['block_len']))
        # bitfield, piece, cancel, port
        elif msg_id in {5, 7, 8, 9}:
            raise NotImplementedError()
        # keep-alive message
        elif msg_id == -1:
            return b'\x00\x00\x00\x00'
        else:
            raise UnknownMessageType()
        msg_id_bytes = struct.pack('!B', msg_id)
        return msg_len + msg_id_bytes + payload

    @staticmethod
    def build_handshake(info_hash):
        """
        Create and return the handshake from the metainfo.
        :param info_hash: info_hash
        :return: bytes encoded handshake message
        """
        """
        Handshake format: <pstrlen><pstr><reserved><info_hash><peer_id>
        pstrlen: string length of <pstr> (19 in decimal i.e. 0x13)
        pstr: string identifier of the protocol (BitTorrent protocol)
        reserved: 8-byte (all zeroes)
        info_hash: 20-byte 20-byte SHA1 hash of the info key in the metainfo file
        peer_id: 20-byte 
        """
        return (b'\x13' + SETTINGS['protocol_name'] +
                b'\x00' * 8 + info_hash + SETTINGS['peer_id'])


class UnexpectedProtocolType(Exception):
    pass


class UnknownMessageType(Exception):
    pass
