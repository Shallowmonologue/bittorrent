import re
import socket
import struct
import sys
import traceback
import requests

import Bencode
from Config import SETTINGS

# 判断当前announce url链接是否为UDP格式
UDP_REGEX = re.compile(r'udp://[(\[]?(.+?)[)\]]?:([\d]{1,5})(?![\d:])')


def get_peers_list_by_torrent_metainfo(metainfo):
    """
    通过metainfo信息，获取http或者udp的peer列表
    :param metainfo: metainfo
    :return: [(ip,port)]的元组列表
    """
    for announce in metainfo.announce_list:
        try:
            if announce.startswith('http'):
                get_method = _get_peers_from_http_tracker
            elif announce.startswith('udp'):
                get_method = _get_peers_from_udp_tracker
            else:
                continue
            return get_method(announce, metainfo)
        except Exception:
            traceback.print_exc(file=sys.stdout)
            continue
    raise PeersFindingError('Could not find peers!')


def _parse_udp_announce_url(announce):
    """
    得到annouce的链接信息
    :param announce: announce url链接
    :return: host ip
    """
    match = re.search(UDP_REGEX, announce)
    host = match.group(1)
    str_port = match.group(2)
    port = 80 if str_port == '' else int(str_port)
    return host, port


def _get_peers_from_http_tracker(announce, metainfo):
    """
    从HTTP tracker得到peer的信息
    :param announce: HTTP announce的url链接
    :param metainfo: metainfo
    :return: [(ip,port)]的元组列表
    """
    # 向http tracker发送请求，并解析该响应
    response = requests.get(announce, _get_http_request_args(metainfo),
                            timeout=SETTINGS['timeout'])

    # 解析bencode的响应
    peers = Bencode.decode(response.content)

    # 处理binary类型的peer数据
    if isinstance(peers[b'peers'], bytes):
        peers = _get_peers_bin_model(peers[b'peers'])
    # 处理字典列表类型的peer数据
    else:
        peers = _get_peers_list_model(peers[b'peers'])
    return peers


def _get_http_request_args(metainfo):
    """
    返回对HTTP tracker请求时用到的参数
    :param metainfo:metainfo
    :return:请求参数的字典
    """
    request = {
        'info_hash': metainfo.info_hash,
        'peer_id': SETTINGS['peer_id'],
        'port': SETTINGS['port'],
        'uploaded': '0', 'downloaded': '0', 'left': metainfo.length,
        'compact': '1', 'no_peer_id': '1', 'numwant': SETTINGS['numwant']
    }
    return request


def _get_peers_from_udp_tracker(announce, metainfo):
    """
    从UDP tracker得到peer的信息
    :param announce: UDP announce的url链接
    :param metainfo: metainfo
    :return: [(ip,port)]的元组列表
    """
    # 建立一个连接UDP tracker的UDP套接字
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        # 设置超时参数
        s.settimeout(SETTINGS['timeout'])
        # 获取announce的host port
        host, port = _parse_udp_announce_url(announce)
        # 连接到announce
        s.connect((host, port))
        '''
        connect request:
        Offset  Size            Name            Value
        0       64-bit integer  protocol_id     0x41727101980 // magic constant
        8       32-bit integer  action          0 // connect
        12      32-bit integer  transaction_id
        16
        '''
        # 形成连接请求
        transaction_id = b'\x00\x00\x00\xff'  # 随机初始化transaction_id
        req = b''.join((b'\x00\x00\x04\x17\x27\x10\x19\x80',  # protocol_id
                        b'\x00\x00\x00\x00',
                        transaction_id))
        # 发送request请求
        s.send(req)
        '''
        connect response:
        Offset  Size            Name            Value
        0       32-bit integer  action          0 // connect
        4       32-bit integer  transaction_id
        8       64-bit integer  connection_id
        16
        '''
        # 接收responce
        res = s.recv(16)
        # 获取IPv4 announce请求
        req = _get_udp_announce_request(res[8:16], transaction_id, metainfo)
        # 发送IPv4 announce请求
        s.send(req)
        # 接收IPv4 announce请求
        res = s.recv(SETTINGS['max_ans_size'])
        # IPV4 响应包含ip和port 但有20位偏移（二进制下）
        return _get_peers_bin_model(res[20:])


def _get_udp_announce_request(connection_id, transaction_id, metainfo):
    """
    通过connection_id,transaction_id和metainfo，返回IPV4连接请求
    :param connection_id: 请求时的connection_id
    :param transaction_id: 请求时的transaction_id
    :param metainfo: metainfo
    :return: bytes类型的UDP请求
    """

    """
    Offset  Size    Name    Value
    0       64-bit integer  connection_id
    8       32-bit integer  action          1 // announce
    12      32-bit integer  transaction_id
    16      20-byte string  info_hash
    36      20-byte string  peer_id
    56      64-bit integer  downloaded
    64      64-bit integer  left
    72      64-bit integer  uploaded
    80      32-bit integer  event           0 // 0: none; 1: completed; 2: started; 3: stopped
    84      32-bit integer  IP address      0 // default
    88      32-bit integer  key
    92      32-bit integer  num_want        -1 // default
    96      16-bit integer  port
    98
    """
    req_list = [
        connection_id,  # connection_id
        b'\x00\x00\x00\x01',  # action: announce = 1
        transaction_id,  # transaction_id
        metainfo.info_hash,  # info_hash
        SETTINGS['peer_id'],  # peer_id
        b'\x00\x00\x00\x00\x00\x00\x00\x00'  # downloaded
    ]

    hex_metainfo_len = hex(metainfo.length)[2:]
    full_hex_metainfo_len = ('0' * (16 - len(hex_metainfo_len)) +
                             hex_metainfo_len)
    req_list.append(bytes.fromhex(full_hex_metainfo_len))  # left

    req_list.append(b'\x00\x00\x00\x00\x00\x00\x00\x00')  # uploaded
    req_list.append(b'\x00\x00\x00\x00')  # event (none)
    req_list.append(b'\x00\x00\x00\x00')  # IP address (default)
    req_list.append(b'\x00\x00\x00\x00')  # key
    req_list.append(struct.pack('!L', SETTINGS['numwant']))  # num_want
    req_list.append(b'\x00\x00\x1a\xe1')  # port
    return b''.join(req_list)


def _get_peers_list_model(peers_list):
    """
    返回字典列表的peer列表
    :param peers_list:字典列表[{b'ip':<ip>,b'port':<port>}]
    :return:[(ip,port),..]的元组列表
    """
    res_peers = []
    for peers_dict in peers_list:
        res_peers.append((peers_dict[b'ip'].decode(), peers_dict[b'port']))
    return res_peers


def _get_peers_bin_model(data):
    """
    返回binary类型的peer列表
    :param data:bytes类型的peer数据
    :return:[(ip,port),..]的元组列表
    """
    # 每6位是一组(ip,port),前四个ip，后两个port
    chunks = [data[i:i + 6] for i in range(0, len(data), 6)]
    return [(_get_ip(chunk[:4]),
             int.from_bytes(chunk[4:], byteorder='big'))
            for chunk in chunks]


def _get_ip(bin_ip):
    """
    从bytes类型返回IP字符串
    :param bin_ip: bytes类型的IP
    :return: IP字符串
    """
    res = []
    for i in range(4):
        res.append(str(bin_ip[i]))
    return '.'.join(res)


class PeersFindingError(Exception):
    pass
