def _beats(a, b):
    """True if entry a ranks strictly lower than entry b. an entry can be (score, tie_breaker,item)."""
    if a[0] != b[0]:
        return a[0] < b[0]
    return a[1] < b[1]

class MinHeap:
    """Binary min-heap stored in a plain list. The parent of index i is (i - 1) // 2."""
    def __init__(self):
        self._data = []

    def __len__(self):
        return len(self._data)

    def peek(self):
        """Return smallest entry without removing it."""
        return self._data[0]

    def push(self, entry):
        self._data.append(entry)
        self._sift_up(len(self._data) - 1)

    def pop(self):
        """Remove and return smallest entry."""
        data = self._data
        top = data[0]
        last = data.pop()
        if data:
            data[0] = last
            self._sift_down(0)
        return top

    def _sift_up(self, i):
        data = self._data
        while i > 0:
            parent = (i - 1) // 2
            if _beats(data[i], data[parent]):
                data[i], data[parent] = data[parent], data[i]
                i = parent
            else:
                break

    def _sift_down(self, i):
        data = self._data
        n = len(data)
        while True:
            left = 2 * i + 1
            right = 2 * i + 2
            smallest = i
            if left < n and _beats(data[left], data[smallest]):
                smallest = left
            if right < n and _beats(data[right], data[smallest]):
                smallest = right
            if smallest == i:
                break
            data[i], data[smallest] = data[smallest], data[i]
            i = smallest


def top_k(items, k, key_fn, largest=True):
    """Return k best items, best first."""
    if k <= 0:
        return []
    heap = MinHeap()
    seq = 0
    for item in items:
        key = key_fn(item)
        if key is None:
            continue
        score = key if largest else -key
        seq += 1
        entry = (score, -seq, item)

        if len(heap) < k:
            heap.push(entry)
        elif _beats(heap.peek(), entry):
            heap.pop()
            heap.push(entry)

    result = [None] * len(heap)
    for i in range(len(result) - 1, -1, -1):
        result[i] = heap.pop()[2]
    return result


# ------------------------------------------------------
# Self-test: python backend/algorithms.py
# ------------------------------------------------------

if __name__ == "__main__":
    import random
    import time

    random.seed(1)
    for trial in range(300):
        n = random.randint(0, 60)
        k = random.randint(0,12)
        data =[{"id": i, "v": random.choice([None, random.randint(0, 15)])} for i in range(n)]
        for largest in (True, False):
            got = top_k(data, k, lambda d: d["v"], largest)
            valid = [d for d in data if d["v"] is not None]
            expected = sorted(valid, key=lambda d: (-d["v"] if largest else d["v"], d["id"]))[:k]
            assert [d["id"] for d in got] == [d["id"] for d in expected], (trial, largest, got, expected)
    print("correctness: 300 random trials x 2 directions passed (including ties and missing values)")
 
    big = [random.random() for _ in range(1_000_000)]
    t = time.perf_counter()
    top_k(big, 10, lambda x: x)
    t_heap = time.perf_counter() - t
    t = time.perf_counter()
    sorted(big, reverse=True)[:10]
    t_sort = time.perf_counter() - t
    print(f"1,000,000 numbers, top 10:  hand-made heap {t_heap:.2f}s   full sort {t_sort:.2f}s")                                           


