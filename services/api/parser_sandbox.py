"""Unprivileged Linux filesystem/network restrictions for parser children.

Fail closed when kernel Landlock or libseccomp is unavailable. This confines
file access and networking; it is not a guarantee against kernel/library bugs.
"""
import ctypes
import ctypes.util
import os
from pathlib import Path
import platform
import sys


def restrict(work, code):
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
    handled = (1 << 15) - 1  # v3 filesystem ABI, including truncate/refer.
    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]
    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]
    rules = Ruleset(handled)
    descriptor = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if descriptor < 0:
        raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
    readonly = (1 << 0) | (1 << 2) | (1 << 3)
    locations = {str(Path(p).resolve()): readonly for p in (
        "/usr", "/lib", "/lib64", sys.prefix, sys.base_prefix,
        str(Path(code)/"services"), str(Path(code)/"packages"), "/etc/fonts",
        "/etc/ld.so.cache", "/dev/urandom", "/dev/random") if Path(p).exists()}
    locations[str(Path(work).resolve())] = handled & ~(1 | 64 | 512 | 1024 | 2048)
    if os.environ.get('CAESAR_OCR_HOME'):
        locations[str(Path(os.environ['CAESAR_OCR_HOME']).resolve())]=readonly
    locations["/dev/null"] = (1 << 1) | (1 << 2) | (1 << 14)
    try:
        for path, access in locations.items():
            if not Path(path).is_dir():
                access &= (1 | 2 | 4 | (1 << 14))
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(access, fd)
                if libc.syscall(445, descriptor, 1, ctypes.byref(rule), 0):
                    raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
            finally:
                os.close(fd)
        if libc.prctl(38, 1, 0, 0, 0) or libc.syscall(446, descriptor, 0):
            raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
    finally:
        os.close(descriptor)
    library = ctypes.util.find_library("seccomp")
    if not library:
        raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
    seccomp = ctypes.CDLL(library)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    context = seccomp.seccomp_init(0x7fff0000)
    if not context:
        raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
    try:
        for name in ("socket", "socketpair", "connect", "bind", "sendto", "sendmsg",
                     "ptrace", "process_vm_readv", "process_vm_writev", "pidfd_getfd",
                     "mount", "setns", "unshare", "bpf", "io_uring_setup", "open_by_handle_at"):
            number = seccomp.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and seccomp.seccomp_rule_add(context, 0x50001, number, 0):
                raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
        if seccomp.seccomp_load(context):
            raise RuntimeError("PARSER_ISOLATION_UNAVAILABLE")
    finally:
        seccomp.seccomp_release(context)
