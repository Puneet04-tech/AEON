"""CPU metering: real process CPU time around the job, never wall clock."""
import time
from contextlib import contextmanager


class Meter:
    def __init__(self) -> None:
        self.cpu_seconds = 0.0
        self.wall_seconds = 0.0

    @contextmanager
    def measure(self):
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        try:
            yield self
        finally:
            self.cpu_seconds = round(time.process_time() - cpu_start, 6)
            self.wall_seconds = round(time.perf_counter() - wall_start, 6)
