"""Bounded, read-only observations outside Wine and the managed runtime.

CPU ticks, thread states and wait channels help investigate a hang even when
all managed logging stops. They do not establish that the game is responsive.
No debugger attachment, signals, process memory, command lines or environment.
"""
import json
import os
from pathlib import Path
import time
from log_retention import rotate

MAX_PROCESSES = 8
MAX_THREADS = 96
MAX_LOG_BYTES = 1024 * 1024


def read_text(path, limit=8192):
    with path.open() as source:
        return source.read(limit)


def read_stat(path):
    # comm can contain spaces and closing parentheses; fields start after the
    # last ')'. Do not export comm (or any user-supplied process arguments).
    fields = read_text(path).rsplit(')', 1)[1].split()
    return {'state':fields[0], 'parent_pid':int(fields[1]),
            'cpu_ticks':int(fields[11])+int(fields[12]),
            'threads':int(fields[17]), 'start_ticks':int(fields[19]),
            'virtual_bytes':int(fields[20]), 'resident_pages':int(fields[21])}


class ClientHealth:
    def __init__(self, pid, logs, proc=Path('/proc'), interval=10):
        self.pid = pid
        self.logs = Path(logs)
        self.proc = Path(proc)
        self.interval = interval
        self.next_sample = 0
        self.previous = {}
        self.root_start = None
        self.disabled = False

    def snapshot(self):
        processes, pending, seen, ticks = [], [self.pid], set(), {}
        budget = MAX_THREADS
        while pending and len(processes) < MAX_PROCESSES:
            pid = pending.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            base = self.proc/str(pid)
            try:
                stat = read_stat(base/'stat')
                if pid == self.pid:
                    if self.root_start is not None and stat['start_ticks'] != self.root_start:
                        return {'availability':'pid_reused', 'processes':[]}
                    self.root_start = stat['start_ticks']
                record = dict(pid=pid, **stat)
                processes.append(record)
                key = (pid, stat['start_ticks'])
                ticks[key] = stat['cpu_ticks']
                record['cpu_delta_ticks'] = (stat['cpu_ticks']-self.previous[key]) if key in self.previous else None
                # Direct children cover Wine's loader child when present. This
                # is intentionally a bounded subtree, not every app process.
                try:
                    pending.extend(int(p) for p in read_text(base/'task'/str(pid)/'children').split()[:MAX_PROCESSES])
                except (OSError, ValueError):
                    record['children_unavailable'] = True
                record['thread_samples'] = []
                try:
                    with os.scandir(base/'task') as entries:
                        for entry in entries:
                            if not entry.name.isdigit():continue
                            if budget <= 0:break
                            budget -= 1
                            thread = Path(entry.path)
                            try:
                                state = read_stat(thread/'stat')
                                item = {'tid':int(entry.name), 'state':state['state'], 'cpu_ticks':state['cpu_ticks']}
                                key = (pid, int(entry.name), state['start_ticks'])
                                ticks[key] = state['cpu_ticks']
                                item['cpu_delta_ticks'] = state['cpu_ticks']-self.previous[key] if key in self.previous else None
                                try:item['wait_channel'] = read_text(thread/'wchan',128).strip()
                                except OSError:item['wait_channel'] = 'unavailable'
                                record['thread_samples'].append(item)
                            except (OSError, ValueError, IndexError):
                                continue # A thread can exit during the sample.
                except OSError:
                    record['threads_unavailable'] = True
            except (OSError, ValueError, IndexError):
                continue # Android may restrict /proc; this must never stop play.
        self.previous = ticks
        return {'availability':'available' if processes else 'unavailable_or_exited',
                'processes':processes, 'thread_limit_reached':budget == 0,
                'process_limit_reached':bool(pending)}

    def sample(self):
        now = time.monotonic()
        if self.disabled or now < self.next_sample:return
        self.next_sample = now+self.interval
        try:
            data = self.snapshot()
            data.update(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()), monotonic_seconds=round(now,2),
                        launcher_pid=self.pid, clock_ticks_per_second=os.sysconf('SC_CLK_TCK'),
                        page_bytes=os.sysconf('SC_PAGE_SIZE'))
            line = json.dumps(data,separators=(',',':'))+'\n'
            path = self.logs/'client-health.log'
            if path.is_symlink():raise ValueError('Log path cannot be a symlink')
            if path.exists() and path.stat().st_size+len(line.encode()) > MAX_LOG_BYTES:rotate(path)
            with path.open('a') as output:output.write(line)
        except (OSError, ValueError, IndexError):
            # Optional diagnostics must not turn an unreadable proc entry or
            # a full filesystem into a new client failure.
            self.disabled = True
