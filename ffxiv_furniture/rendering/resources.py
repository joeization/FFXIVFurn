"""Bounded decoded-asset cache with source-file change detection."""
from collections import OrderedDict
from threading import RLock
from pathlib import Path
import numpy as np


def file_stamp(path):
    try:
        s=Path(path).stat();return (s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    except FileNotFoundError:return None


def dependency_snapshot(paths):
    return {str(Path(p).absolute()):file_stamp(p) for p in paths}


def dependencies_current(snapshot):
    return all(file_stamp(p)==(tuple(stamp) if stamp is not None else None) for p,stamp in snapshot.items())


def _array_bytes(value,seen=None):
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value))
    if isinstance(value,np.ndarray):return value.nbytes
    if isinstance(value,dict):return sum(_array_bytes(v,seen) for v in value.values())
    if isinstance(value,(list,tuple)):return sum(_array_bytes(v,seen) for v in value)
    return 0


class DecodedAssetCache:
    """Optional process-local reuse; Assets itself remains a per-run loader.

    Stamps cover geometry, material and texture companions and missing lookup
    candidates, so newly extracted higher-priority files also invalidate entries.
    No catalog/app data is written. This is not an on-disk asset replacement.
    """
    def __init__(self,max_bytes=256*1024*1024,max_entries=128):
        self.max_bytes=max_bytes;self.max_entries=max_entries
        self._entries=OrderedDict();self._bytes=0;self._lock=RLock();self.hits=0;self.misses=0
    def get(self,key):
        with self._lock:
            entry=self._entries.get(key)
            if entry is not None:
                result,coverage,deps,nbytes=entry
                if dependencies_current(deps):
                    self._entries.move_to_end(key);self.hits+=1
                    return result,coverage,deps
                self._bytes-=nbytes;del self._entries[key]
            self.misses+=1
            return None
    def put(self,key,result,coverage,dependencies):
        nbytes=_array_bytes(result)
        with self._lock:
            old=self._entries.pop(key,None)
            if old:self._bytes-=old[3]
            if nbytes>self.max_bytes or self.max_entries<1:return
            self._entries[key]=(result,coverage,dependency_snapshot(dependencies),nbytes);self._bytes+=nbytes
            while self._entries and (len(self._entries)>self.max_entries or self._bytes>self.max_bytes):
                _,old=self._entries.popitem(last=False);self._bytes-=old[3]
    def stats(self):
        with self._lock:return dict(entries=len(self._entries),bytes=self._bytes,max_bytes=self.max_bytes,hits=self.hits,misses=self.misses)
    def clear(self):
        with self._lock:self._entries.clear();self._bytes=0;self.hits=self.misses=0
