"""Optional read-only RAR backend using system libarchive; no extraction to disk."""
from __future__ import annotations
import ctypes
import ctypes.util
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    filename: str
    file_size: int


class LibArchiveRAR:
    """Reads a RAR through libarchive. Enforces decompressed byte limits."""
    def __init__(self,path: Path):
        soname=ctypes.util.find_library("archive")
        if not soname:raise RuntimeError("System libarchive unavailable")
        self.path=str(path)
        self.lib=ctypes.CDLL(soname)
        lib=self.lib
        lib.archive_read_new.restype=ctypes.c_void_p
        lib.archive_read_support_format_all.argtypes=[ctypes.c_void_p]
        lib.archive_read_support_filter_all.argtypes=[ctypes.c_void_p]
        lib.archive_read_open_filename.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t]
        lib.archive_read_next_header.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
        lib.archive_entry_pathname.argtypes=[ctypes.c_void_p]
        lib.archive_entry_pathname.restype=ctypes.c_char_p
        lib.archive_entry_size.argtypes=[ctypes.c_void_p]
        lib.archive_entry_size.restype=ctypes.c_int64
        lib.archive_read_data.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t]
        lib.archive_read_data.restype=ctypes.c_ssize_t
        lib.archive_read_free.argtypes=[ctypes.c_void_p]
        lib.archive_error_string.argtypes=[ctypes.c_void_p]
        lib.archive_error_string.restype=ctypes.c_char_p
        self._infos=self._list_entries()

    def _error(self,ptr):
        msg=self.lib.archive_error_string(ptr) or b"libarchive read error"
        return msg.decode("utf-8","replace")

    def _open(self):
        ptr=self.lib.archive_read_new()
        if not ptr:raise RuntimeError("libarchive allocation failed")
        try:
            self.lib.archive_read_support_format_all(ptr)
            self.lib.archive_read_support_filter_all(ptr)
            result=self.lib.archive_read_open_filename(ptr,self.path.encode("utf-8"),65536)
            if result<0:raise RuntimeError(self._error(ptr))
            return ptr
        except Exception:
            self.lib.archive_read_free(ptr)
            raise

    def _headers(self,ptr):
        header=ctypes.c_void_p()
        while True:
            result=self.lib.archive_read_next_header(ptr,ctypes.byref(header))
            if result==1:break
            if result<0:raise RuntimeError(self._error(ptr))
            raw=self.lib.archive_entry_pathname(header)
            if raw is None:raise RuntimeError("RAR item has no name")
            yield raw.decode("utf-8","replace"),int(self.lib.archive_entry_size(header))

    def _list_entries(self):
        ptr=self._open()
        try:return [Entry(n,s) for n,s in self._headers(ptr)]
        finally:self.lib.archive_read_free(ptr)

    def infolist(self):
        return self._infos

    def read(self,filename:str,max_bytes:int):
        ptr=self._open()
        try:
            for name,size in self._headers(ptr):
                if name!=filename:continue
                if size>max_bytes:raise ValueError(f"RAR entry too large: {name}")
                return self._consume(ptr,max_bytes,name)
            raise KeyError(filename)
        finally:self.lib.archive_read_free(ptr)

    def _consume(self,ptr,max_bytes,name):
        chunks=bytearray()
        buf=ctypes.create_string_buffer(65536)
        while True:
            n=self.lib.archive_read_data(ptr,buf,len(buf))
            if n<0:raise RuntimeError(self._error(ptr))
            if n==0:break
            if len(chunks)+n>max_bytes:
                raise ValueError(f"RAR entry too large: {name}")
            chunks.extend(buf.raw[:n])
        return bytes(chunks)

    def iter_files(self,names:set[str],max_bytes:int):
        ptr=self._open()
        try:
            for name,size in self._headers(ptr):
                if name not in names:continue
                if size>max_bytes:raise ValueError(f"RAR entry too large: {name}")
                yield name,self._consume(ptr,max_bytes,name)
        finally:self.lib.archive_read_free(ptr)

    def close(self):
        pass
