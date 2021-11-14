from CLI import CLI
import argparse
import os
import sys


def is_valid_torrent_file(filename):
    """
    Check if the given torrent file exists and is a torrent file.
    :param filename: file path
    :return: bool
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
    # Create the parser
    my_parser = argparse.ArgumentParser(description='Torrent Client to download files using .torrent files.')
    # Add the arguments
    my_parser.add_argument(action='store', dest='path', help='the path to the .torrent file')
    # Execute the parse_args() method
    args = my_parser.parse_args()
    input_path = args.path

    if not is_valid_torrent_file(input_path):
        print('The file specified does not exist or is not a .torrent file.')
        sys.exit()

    CLI(path=input_path).run()


if __name__ == '__main__':
    main()
