import copy, json, time, uuid
from .wire import MAX_FRAME


class SnapshotError(ValueError):
    pass


class SnapshotStore:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.snapshots = {}
        self.cursors = {}

    def create(self, jobs, at_seq, limit=100):
        self._expire()
        # Bound concurrent snapshots; clients can retry expired snapshots.
        if len(self.snapshots) >= 4:
            oldest = next(iter(self.snapshots))
            del self.snapshots[oldest]
        sid = str(uuid.uuid4())
        self.snapshots[sid] = (self.clock(), copy.deepcopy(jobs), at_seq)
        return self._page(sid, 0, limit)

    def page(self, cursor, limit=100):
        self._expire()
        if cursor not in self.cursors:
            raise SnapshotError("snapshot_expired")
        sid, index = self.cursors[cursor]
        return self._page(sid, index, limit)

    def _expire(self):
        self.snapshots = {
            k: v for k, v in self.snapshots.items() if self.clock() - v[0] < 60
        }
        self.cursors = {k: v for k, v in self.cursors.items() if v[0] in self.snapshots}

    def _page(self, sid, index, limit):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SnapshotError("invalid_params")
        if sid not in self.snapshots:
            raise SnapshotError("snapshot_expired")
        _, jobs, seq = self.snapshots[sid]
        items = []
        size = 1024
        for item in jobs[index : index + limit]:
            item_size = len(json.dumps(item, ensure_ascii=False).encode()) + 1
            if size + item_size > MAX_FRAME:
                if not items:
                    raise SnapshotError("invalid_params")
                break
            items.append(item)
            size += item_size
        next_index = index + len(items)
        cursor = None
        if next_index < len(jobs):
            # Deterministic cursor per page position avoids growth on repeated reads.
            cursor = f"{sid}:{next_index}"
            self.cursors[cursor] = (sid, next_index)
        return {"snapshot_id": sid, "at_seq": seq, "jobs": items, "next_cursor": cursor}
