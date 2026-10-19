#!/usr/bin/env python3
"""Remove only exactly zero-area facets from a binary STL, without mesh repair.

Every finite binary32 coordinate is represented as an integer times 2**-149.
Cross products therefore use exact integer arithmetic, without tolerance,
underflow, or rounded subtraction. Normals are checked for finiteness but are
never recomputed. Each retained 50-byte facet record and the 80-byte header are
copied verbatim; only the little-endian facet count changes.

Input/output must be distinct regular-file paths on a POSIX system supporting
O_NOFOLLOW and directory-relative opens. Symlinks in any path component, parent
navigation (".."), and existing outputs are refused. On failure, a newly created
partial output is removed. Input changes detected during filtering are refused.

Facet data is streamed in bounded chunks. The exact removed-index report uses
O(number of removed facets) memory; indices are zero-based in the original STL.
No CAD packages, mesh libraries, or external dependencies are used.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import PurePath
import stat
import struct
import sys
from typing import BinaryIO


HEADER_BYTES = 80
PREFIX_BYTES = 84
FACET_BYTES = 50
_WORDS = struct.Struct("<12I")
_COUNT = struct.Struct("<I")


class STLFilterError(ValueError):
    """The source is not a safe, well-formed, finite binary STL."""


@dataclass(frozen=True)
class FilterReport:
    input_path: str
    output_path: str
    input_sha256: str
    output_sha256: str
    input_facet_count: int
    removed_facet_count: int
    retained_facet_count: int
    removed_facet_indices: tuple[int, ...]
    facet_index_base: int = 0

    def to_dict(self) -> dict:
        """Return the complete JSON-serializable audit report."""
        result = asdict(self)
        result["removed_facet_indices"] = list(self.removed_facet_indices)
        return result


def _integer_float32(word: int) -> int:
    """Return the exact binary32 value in units of 2**-149 (finite only)."""
    exponent = (word >> 23) & 0xFF
    significand = word & 0x7FFFFF
    if exponent:
        significand = (significand | 0x800000) << (exponent - 1)
    return -significand if word & 0x80000000 else significand


def _is_exactly_zero_area(words: tuple[int, ...]) -> bool:
    ax, ay, az, bx, by, bz, cx, cy, cz = (
        _integer_float32(word) for word in words[3:]
    )
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    return (
        uy * vz == uz * vy
        and uz * vx == ux * vz
        and ux * vy == uy * vx
    )


def _file_path(path: str | os.PathLike[str]) -> str:
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or raw.endswith(os.sep):
        raise STLFilterError("A nonempty file path without a trailing separator is required")
    if ".." in PurePath(raw).parts:
        raise STLFilterError("Parent navigation ('..') is refused in file paths")
    return os.path.abspath(raw)


def _open_parent(path: str) -> tuple[int, str]:
    """Open every directory without following symlinks, retaining the final fd."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise STLFilterError("Safe path handling requires POSIX O_NOFOLLOW and O_DIRECTORY")
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise STLFilterError("Safe path handling requires directory-relative file operations")
    parts = PurePath(path).parts
    if len(parts) < 2:
        raise STLFilterError("A regular-file path is required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(parts[0], flags)
    try:
        for component in parts[1:-1]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def _snapshot(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    while block := stream.read(1024 * 1024):
        digest.update(block)
    return digest.hexdigest()


def _remove_created_output(parent_fd: int, name: str, identity: tuple[int, int]) -> None:
    """Never unlink a file that has replaced the output we created."""
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) == identity:
        os.unlink(name, dir_fd=parent_fd)


def filter_binary_stl(
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    chunk_facets: int = 8192,
) -> FilterReport:
    """Filter a binary STL into a new file and return a complete audit report.

    Raises STLFilterError for invalid STL data/options and OSError for unsafe or
    unavailable filesystem paths. Never overwrites an output or changes input.
    A valid zero-facet STL is permitted, as is an output with zero facets.
    """
    if isinstance(chunk_facets, bool) or not isinstance(chunk_facets, int) or chunk_facets < 1:
        raise STLFilterError("chunk_facets must be a positive integer")
    source_path = _file_path(input_path)
    target_path = _file_path(output_path)
    if source_path == target_path:
        raise STLFilterError("Input and output paths must be distinct")

    with ExitStack() as stack:
        source_parent, source_name = _open_parent(source_path)
        stack.callback(os.close, source_parent)
        target_parent, target_name = _open_parent(target_path)
        stack.callback(os.close, target_parent)
        # O_NONBLOCK ensures an unexpected FIFO cannot hang before fstat rejects it.
        source_fd = os.open(
            source_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_parent
        )
        source = stack.enter_context(os.fdopen(source_fd, "rb"))
        source_info = os.fstat(source.fileno())
        if not stat.S_ISREG(source_info.st_mode):
            raise STLFilterError("Input must be a regular file")
        prefix = source.read(PREFIX_BYTES)
        if len(prefix) != PREFIX_BYTES:
            raise STLFilterError("Truncated binary STL: expected an 84-byte header and count")
        input_count = _COUNT.unpack_from(prefix, HEADER_BYTES)[0]
        expected_size = PREFIX_BYTES + FACET_BYTES * input_count
        if source_info.st_size != expected_size:
            raise STLFilterError(
                f"Binary STL length mismatch: count {input_count} requires {expected_size} "
                f"bytes, found {source_info.st_size}; truncation and trailing bytes are refused"
            )

        # O_EXCL refuses regular files, hard-link aliases, symlinks, and races.
        target_fd = os.open(
            target_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=target_parent,
        )
        target_info = os.fstat(target_fd)
        target_identity = (target_info.st_dev, target_info.st_ino)
        try:
            target = stack.enter_context(os.fdopen(target_fd, "w+b"))
            target.write(prefix)
            input_digest = hashlib.sha256(prefix)
            removed: list[int] = []
            index = 0
            while index < input_count:
                count = min(chunk_facets, input_count - index)
                block = source.read(count * FACET_BYTES)
                if len(block) != count * FACET_BYTES:
                    raise STLFilterError(f"Truncated binary STL at facet {index}")
                input_digest.update(block)
                retained = bytearray()
                for local_index in range(count):
                    offset = local_index * FACET_BYTES
                    words = _WORDS.unpack_from(block, offset)
                    for component, word in enumerate(words):
                        if (word & 0x7F800000) == 0x7F800000:
                            kind = "normal" if component < 3 else "coordinate"
                            raise STLFilterError(
                                f"Nonfinite {kind} in facet {index + local_index} "
                                f"(component {component})"
                            )
                    if _is_exactly_zero_area(words):
                        removed.append(index + local_index)
                    else:
                        retained.extend(block[offset : offset + FACET_BYTES])
                target.write(retained)
                index += count

            if source.read(1):
                raise STLFilterError("Trailing bytes appeared while reading the binary STL")
            if _snapshot(os.fstat(source.fileno())) != _snapshot(source_info):
                raise STLFilterError("Input changed while filtering; output discarded")
            retained_count = input_count - len(removed)
            target.seek(HEADER_BYTES)
            target.write(_COUNT.pack(retained_count))
            target.flush()
            os.fsync(target.fileno())
            target.seek(0)
            output_digest = _sha256_stream(target)
            output_info = os.fstat(target.fileno())
            if output_info.st_size != PREFIX_BYTES + FACET_BYTES * retained_count:
                raise STLFilterError("Unexpected output length; output discarded")
            return FilterReport(
                input_path=source_path,
                output_path=target_path,
                input_sha256=input_digest.hexdigest(),
                output_sha256=output_digest,
                input_facet_count=input_count,
                removed_facet_count=len(removed),
                retained_facet_count=retained_count,
                removed_facet_indices=tuple(removed),
            )
        except BaseException:
            _remove_created_output(target_parent, target_name, target_identity)
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Existing binary STL; never modified")
    parser.add_argument("output", help="New output STL; must not already exist")
    parser.add_argument("--chunk-facets", type=int, default=8192, help="Facets per streaming chunk")
    arguments = parser.parse_args(argv)
    try:
        report = filter_binary_stl(
            arguments.input, arguments.output, chunk_facets=arguments.chunk_facets
        )
    except (STLFilterError, OSError) as error:
        print(f"zero_area_filter: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
