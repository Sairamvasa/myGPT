class MemoryStore:
    def __init__(self):
        self._entries = []

    def add(self, entry: dict):
        self._entries.append(entry)

    def get_recent(self, limit: int = 10):
        return self._entries[-limit:]

    def clear(self):
        self._entries.clear()
