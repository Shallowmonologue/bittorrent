import re
import socket
import struct
import sys
import traceback
import requests
import bencodepy

from settings import SETTINGS

# regex to identify if announce url is UDP
UDP_REGEX = re.compile(r'udp://[(\[]?(.+?)[)\]]?:([\d]{1,5})(?![\d:])')


def get_peers_list_by_torrent_metainfo(metainfo):
    """
    Get peers list from either HTTP or UDP tracker using metainfo
    :param metainfo: metainfo
    :return: List of tuples in the form [(ip, port), ...]
    """
    for announce in metainfo.announce_list:
        try:
            if announce.startswith('http'):
                get_method = _get_peers_from_http_tracker
            else:
                get_method = _get_peers_from_udp_tracker
            if get_method is None:
                continue
            return get_method(announce, metainfo)
        except Exception:
            # traceback.print_exc(file=sys.stdout)
            continue
    raise PeersFindingError('Could not find peers!')


def _parse_udp_announce_url(announce):
    """
    Get host and ip from the UDP announce url.
    :param announce: announce url
    :return: host and ip
    """
    match = re.search(UDP_REGEX, announce)
    host = match.group(1)
    str_port = match.group(2)
    port = 80 if str_port == '' else int(str_port)
    return host, port


def _get_peers_from_http_tracker(announce, metainfo):
    """
    Get the peers from the HTTP tracker.
    :param announce: HTTP announce url
    :param metainfo: metainfo
    :return: List of tuples in the form [(ip, port), ...]
    """
    # sending request to http tracker and parsing the response
    response = requests.get(announce, _get_http_request_args(metainfo),
                            timeout=SETTINGS['timeout'])

    # parse the bencoded reply and check for any errors
    peers = bencodepy.decode(response.content)
    check_for_error(peers)

    # binary model of peers
    if isinstance(peers[b'peers'], bytes):
        peers = _get_peers_bin_model(peers[b'peers'])
    # list of dictionary model of peers
    else:
        peers = _get_peers_list_model(peers[b'peers'])
    return peers


def check_for_error(tracker_response):
    """
    Check if tracker responded with an error in the response (applies only to HTTP tracker response)
    :param tracker_response: Response of the tracker
    :return: None
    """
    try:
        message = tracker_response.decode("utf-8")
        if "failure" in message:
            raise ConnectionError(f"Unable to connect to tracker: {message}")
    except UnicodeDecodeError:
        pass


def _get_http_request_args(metainfo):
    """
    Return request arguments to be used during HTTP tracker request
    :param metainfo: metainfo
    :return: Dictionary of request arguments
    """
    # More info: https://wiki.theory.org/index.php/BitTorrentSpecification#Tracker_Request_Parameters
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
    Get the peers from the UDP tracker.
    :param announce: UDP announce url
    :param metainfo: metainfo
    :return: List of tuples in the form [(ip, port), ...]
    """
    # More info: http://bittorrent.org/beps/bep_0015.html
    # open a UDP socket to connect to UDP tracker
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        # set timeout for the request
        s.settimeout(SETTINGS['timeout'])
        # get host and port from announce url
        host, port = _parse_udp_announce_url(announce)
        # try to connect the host
        s.connect((host, port))
        '''
        connect request:
        Offset  Size            Name            Value
        0       64-bit integer  protocol_id     0x41727101980 // magic constant
        8       32-bit integer  action          0 // connect
        12      32-bit integer  transaction_id
        16
        '''
        # form the connect request
        transaction_id = b'\x00\x00\x00\xff'  # random transaction_id
        req = b''.join((b'\x00\x00\x04\x17\x27\x10\x19\x80',  # protocol_id
                        b'\x00\x00\x00\x00',
                        transaction_id))
        # send the connect request
        s.send(req)
        '''
        connect response:
        Offset  Size            Name            Value
        0       32-bit integer  action          0 // connect
        4       32-bit integer  transaction_id
        8       64-bit integer  connection_id
        16
        '''
        # receive the response from the host
        res = s.recv(16)
        # get the IPv4 announce request
        req = _get_udp_announce_request(res[8:16], transaction_id, metainfo)
        # send the IPv4 announce request
        s.send(req)
        # receive the IPv4 announce response
        res = s.recv(SETTINGS['max_ans_size'])
        # IPv4 announce response contains peer ip and port offset 20 onwards (in binary model)
        return _get_peers_bin_model(res[20:])


def _get_udp_announce_request(connection_id, transaction_id, metainfo):
    """
    Return the IPv4 connect request from connection_id, transaction_id, metainfo
    :param connection_id: connection_id to be used during request
    :param transaction_id: transaction_id to be used during request
    :param metainfo: metainfo
    :return: UDP announce request in bytes
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
    Return peers list from list of dictionaries.
    :param peers_list: list of dictionaries in the form [{b'ip': <ip>, b'port': <port> ...}
    :return: List of tuples in the form [(ip, port), ...]
    """
    res_peers = []
    for peers_dict in peers_list:
        res_peers.append((peers_dict[b'ip'].decode(), peers_dict[b'port']))
    return res_peers


def _get_peers_bin_model(data):
    """
    Return peers list from binary data.
    :param data: Peers data in bytes
    :return: List of tuples in the form [(ip, port), ...]
    """
    chunks = [data[i:i + 6] for i in range(0, len(data), 6)]
    return [(_get_ip(chunk[:4]),
             int.from_bytes(chunk[4:], byteorder='big'))
            for chunk in chunks]


def _get_ip(bin_ip):
    """
    Return string IP from bytes.
    :param bin_ip: IP in bytes
    :return: string IP
    """
    res = []
    for i in range(4):
        res.append(str(bin_ip[i]))
    return '.'.join(res)


class PeersFindingError(Exception):
    pass
