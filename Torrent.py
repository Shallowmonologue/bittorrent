import hashlib
import math
import time
from threading import Lock
from threading import Thread

from TrackerAPI import get_peers_list_by_torrent_metainfo, PeersFindingError
from TorrentWriter import TorrentWriter
from Config import SETTINGS
from Peer import Peer


class Torrent:
    def __init__(self, metainfo):
        self.metainfo = metainfo
        # torrent文件中下载内容的长度
        self.downloaded_data_len = 0
        self.prev_time = time.time()
        # torrent writer
        # 将下载内容读写至磁盘
        self.writer = TorrentWriter(metainfo)
        self.prev_peers_count = 1
        # 使用dict类型储存peers
        self.peers = {}
        # 使用set类型储存peers黑名单
        self.peers_blacklist = set()
        # 互斥访问peer锁
        self.peers_lock = Lock()
        self.p_blocks = [self._get_initial_blocks_list(i)
                         for i in range(len(metainfo.pieces))]
        # 每一个piece中储存的block数量
        self.p_numblocks = [0] * len(metainfo.pieces)
        self.exp_p_blocks = {}
        self._init_exp_p_blocks()
        self.exp_p_blocks_lock = Lock()

    def _get_initial_blocks_list(self, piece_idx):
        """
        初始化block list, block list的长度由piece中block的数量决定
        :param piece_idx: piece的索引
        :return: 储存block信息的list
        """
        # 预先设定好的block长度
        block_len = SETTINGS['int_block_len']
        # 从metainfo中获取当前piece的长度
        cur_piece_len = self.metainfo.get_piece_len_at(piece_idx)
        # 计算当前piece中应有多少个block
        cur_blocks_count = math.ceil(cur_piece_len / block_len)
        # 以[None, None, ...] 形式返回当前piece的block list
        return [None] * cur_blocks_count

    def _init_exp_p_blocks(self):
        """
        初始化未完成的pieces的block list, 其形式如下:
        {
            <piece index0>:{<block index0>, <block index1>, ...},
            <piece index1>:{<block index0>, <block index1>, ...},
            ...
        }
        :return: None
        """
        # 获取未完成的piece索引
        exp_pieces = self.writer.get_uncompleted_piece_indexes()
        # 对每个未完成的piece初始化其block list, 其形式如下:
        for piece_idx in exp_pieces:
            self.exp_p_blocks[piece_idx] = {
                b_i for b_i in range(len(self.p_blocks[piece_idx]))}

    def _get_new_ip_port_list(self):
        """
        调用tracker  API获取新的peers名单列表
        :return: peers列表
        """
        try:
            return get_peers_list_by_torrent_metainfo(self.metainfo)
        except PeersFindingError:
            return []

    def get_pbi_for_peer(self, peer):
        """
        对每个peer返回需要请求的piece与block索引, 其形式如下:
        (piece_idx, block_idx)
        :param peer: peer对象
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
        若收到不正确的(piece_idx, block_idx), 将其加入未完成的block list
        :param piece_idx: piece索引
        :param block_idx: piece内的block索引
        :return: None
        """
        with self.exp_p_blocks_lock:
            self.exp_p_blocks[piece_idx].add(block_idx)

    def handle_peer_disconnect(self, peer, peer_is_bad):
        """
        若peer失去连接, 则将其加入黑名单并重新获取peer
        :param peer: peer对象
        :param peer_is_bad: bool类型
        :return: None
        """
        # 将连接状况较差的peer加入黑名单
        if peer_is_bad:
            self.peers_blacklist.add(peer.name)
        # 从peer名单列表中删去该peer
        with self.peers_lock:
            self.peers.pop(peer.name)
        # 添加新的peer
        if len(self.peers) < self.prev_peers_count * 0.7:
            self.add_new_peers()

    @property
    def progress(self):
        """
        未完成block list的进度条实现
        :return: float
        """
        return 1 - len(self.exp_p_blocks) / len(self.p_blocks)

    @property
    def download_speed(self):
        """
        计算当前的下载速度, 下载耗时以及完成下载的数据大小
        :return: str类型(下载速度)
        """
        # 获取当前时间
        cur_time = time.time()
        # 计算已下载内容的数据大小(bit)
        res_bits_count = self.downloaded_data_len * 8
        # 重置下载数据大小
        self.downloaded_data_len = 0
        # 计算时间差
        res_time = cur_time - self.prev_time
        # 速度为0时
        if res_time == 0:
            return '0 B/s'
        # 使用当前时间充当下次计算的起始时间
        self.prev_time = cur_time
        # 下载速度达到B/s时
        if res_bits_count / 1024 < 1:
            res_number = res_bits_count
            res_speed = 'B/s'
        # 下载速度达到KB/s时
        elif res_bits_count / 1024 ** 2 < 1:
            res_number = res_bits_count / 1024
            res_speed = 'KB/s'
        # 下载速度达到MB/s时
        else:
            res_number = res_bits_count / 1024 ** 2
            res_speed = 'MB/s'
        return '{:.2f} {}'.format(res_number / res_time, res_speed)

    def add_new_peers(self):
        """
        添加新的peer并开始下载
        :return: None
        """
        while True:
            # 从tracker中获得peer的ip与端口号
            ip_port_list = self._get_new_ip_port_list()
            # 创建线程
            threads = []
            for ip, port in ip_port_list:
                # 创建线程以添加新的peer
                cur_thread = Thread(target=self._add_new_peer, args=(ip, port))
                threads.append(cur_thread)
                cur_thread.start()
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            # 更新记录的peer数量
            self.prev_peers_count = max(len(self.peers), 1)
            # 若当前的peer数量大于等于peer的记录数量则break, 不再添加新的peer
            if len(self.peers) >= self.prev_peers_count:
                break
        # 启动没有正在运行的peer
        with self.peers_lock:
            for peer in self.peers.values():
                if not peer.is_running:
                    Thread(target=peer.run_download, args=()).start()

    def _add_new_peer(self, ip, port):
        """
        通过给定的ip与端口号添加新的peer至peers dict中
        :param ip: peer的ip地址
        :param port: peer的端口号
        :return: None
        """
        # 通过<ip>:<port>的形式定义peer格式
        cur_ip_port = ip + ':' + str(port)
        # 对于不在peers dict中的peer, 且该peer不在黑名单中, 完成加入
        if cur_ip_port not in self.peers and cur_ip_port not in self.peers_blacklist:
            peer = Peer(ip, port, self)
            if peer.is_available:
                with self.peers_lock:
                    self.peers[cur_ip_port] = peer

    def run_download(self):
        self.add_new_peers()

    def handle_block(self, piece_idx, block_idx, block):
        """
        处理新增加的block时
        :param piece_idx: piece索引
        :param block_idx: block索引
        :param block: block对象
        :return: None
        """
        # 计算block长度(用以计算下载速度)
        self.downloaded_data_len += len(block)
        # 讲block对象添加至block list中
        self.p_blocks[piece_idx][block_idx] = block
        # 增加对应piece的索引长度
        self.p_numblocks[piece_idx] += 1

        if self.p_numblocks[piece_idx] == len(self.p_blocks[piece_idx]):
            self.handle_piece(piece_idx)

    def handle_piece(self, piece_idx):
        """
        处理新增加的piece
        :param piece_idx: piece索引
        :return: None
        """
        # 从blocks中合成piece
        piece = b''.join(self.p_blocks[piece_idx])
        # 计算该piece的hash值
        cur_piece_hash = hashlib.sha1(piece).digest()
        # 若计算得到的hash值不能与metainfo中的匹配, 则认为该piece不正确
        if cur_piece_hash != self.metainfo.pieces[piece_idx]:
            self._handle_incorrect_piece(piece_idx)
            return
        # 若正确, 则将该piece写入磁盘
        self.p_blocks[piece_idx] = None
        self.writer.write_piece(piece_idx, piece)
        # 将该piece从未完成block list移除
        with self.exp_p_blocks_lock:
            self.exp_p_blocks.pop(piece_idx)

    def _handle_incorrect_piece(self, piece_idx):
        """
        处理不正确的piece
        :param piece_idx: piece索引
        :return: None
        """
        # 重置该piece块的block list
        self.p_blocks[piece_idx] = self._get_initial_blocks_list(piece_idx)
        # 同时重置该piece的未完成列表
        with self.exp_p_blocks_lock:
            self.exp_p_blocks[piece_idx] = {
                b_i for b_i in range(len(self.p_blocks[piece_idx]))}
            self.p_numblocks[piece_idx] = 0
