import hashlib
import math
import time
from threading import Lock
from threading import Thread

from TrackerAPI import get_peers_list_by_torrent_metainfo, PeersFindingError
from TorrentWriter import TorrentWriter
from settings import SETTINGS
from Peer import Peer


class Torrent:
    def __init__(self, metainfo):
        self.metainfo = metainfo
        # length of total downloaded data in torrent
        self.downloaded_data_len = 0
        self.prev_time = time.time()
        # torrent writer
        self.writer = TorrentWriter(metainfo)
        self.prev_peers_count = 1
        # peers dict
        self.peers = {}
        # peer set to store the black-listed peers
        self.peers_blacklist = set()
        # peers lock
        self.peers_lock = Lock()
        self.p_blocks = [self._get_initial_blocks_list(i)
                         for i in range(len(metainfo.pieces))]
        # list to store number of blocks in each piece
        self.p_numblocks = [0] * len(metainfo.pieces)
        self.exp_p_blocks = {}
        self._init_exp_p_blocks()
        self.exp_p_blocks_lock = Lock()

    def _get_initial_blocks_list(self, piece_idx):
        """
        Get the None defaulted list of piece as:
        [None, None, ...] where total None values in the list correspond to
        the blocks count in the piece
        :param piece_idx: piece index
        :return: list
        """
        # pre-configured block length
        block_len = SETTINGS['int_block_len']
        # get the current piece length from the metainfo
        cur_piece_len = self.metainfo.get_piece_len_at(piece_idx)
        # calculate the number of blocks in the current piece
        cur_blocks_count = math.ceil(cur_piece_len / block_len)
        # return the piece as the [None, None, ...] where total None values
        # in the list correspond to the blocks count in the piece
        return [None] * cur_blocks_count

    def _init_exp_p_blocks(self):
        """
        Initialize the expected piece blocks.
        :return: None
        """
        # get incomplete (expected) piece indices
        exp_pieces = self.writer.get_uncompleted_piece_indexes()
        # initialize expected blocks for each expected piece by adding
        # to the expected piece blocks dict as:
        # {
        #   <piece index0>:{<block index0>, <block index1>, ...},
        #   <piece index1>:{<block index0>, <block index1>, ...},
        #    ...
        # }
        for piece_idx in exp_pieces:
            self.exp_p_blocks[piece_idx] = {
                b_i for b_i in range(len(self.p_blocks[piece_idx]))}

    def _get_new_ip_port_list(self):
        """
        Get the new peers list using the tracker API.
        :return: list of peers
        """
        try:
            return get_peers_list_by_torrent_metainfo(self.metainfo)
        except PeersFindingError:
            return []

    def get_pbi_for_peer(self, peer):
        """
        Return the (piece_idx, block_idx) for the peer.
        :param peer: peer
        :return: (piece_idx, block_idx)
        """
        res_piece_idx = res_block_idx = None
        with self.exp_p_blocks_lock:
            for piece_idx in self.exp_p_blocks:
                cur_blocks = self.exp_p_blocks[piece_idx]
                if peer.have_piece(piece_idx):
                    res_piece_idx = piece_idx
                    if len(cur_blocks) != 0:
                        res_block_idx = cur_blocks.pop()
                        break
        return res_piece_idx, res_block_idx

    def handle_incorrect_pbi(self, piece_idx, block_idx):
        """
        Handle the incorrect piece and block index.
        :param piece_idx: piece index
        :param block_idx: block index for the piece index
        :return: None
        """
        with self.exp_p_blocks_lock:
            # add new expected block index to the corresponding piece index
            self.exp_p_blocks[piece_idx].add(block_idx)

    def handle_peer_disconnect(self, peer, peer_is_bad):
        """
        Handle peer disconnect.
        :param peer: peer
        :param peer_is_bad: bool value to identify if peer is bad
        :return: None
        """
        # add peer to black-list set if it is bad
        if peer_is_bad:
            self.peers_blacklist.add(peer.name)
        # remove the peer form the peers dict
        with self.peers_lock:
            self.peers.pop(peer.name)
        # add new peers
        if len(self.peers) < self.prev_peers_count * 0.7:
            self.add_new_peers()

    @property
    def progress(self):
        """
        Return the progress using the expected piece blocks and piece blocks
        :return: float
        """
        return 1 - len(self.exp_p_blocks) / len(self.p_blocks)

    @property
    def download_speed(self):
        """
        Calculate the download speed using the current time, previous time and
        the total bits downloaded so far.
        :return: Formatted string showing current download speed
        """
        # get the current time
        cur_time = time.time()
        # calculate total bits downloaded from the downloaded data length
        res_bits_count = self.downloaded_data_len * 8
        # reset downloaded data length
        self.downloaded_data_len = 0
        # get the result time
        res_time = cur_time - self.prev_time
        # for no speed
        if res_time == 0:
            return '0 B/s'
        # update previous time with the current time
        self.prev_time = cur_time
        # for bytes/second
        if res_bits_count / 1024 < 1:
            res_number = res_bits_count
            res_speed = 'B/s'
        # for KB/second
        elif res_bits_count / 1024 ** 2 < 1:
            res_number = res_bits_count / 1024
            res_speed = 'KB/s'
        # for MB/second
        else:
            res_number = res_bits_count / 1024 ** 2
            res_speed = 'MB/s'
        return '{:.2f} {}'.format(res_number / res_time, res_speed)

    def add_new_peers(self):
        """
        Add new peers and start the download from the peers.
        :return: None
        """
        while True:
            # get the peers ip:port list from the tracker
            ip_port_list = self._get_new_ip_port_list()
            # create threads for the peers
            threads = []
            for ip, port in ip_port_list:
                # create the thread to add the new peer and append to the threads list
                cur_thread = Thread(target=self._add_new_peer, args=(ip, port))
                threads.append(cur_thread)
                cur_thread.start()
            # wait for all threads to finish
            for thread in threads:
                thread.join()
            # update the previous peers count
            self.prev_peers_count = max(len(self.peers), 1)
            # break if the current peers count is greater than or equal to that of
            # previous peers count
            if len(self.peers) >= self.prev_peers_count:
                break
        # start download for each peer added in peers dict when it is not already running
        with self.peers_lock:
            for peer in self.peers.values():
                if not peer.is_running:
                    Thread(target=peer.run_download, args=()).start()

    def _add_new_peer(self, ip, port):
        """
        Add new peer with given ip and port to the peers dict indexed by <ip>:<port> key.
        :param ip: ip address of the peer
        :param port: port of the peer
        :return: None
        """
        # format the peer name as <ip>:<port>
        cur_ip_port = ip + ':' + str(port)
        # add the peer to the peers dict only when it is not already present in the
        # peers dict or peers blacklist set and when it is available for download
        if (cur_ip_port not in self.peers and
                cur_ip_port not in self.peers_blacklist):
            peer = Peer(ip, port, self)
            if peer.is_available:
                with self.peers_lock:
                    self.peers[cur_ip_port] = peer

    def run_download(self):
        self.add_new_peers()

    def handle_block(self, piece_idx, block_idx, block):
        """
        Handle the block with the given piece index, block index and the actual block.
        :param piece_idx: piece index
        :param block_idx: block index
        :param block: block
        :return: None
        """
        # increase the downloaded data length by the block length
        self.downloaded_data_len += len(block)
        # update the blocks map for the given block index in the given piece index
        self.p_blocks[piece_idx][block_idx] = block
        # increment the number of blocks in the given piece index
        self.p_numblocks[piece_idx] += 1

        if self.p_numblocks[piece_idx] == len(self.p_blocks[piece_idx]):
            self.handle_piece(piece_idx)

    def handle_piece(self, piece_idx):
        """
        Handle the piece with given piece index.
        :param piece_idx: piece index
        :return: None
        """
        # form piece from its blocks
        piece = b''.join(self.p_blocks[piece_idx])
        # calculate piece sha-1 hash
        cur_piece_hash = hashlib.sha1(piece).digest()
        # if calculated hash doesn't match with the piece hash in metainfo,
        # then simply handle the incorrect piece and return
        if cur_piece_hash != self.metainfo.pieces[piece_idx]:
            self._handle_incorrect_piece(piece_idx)
            return
        # Otherwise, clear piece blocks and write the piece to the file
        self.p_blocks[piece_idx] = None
        self.writer.write_piece(piece_idx, piece)
        # remove piece blocks from expected piece blocks
        with self.exp_p_blocks_lock:
            self.exp_p_blocks.pop(piece_idx)

    def _handle_incorrect_piece(self, piece_idx):
        """
        Handle the incorrect piece with given piece index.
        :param piece_idx: piece index
        :return: None
        """
        # reset the piece blocks for the given piece index
        self.p_blocks[piece_idx] = self._get_initial_blocks_list(piece_idx)
        # reset the expected piece block and blocks count for the given piece index
        with self.exp_p_blocks_lock:
            self.exp_p_blocks[piece_idx] = {
                b_i for b_i in range(len(self.p_blocks[piece_idx]))}
            self.p_numblocks[piece_idx] = 0
