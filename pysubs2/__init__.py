from . import attachments, cli, exceptions, formats, time
from .attachments import AttachmentMapping
from .common import VERSION, Alignment, Color
from .exceptions import *
from .formats import whisper
from .ssaevent import SSAEvent
from .ssafile import SSAFile
from .ssastyle import SSAStyle

__all__ = [
    "VERSION",
    "Alignment",
    "AttachmentMapping",
    "Color",
    "SSAEvent",
    "SSAFile",
    "SSAStyle",
    "attachments",
    "cli",
    "exceptions",
    "formats",
    "load",
    "load_from_whisper",
    "make_time",
    "time",
    "whisper",
]

#: Alias for :meth:`SSAFile.load()`.
load = SSAFile.load

#: Alias for :meth:`pysubs2.whisper.load_from_whisper()`.
load_from_whisper = whisper.load_from_whisper

#: Alias for :meth:`pysubs2.time.make_time()`.
make_time = time.make_time

#: Alias for `pysubs2.common.VERSION`.
__version__ = VERSION
