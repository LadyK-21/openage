# Copyright 2015-2024 the openage authors. See copying.md for legal info.

"""
Provides Filecollection, a utility class for combining multiple file-like
objects to a FSLikeObject.
"""
from __future__ import annotations
import typing

from collections import OrderedDict
from io import UnsupportedOperation
from typing import NoReturn

from .abstract import FSLikeObject
from .path import Path

if typing.TYPE_CHECKING:
    from openage.util.filelike.stream import StreamFragment


class FileCollection(FSLikeObject):
    """
    FSLikeObject that holds several individual files.

    Uses lambdas to access files somewhere else on the fly.
    """

    def __init__(self):
        super().__init__()

        # stores lambdas to access the files
        # {name: open_r, open_w, size, mtime}, {name: subdir}
        self.rootentries = OrderedDict(), OrderedDict()

    @property
    def root(self):
        return FileCollectionPath(self, [])

    def get_direntries(self, parts=None, create: bool = False) -> tuple[OrderedDict, OrderedDict]:
        """
        Fetches the fileentries, subdirentries tuple for the given dir.

        If create == False, raises FileNotFoundError if the directory doesn't
        exist.

        Helper method for internal use.
        """
        if parts is None:
            parts = []

        entries = self.rootentries
        for idx, subdir in enumerate(parts):
            if subdir not in entries[1]:
                if create:
                    if subdir in entries[0]:
                        raise FileExistsError(b"/".join(parts[:idx + 1]))
                    entries[1][subdir] = OrderedDict(), OrderedDict()
                else:
                    raise FileNotFoundError(
                        "No such directory: " +
                        b"/".join(parts[:idx + 1]).decode(errors='replace'))

            entries = entries[1][subdir]

        return entries

    def add_fileentry(self, parts, fileentry: FileEntry):
        """
        Adds a file entry (and parent directory entries, if needed).

        This method should not be called directly; instead, use the
        add_file method of Path objects that were obtained from this.
        """
        if not parts:
            raise IsADirectoryError("FileCollection.root is a directory")

        entries = self.get_direntries(parts[:-1], create=True)

        name = parts[-1]
        if name in entries[1]:
            raise IsADirectoryError(b"/".join(parts))

        entries[0][name] = fileentry

    def get_fileentry(self, parts) -> FileEntry:
        """
        Gets a file entry. Helper method for internal use.
        """
        if not parts:
            raise IsADirectoryError(
                "FileCollection.root is a directory")

        entries = self.get_direntries(parts[:-1])

        name = parts[-1]

        if name in entries[1]:
            raise IsADirectoryError(b"/".join(parts))

        if name not in entries[0]:
            raise FileNotFoundError(b"/".join(parts))

        return entries[0][name]

    def open_r(self, parts: list[bytes]) -> StreamFragment:
        entry = self.get_fileentry(parts)

        open_r = entry.open_r()

        if open_r is None:
            raise UnsupportedOperation(
                "not readable: " +
                b"/".join(parts).decode(errors='replace'))

        return open_r

    def open_w(self, parts: list[bytes]):
        entry = self.get_fileentry(parts)

        open_w = entry.open_w()

        if open_w is None:
            raise UnsupportedOperation(
                "not writable: " +
                b"/".join(parts).decode(errors='replace'))

        return open_w

    def list(self, parts):
        fileentries, subdirs = self.get_direntries(parts)

        yield from subdirs
        yield from fileentries

    def filesize(self, parts) -> int:
        entry = self.get_fileentry(parts)

        return entry.size()

    def mtime(self, parts) -> float:
        entry = self.get_fileentry(parts)

        return entry.mtime()

    def mkdirs(self, parts) -> None:
        self.get_direntries(parts, create=True)

    def rmdir(self, parts) -> None:
        if not parts:
            raise UnsupportedOperation("can't rmdir FileCollection.root")

        parent_files, parent_dirs = self.get_direntries(parts[:-1])
        name = parts[-1]

        if name in parent_files:
            raise NotADirectoryError(b'/'.join(parts))

        try:
            files, subdirs = parent_dirs[name]
        except KeyError:
            raise FileNotFoundError(b'/'.join(parts)) from None

        if files or subdirs:
            raise IOError("Directory not empty: " +
                          b'/'.join(parts).decode(errors='replace'))

        del parent_dirs[name]

    def unlink(self, parts) -> None:
        if not parts:
            raise IsADirectoryError("FileCollection.root")

        parent_files, parent_dirs = self.get_direntries(parts[:-1])
        name = parts[-1]

        if name in parent_dirs:
            raise IsADirectoryError(b'/'.join(parts))

        try:
            del parent_files[name]
        except KeyError:
            raise FileNotFoundError(b'/'.join(parts)) from None

    def touch(self, parts) -> NoReturn:
        raise UnsupportedOperation("FileCollection.touch")

    def rename(self, srcparts, tgtparts) -> NoReturn:
        raise UnsupportedOperation("FileCollection.rename")

    def is_file(self, parts) -> bool:
        try:
            self.get_fileentry(parts)
            return True
        except IOError:
            return False

    def is_dir(self, parts) -> bool:
        try:
            self.get_direntries(parts)
            return True
        except IOError:
            return False

    def writable(self, parts) -> bool:
        try:
            _, open_w, _, _ = self.get_fileentry(parts)
            return open_w is not None
        except IOError:
            # generally, directories are not writable,
            # though some of the existing files inside might be.
            return False

    def watch(self, parts, callback) -> bool:
        del self, parts, callback  # unused
        return False

    def poll_watches(self) -> None:
        pass


class FileCollectionPath(Path):
    """
    Provides an additional method for adding a file at this path.
    """

    def add_file(
        self,
        open_r=None,
        open_w=None,
        filesize: int = None,
        mtime: float = None
    ) -> bool:
        """
        All parent directories are 'created', if needed.

        Any arguments may be None, and shall be callable otherwise.
        If open_r/open_w are None, the file will write-/read-only.
        """
        return self.fsobj.add_fileentry(
            self.parts, (open_r, open_w, filesize, mtime))

    def add_file_from_path(self, path: Path) -> None:
        """
        Like add_file, but uses a Path object instead of callables.
        """
        if path.writable():
            open_w = path.open_w
        else:
            open_w = None

        self.add_file(path.open_r, open_w, path.filesize, path.mtime)


class FileEntry:
    """
    Entry in a file collection archive.
    """
    # pylint: disable=no-self-use

    def open_r(self) -> StreamFragment:
        """
        Returns a file-like object for reading.
        """
        raise UnsupportedOperation("FileEntry.open_r")

    def open_w(self):
        """
        Returns a file-like object for writing.
        """
        raise UnsupportedOperation("FileEntry.open_w")

    def size(self) -> int:
        """
        Returns the size of the entr<.
        """
        raise UnsupportedOperation("FileEntry.size")

    def mtime(self) -> float:
        """
        Returns the modification time of the entry.
        """
        raise UnsupportedOperation("FileEntry.mtime")
