"""Stubbed consistent hash manager for tests."""

import hashlib
from bisect import bisect_right
from typing import Dict, List, Set


class ConsistentHashManager:
    """Minimal consistent hash ring implementation to satisfy unit tests."""

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: Dict[int, str] = {}
        self.sorted_keys: List[int] = []
        self.nodes: Set[str] = set()

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: str):
        if node in self.nodes:
            return
        self.nodes.add(node)
        for i in range(self.virtual_nodes):
            h = self._hash(f"{node}:{i}")
            self.ring[h] = node
            self.sorted_keys.append(h)
        self.sorted_keys.sort()

    def remove_node(self, node: str):
        if node not in self.nodes:
            return
        self.nodes.remove(node)
        keys_to_remove = [k for k, v in self.ring.items() if v == node]
        for k in keys_to_remove:
            self.ring.pop(k, None)
        self.sorted_keys = sorted(self.ring.keys())

    def get_node_for_instrument(self, instrument_key: str) -> str:
        if not self.ring:
            return ""
        h = self._hash(instrument_key)
        idx = bisect_right(self.sorted_keys, h)
        if idx == len(self.sorted_keys):
            idx = 0
        return self.ring[self.sorted_keys[idx]]
