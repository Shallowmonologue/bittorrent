from TorrentMetainfo import TorrentMetainfo
from TrackerAPI import get_peers_list_by_torrent_metainfo

if __name__ == '__main__':
    # torrent file
    filename = "sintel.torrent"

    # extract metainfo from the torrent file
    metainfo = TorrentMetainfo(filename)
    print(metainfo)

    # get peers from the metainfo
    # if we get the socket.timeout, then tracker is not responsive
    peers = get_peers_list_by_torrent_metainfo(metainfo)
    print("Total peers:", len(peers))
    print(peers)
