import socket

from settings import SETTINGS
from messages import build_handshake


class Peer:
    def __init__(self, ip, port, torrent):
        self.ip = ip
        self.port = port
        self.torrent = torrent
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_available = True
        self.peer_choking = True
        self.peer_interested = False
        self.im_choking = True
        self.im_interested = False
        self.buffer = b''
        self._init_connection()

    def _init_connection(self):
        """
        Connects to the peer over TCP, sends the handshake message and then
        handles the incoming peer handshake.
        :return: None
        """
        # connect to the peer over TCP
        try:
            # start TCP connection to the peer with timeout in settings
            self.sock.settimeout(SETTINGS['timeout_for_peer'])
            self.sock.connect((self.ip, self.port))
            # send the very first expected message i.e. handshake
            self._send_handshake(self.torrent.metainfo.info_hash)
            # handle the response handshake by the peer
            self._handle_handshake()
            print(f"Handshake with peer {self.ip}:{self.port} completed!")
        except Exception:
            # if an error occurs, mark the peer as unavailable and close the connection
            self.is_available = False
            self.sock.close()
            print(f"Handshake with peer {self.ip}:{self.port} failed!")

    @property
    def buffer_length(self):
        return len(self.buffer)

    def _handle_handshake(self):
        """
        Handles the handshake message from the peer
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

    def get_new_data_from_socket(self):
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
        new_data = self.get_new_data_from_socket()
        if not new_data:
            raise Exception('Received empty data!')
        self.buffer += new_data

    def _send_handshake(self, info_hash):
        """
        Builds and sends the handshake message using given info_hash
        :param info_hash: info_hash
        :return: None
        """
        self.sock.send(build_handshake(info_hash))


class UnexpectedProtocolType(Exception):
    pass
