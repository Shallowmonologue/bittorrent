from dataclasses import dataclass
from typing import Union

# 得到标志位的unicode编码
COLON = ord(":") #冒号 ：
END_MARKER = ord("e") #结束标志 e
START_DICT = ord("d") #字典开始 d
START_INTEGER = ord("i") #整数开始 i
START_LIST = ord("l") #列表开始 l


@dataclass
class BencodedString:
    """处理bencode字符串的类"""

    def __init__(self, data):
        """构造函数，把数据转换为byte"""
        self.bytes = bytearray(data)

    def del_prefix(self, index):
        """删除指定长度的前缀"""
        del self.bytes[:index]

    def get_prefix(self, index):
        """得到指定长度的前缀"""
        return bytes(self.bytes[:index])


def _decode(data: BencodedString) -> Union[bytes, dict, int, list]:
    """将bencode字符串类转换为Python基本属性的对象
       参数：
            bencode字符串类型数据
       返回值：
            python基本对象
    """
    if not data.bytes:
        raise ValueError("Cannot decode an empty bencoded string.")

    if data.bytes[0] == START_DICT:
        return _decode_dict(data)

    if data.bytes[0] == START_LIST:
        return _decode_list(data)

    if data.bytes[0] == START_INTEGER:
        return _decode_int(data)

    if chr(data.bytes[0]).isdigit():
        return _decode_bytes(data)

    raise ValueError(
        "Cannot decode data, expected the first byte to be one of "
        f"'d', 'i', 'l' or a digit, got {chr(data.bytes[0])!r} instead."
    )

def _decode_bytes(data: BencodedString) -> bytes:
    """
    解码bytes类型开头的bencode字符串数据
    输入：
        bytes类型开头的bencode字符串
    返回值：
        解析的byte字符串
    """

    # 得到byte的长度，通过冒号分隔符找到
    delimiter_index = data.bytes.find(COLON)

    if delimiter_index > 0:
        length_prefix = data.get_prefix(delimiter_index)
        string_length = int(length_prefix.decode("ascii"))
        data.del_prefix(delimiter_index + 1)
    else:
        raise ValueError(
            "Cannot decode a byte string, it doesn't contain a delimiter. "
            "Most likely the bencoded string is incomplete or incorrect."
        )

    # 得到byte数据
    if len(data.bytes) >= string_length:
        result_bytes = data.get_prefix(string_length)
        data.del_prefix(string_length)
    else:
        raise ValueError(
            f"Cannot decode a byte string (prefix length "
            f"- {string_length}, real_length - {len(data.bytes)}. "
            "Most likely the bencoded string is incomplete or incorrect."
        )

    return result_bytes


def _decode_dict(data: BencodedString) -> dict:
    """
    解码dict类型开头的bencode字符串数据
    输入：
        dict类型开头的bencode字符串
    返回值：
        解析的dict对象
    """
    result_dict = {}
    data.del_prefix(1)

    while True:
        if data.bytes:
            if data.bytes[0] != END_MARKER:
                key = _decode(data)
                value = _decode(data)
                result_dict[key] = value
            else:
                data.del_prefix(1)
                break
        else:
            raise ValueError(
                "Cannot decode a dictionary, reached end of the bencoded "
                "string before the end marker was found. Most likely the "
                "bencoded string is incomplete or incorrect."
            )

    return result_dict


def _decode_int(data: BencodedString) -> int:
    """
    解码int类型开头的bencode字符串数据
    输入：
        int类型开头的bencode字符串
    返回值：
        解析的int数据
    """

    data.del_prefix(1)
    end_marker_index = data.bytes.find(END_MARKER)

    if end_marker_index > 0:
        result_bytes = data.get_prefix(end_marker_index)
        data.del_prefix(end_marker_index + 1)
    else:
        raise ValueError(
            "Cannot decode an integer, reached the end of the bencoded "
            "string before the end marker was found. Most likely the "
            "bencoded string is incomplete or incorrect."
        )

    return int(result_bytes.decode("ascii"))


def _decode_list(data: BencodedString) -> list:
    """
    解码list类型开头的bencode字符串数据
    输入：
        list类型开头的bencode字符串
    返回值：
        解析的list
    """
    result_list = []
    data.del_prefix(1)

    while True:
        if data.bytes:
            if data.bytes[0] != END_MARKER:
                result_list.append(_decode(data))
            else:
                data.del_prefix(1)
                break
        else:
            raise ValueError(
                "Cannot decode a list, reached end of the bencoded string "
                "before the end marker was found. Most likely the bencoded "
                "string is incomplete or incorrect."
            )

    return result_list


def _encode_bytes(source: bytes) -> bytes:
    """编码bytes对象到bencode字符串"""
    return str(len(source)).encode("ascii") + b":" + source


def _encode_dict(source: dict) -> bytes:
    """编码dict对象到bencode字符串"""
    result_data = b"d"

    for key, value in source.items():
        result_data += encode(key) + encode(value)

    return result_data + b"e"


def _encode_int(source: int) -> bytes:
    """编码int对象到bencode字符串"""
    return b"i" + str(source).encode("ascii") + b"e"


def _encode_list(source: list) -> bytes:
    """编码llist对象到bencode字符串"""
    result_data = b"l"

    for item in source:
        result_data += encode(item)

    return result_data + b"e"


def decode(data: bytes) -> Union[bytes, dict, int, list]:
    """
    bencode字符串转换为python类型
    输入：
         bytes类型数据
    返回值：
         Python类型对象
    """

    if not isinstance(data, bytes):
        raise ValueError(
            f"Cannot decode data, expected bytes, got {type(data)} instead."
        )
    return _decode(BencodedString(data))


def encode(data: Union[bytes, dict, int, list]) -> bytes:
    """
    python类型转换为bencode字符串
    输入：
         Python类型数据
    返回值：
         bencode类型对象
    """
    if isinstance(data, bytes):
        return _encode_bytes(data)

    if isinstance(data, dict):
        return _encode_dict(data)

    if isinstance(data, int):
        return _encode_int(data)

    if isinstance(data, list):
        return _encode_list(data)

    raise ValueError(
        f"Cannot encode data: objects of type {type(data)} are not supported."
    )

def readfile(fd):
    return decode(fd.read())