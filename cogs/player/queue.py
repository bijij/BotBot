from pathlib import Path
from random import choice

from typing import Optional

from .track import Track


class Queue:

    def __init__(self, config=None):
        self.config = config or dict()
        self.requests = list()

    def next_track(self) -> Optional[Track]:
        if self.requests:
            return self.requests.pop(0)
        return None

    def add_request(self, track: Track, *, at_start: bool = False):
        """Adds a track to the list of requests.

        Args:
            track (Track): The track to add to the requests pool.
            user (discord.User): The user who requested the track.
        Kwargs:
            at_start (bool): Determines wether the track should be added to the start of the queue.

        """
        if at_start:
            self.requests.insert(0, track)
        else:
            self.requests.append(track)
