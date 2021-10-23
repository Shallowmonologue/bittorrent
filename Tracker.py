# Step 2: Send request to tracker and parse the reply

import random
from urllib.parse import urlencode
from urllib import request
import bencodepy
import Torrent


class Tracker:
    """
    More info: https://wiki.theory.org/index.php/BitTorrentSpecification#Tracker_Request_Parameters
    """

    def __init__(self, torrent):
        self.torrent = torrent
        self.peer_id = self._generate_peer_id()

    def connect(self, first=None, uploaded=0, downloaded=0):
        """
        Make announcement call to the tracker with the current client torrent stats.
        """
        params = self._get_request_params(first, uploaded, downloaded)

        tracker_url = self.torrent.announce + '?' + urlencode(params)
        print(f"Connecting to tracker at:: {tracker_url} ")
        res = request.urlopen(tracker_url).read()

        return bencodepy.decode(res)

    @staticmethod
    def _generate_peer_id():
        """
        https://wiki.theory.org/BitTorrentSpecification#peer_id
        """
        return "-AZ2060-" + "".join([str(random.randint(0, 9)) for _ in range(12)])

    @staticmethod
    def check_for_error(tracker_response):
        try:
            message = tracker_response.decode("utf-8")
            if "failure" in message:
                raise ConnectionError(f"Unable to connect to tracker: {message}")
        except UnicodeDecodeError:
            pass

    def _get_request_params(self, first=None, uploaded=0, downloaded=0):
        """
        Returns the URL request parameters to be sent to tracker
        """
        params = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.peer_id,
            'uploaded': uploaded,
            'downloaded': downloaded,
            'port': 6889,
            'left': self.torrent.total_length - downloaded,
            'compact': 1
        }

        if first:
            params['event'] = 'started'

        return params


class TrackerResponse:
    """
    More info: https://wiki.theory.org/BitTorrentSpecification#Tracker_Response
    """

    def __init__(self, tracker_response):
        self.tracker_response = tracker_response

    @property
    def failure(self):
        if b"failure reason" in self.tracker_response:
            return self.tracker_response[b"failure reason"].decode("utf-8")
        return None

    @property
    def warning(self):
        if b"warning message" in self.tracker_response:
            return self.tracker_response[b"warning message"].decode("utf-8")
        return None

    @property
    def interval(self):
        """
        The interval in seconds that the client should wait before sending
        periodic calls to the tracker
        """
        return self.tracker_response.get(b"interval", 0)

    @property
    def complete(self):
        """
        Number of peers with complete file i.e seeders
        """
        return self.tracker_response.get(b"complete", 0)

    @property
    def incomplete(self):
        """
        Number of non-seeder peers i.e leechers
        """
        return self.tracker_response.get(b"incomplete", 0)

    @property
    def peers(self):
        """
        Get the appropriate peers from the tracker response.
        """
        peers = self.tracker_response[b"peers"]

        def convert_ip(ip):
            return '{}.{}.{}.{}'.format(*ip)

        def dict_model():
            return [{k.decode(): convert_ip(v) if k == b'ip' else v
                     for k, v in peer.items()} for peer in peers]

        def binary_model():
            chunks = [peers[i:i + 6] for i in range(0, len(peers), 6)]

            return [{'ip': convert_ip(chunk[:4]),
                     'port': int.from_bytes(chunk[4:], byteorder='big')}
                    for chunk in chunks]

        if isinstance(peers, list):
            return dict_model()
        elif isinstance(peers, bytes):
            return binary_model()
        else:
            raise ValueError('Unsupported peer model.')

    def __str__(self):
        return f"incomplete (leechers): {self.incomplete}\n" \
               f"complete (peers): {self.complete}\n" \
               f"interval (sec): {self.interval}\n" \
               f"peers ip:port: \n{self.peers}\n"


torrent = Torrent.Torrent("ubuntu.torrent")
print(torrent)
tracker = Tracker(torrent)
res = tracker.connect()
print(TrackerResponse(res))
