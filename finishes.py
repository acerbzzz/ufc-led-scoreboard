"""Fetch the official result attached to a final bout, independently of display rotation."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from urllib.request import urlopen


def method_label(result):
    if not isinstance(result, dict):
        return ""
    return str(result.get("displayName") or result.get("shortDisplayName") or "").strip()


class ResultFeed:
    def __init__(self):
        self.worker = ThreadPoolExecutor(max_workers=2)
        self.pending = {}
        self.labels = {}
        self.retry = {}

    @staticmethod
    def lookup(key):
        event, bout = key
        url = ("https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/"
               "events/{}/competitions/{}/status").format(event, bout)
        with urlopen(url, timeout=5) as response:
            return method_label(json.load(response).get("result"))

    def update(self, card):
        for fight in card:
            key = fight.key
            if fight.state != "post" or not all(part.isdigit() for part in key) or len(key) != 2:
                continue
            if fight.method:
                continue
            if key in self.pending and self.pending[key].done():
                try:
                    label = self.pending[key].result()
                    if label:
                        self.labels[key] = label
                except (ValueError, OSError) as exc:
                    logging.debug("Result lookup failed: %s", exc)
                del self.pending[key]
                self.retry[key] = monotonic() + 60
            fight.method = self.labels.get(key, "")
            if not fight.method and key not in self.pending and monotonic() >= self.retry.get(key, 0):
                self.pending[key] = self.worker.submit(self.lookup, key)
