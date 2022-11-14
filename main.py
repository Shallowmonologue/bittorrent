from Client import Client
import argparse
import os
import sys


def is_valid_torrent_file(filename):
    """
    torrent文件名的异常性检查
    :param filename: 文件路径
    :return: bool类型
    """
    try:
        if not os.path.isfile(filename):
            raise RuntimeError(f"Exception: \"{filename}\" doesn't exist.")
        elif not filename.endswith(".torrent"):
            raise RuntimeError(f"Exception: \"{filename}\" is not a valid torrent file.")
    except RuntimeError as e:
        return False
    return True


def main():
    # 创建parser解析torrent文件
    my_parser = argparse.ArgumentParser(description='Torrent Client to download files using .torrent files.')
    # 添加parser输入变量
    my_parser.add_argument(action='store', dest='path', help='the path to the .torrent file')
    # 执行parse_args()方法获取torrent文件路径
    args = my_parser.parse_args()
    input_path = args.path
    # 进行文件异常校验
    if not is_valid_torrent_file(input_path):
        print('The file specified does not exist or is not a .torrent file.')
        sys.exit()

    # 执行下载
    Client(path=input_path).run()


if __name__ == '__main__':
    main()
