import struct
from enum import Enum
from settings import SETTINGS


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
    pstrlen = b'\x13'
    pstr = SETTINGS['protocol_name']
    reserved = b'\x00' * 8
    peer_id = SETTINGS['peer_id']

    return pstrlen + pstr + reserved + info_hash + peer_id


class MessageId(Enum):
    KEEP_ALIVE = -1
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7
    CANCEL = 8
    PORT = 9


# General Message Format: <length prefix><message ID><payload>
def build_message(message_id, **args):
    """
    Builds a message from the given message_id and the args.
    :param message_id: message_id
    :param args: zero or more keyword arguments
    :return: bytes encoded message
    """
    # CHOKE, UNCHOKE, INTERESTED and NOT_INTERESTED don't have any payload and have msg_len = 1
    if message_id in {MessageId.CHOKE,
                      MessageId.UNCHOKE,
                      MessageId.INTERESTED,
                      MessageId.NOT_INTERESTED}:
        msg_len = b'\x00\x00\x00\x01'
        payload = b''

    # have: <len=0005><id=4><piece index>
    elif message_id == MessageId.HAVE:
        msg_len = b'\x00\x00\x00\x05'
        payload = struct.pack('!L', args['piece_index'])

    # request: <len=0013><id=6><index><begin><length>
    elif message_id == MessageId.REQUEST:
        msg_len = b'\x00\x00\x00\x0d'
        payload = (struct.pack('!L', args['piece_index']) +
                   struct.pack('!L', args['offset']) +
                   struct.pack('!L', args['block_len']))

    elif message_id in {MessageId.BITFIELD,
                        MessageId.PIECE,
                        MessageId.CANCEL,
                        MessageId.PORT}:  # bitfield, piece, cancel, port
        raise NotImplementedError()

    # keep-alive: <len=0000>
    elif message_id == MessageId.KEEP_ALIVE:
        return b'\x00\x00\x00\x00'

    else:
        raise UnknownMessageType()

    message_id_bytes = struct.pack('!B', message_id)
    return msg_len + message_id_bytes + payload


class UnknownMessageType(Exception):
    pass
