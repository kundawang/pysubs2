"""
Reading and writing of SubStation Alpha attachments (embedded fonts and images).

In ASS/SSA files, attachments are stored in the ``[Fonts]`` and ``[Graphics]``
sections as ASCII-armored binary data. Each attachment starts with a
``fontname:`` (fonts) or ``filename:`` (graphics) line, followed by one or more
lines of encoded data. The encoding is Aegisub's nonstandard variant of
uuencode:

- every three input bytes become four 6-bit values,
- each value is written as a character with ordinal ``value + 33``, so the
  alphabet is ``!`` through ````` (characters 33--96),
- lines are wrapped after 80 characters,
- a final partial group writes only ``remaining_bytes + 1`` characters
  (two, three or four characters for one, two or three remaining bytes).

The encoded lines are kept verbatim in :attr:`pysubs2.SSAFile.fonts_opaque`
and :attr:`pysubs2.SSAFile.graphics_opaque`, which lets unmodified attachments
be written back exactly as they were read. The helpers in this module decode
those lines to ``bytes`` and encode new payloads to lines.
"""

from collections.abc import Iterator, MutableMapping, Sequence
from pathlib import PurePath
from typing import TYPE_CHECKING, Literal, override

from .exceptions import AttachmentError

if TYPE_CHECKING:
    from .ssafile import SSAFile

__all__ = [
    "ATTACHMENT_LINE_LENGTH",
    "FONT_EXTENSIONS",
    "MAX_ATTACHMENT_SIZE",
    "AttachmentKind",
    "AttachmentMapping",
    "decode_attachment",
    "encode_attachment",
    "guess_attachment_kind",
    "normalize_attachment_kind",
    "validate_attachment",
    "validate_attachment_name",
]

#: Type of an attachment, matching the ``[Fonts]`` and ``[Graphics]`` sections.
AttachmentKind = Literal["font", "graphics"]

#: Default maximum decoded size of a single attachment (64 MiB).
#:
#: This is a safety limit against corrupt or malicious input. It can be
#: overridden with the ``max_attachment_size`` reader argument; pass ``None``
#: to disable the limit.
MAX_ATTACHMENT_SIZE: int = 64 * 1024 * 1024

#: Number of characters per encoded line, as produced by Aegisub.
ATTACHMENT_LINE_LENGTH: int = 80

#: File extensions which Aegisub treats as fonts; everything else is a graphic.
FONT_EXTENSIONS: frozenset[str] = frozenset({".ttf", ".ttc", ".otf", ".pfb"})

#: Character used for the 6-bit value zero; the alphabet ends at ``_MAX_CHAR``.
_CHAR_OFFSET = 33  # "!"
_MAX_CHAR = 96  # "`"

#: Characters of the ASS attachment alphabet.
_ALPHABET = frozenset(map(chr, range(_CHAR_OFFSET, _MAX_CHAR + 1)))

#: Encoded lines, optionally paired with their 1-based source line number.
type _NumberedLines = Sequence[tuple[str, int | None]]


def guess_attachment_kind(name: str) -> AttachmentKind:
    """
    Guess whether an attachment is a font or a graphic from its filename.

    This mirrors Aegisub's behaviour: known font extensions are treated as
    fonts, everything else goes into the ``[Graphics]`` section.
    """
    suffix = PurePath(name).suffix.lower()
    return "font" if suffix in FONT_EXTENSIONS else "graphics"


def normalize_attachment_kind(kind: str) -> AttachmentKind:
    """
    Normalize an attachment kind name.

    Accepts ``"font"``/``"fonts"`` and ``"graphics"``/``"graphic"``/
    ``"image"``/``"images"`` (case-insensitively).

    Raises:
        ValueError: The kind is not recognized.
    """
    normalized = kind.lower()
    if normalized in ("font", "fonts"):
        return "font"
    if normalized in ("graphics", "graphic", "image", "images"):
        return "graphics"
    raise ValueError(f"Unknown attachment kind {kind!r}, expected 'font' or 'graphics'")


def validate_attachment_name(name: str) -> str:
    """
    Check that an attachment name can be stored in an ASS file.

    Returns the name unchanged. Attachment names are stored as a single token
    on the heading line, so they must not be empty, must not have leading or
    trailing whitespace, and must not contain control characters.

    Raises:
        TypeError: The name is not a string.
        ValueError: The name is invalid.
    """
    if not isinstance(name, str):
        raise TypeError(f"Attachment name must be str, not {type(name).__name__}")
    if not name or not name.strip():
        raise ValueError("Attachment name must not be empty")
    if name != name.strip():
        raise ValueError(f"Attachment name {name!r} must not have leading or trailing whitespace")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError(f"Attachment name {name!r} must not contain control characters")
    return name


def _decoded_size(char_count: int) -> int:
    """
    Number of bytes represented by ``char_count`` encoded characters.

    A trailing group of one character is incomplete and contributes no byte;
    the final validation reports it as a truncated tail group.
    """
    full_groups, remainder = divmod(char_count, 4)
    if remainder <= 1:
        return full_groups * 3
    return full_groups * 3 + (remainder - 1)


def encode_attachment(
        data: bytes | bytearray | memoryview,
        line_length: int = ATTACHMENT_LINE_LENGTH,
) -> list[str]:
    """
    Encode binary data into ASS attachment lines.

    Arguments:
        data: Binary payload, eg. the contents of a font or image file.
        line_length: Number of characters per line. It must be a positive
            multiple of four, so that every line contains whole encoded
            groups; the default of 80 matches Aegisub.

    Returns:
        Encoded lines without line terminators. Empty data produces an
        empty list.

    Raises:
        ValueError: ``line_length`` is not a positive multiple of four.
    """
    if line_length <= 0 or line_length % 4 != 0:
        raise ValueError("Attachment line length must be a positive multiple of 4")

    payload = bytes(data)
    chars = bytearray()
    for i in range(0, len(payload), 3):
        chunk = payload[i:i + 3]
        b0 = chunk[0]
        b1 = chunk[1] if len(chunk) > 1 else 0
        b2 = chunk[2] if len(chunk) > 2 else 0
        value = (b0 << 16) | (b1 << 8) | b2
        values = (
            (value >> 18) & 0x3f,
            (value >> 12) & 0x3f,
            (value >> 6) & 0x3f,
            value & 0x3f,
        )
        # A partial group only carries the characters needed for its bytes:
        # two characters for one byte, three for two, four for three.
        chars.extend(value + _CHAR_OFFSET for value in values[:len(chunk) + 1])

    return [
        chars[i:i + line_length].decode("ascii")
        for i in range(0, len(chars), line_length)
    ]


def _number_lines(lines: Sequence[str], lineno: int | None) -> list[tuple[str, int | None]]:
    """Attach consecutive line numbers to lines, if a starting number is known."""
    if lineno is None:
        return [(line, None) for line in lines]
    return [(line, lineno + index) for index, line in enumerate(lines)]


def _check_numbered_lines(
        lines: _NumberedLines,
        *,
        name: str | None,
        max_size: int | None,
) -> int:
    """
    Validate encoded lines, returning the decoded size in bytes.

    Raises:
        AttachmentError: On characters outside the ASS alphabet, a truncated
            final group, or a payload larger than ``max_size``.
    """
    char_count = 0
    for text, lineno in lines:
        invalid = set(text) - _ALPHABET
        if invalid:
            # Report the first offending character in this line.
            bad = next(char for char in text if char not in _ALPHABET)
            raise AttachmentError(
                f"invalid character {bad!r} in attachment data "
                f"(expected characters {min(_ALPHABET)!r} through {max(_ALPHABET)!r})",
                name=name,
                line=lineno,
            )
        char_count += len(text)
        if max_size is not None and _decoded_size(char_count) > max_size:
            raise AttachmentError(
                f"attachment is too large ({_decoded_size(char_count)} bytes, "
                f"limit is {max_size} bytes)",
                name=name,
                line=lineno,
            )

    if char_count % 4 == 1:
        raise AttachmentError(
            "truncated attachment data: final group has only one character",
            name=name,
            line=lines[-1][1] if lines else None,
        )
    return _decoded_size(char_count)


def validate_attachment(
        lines: Sequence[str] | _NumberedLines,
        *,
        name: str | None = None,
        lineno: int | None = None,
        max_size: int | None = MAX_ATTACHMENT_SIZE,
) -> int:
    """
    Validate encoded attachment lines without decoding them.

    Arguments:
        lines: Encoded lines. Each item may be a string or a
            ``(line, line_number)`` pair; line numbers are included in error
            messages when available.
        name: Attachment name, included in error messages.
        lineno: Line number of the first line, used when the items are plain
            strings. The following lines are assumed to be consecutive.
        max_size: Maximum decoded size in bytes, or ``None`` for no limit.

    Returns:
        Decoded size in bytes.

    Raises:
        AttachmentError: Invalid character, truncated final group or
            oversized payload.
    """
    numbered: list[tuple[str, int | None]] = [
        item if isinstance(item, tuple) else (item, None)  # type: ignore[misc]
        for item in lines
    ]
    if lineno is not None and all(item_lineno is None for _, item_lineno in numbered):
        numbered = _number_lines([text for text, _ in numbered], lineno)
    return _check_numbered_lines(numbered, name=name, max_size=max_size)


def decode_attachment(
        lines: Sequence[str],
        *,
        name: str | None = None,
        lineno: int | None = None,
        max_size: int | None = MAX_ATTACHMENT_SIZE,
) -> bytes:
    """
    Decode ASS attachment lines into binary data.

    Arguments:
        lines: Encoded lines without line terminators, as stored in
            :attr:`pysubs2.SSAFile.fonts_opaque` and
            :attr:`pysubs2.SSAFile.graphics_opaque`.
        name: Attachment name, included in error messages.
        lineno: Line number of the first line in the source file, included in
            error messages.
        max_size: Maximum decoded size in bytes, or ``None`` for no limit.

    Returns:
        Decoded binary payload.

    Raises:
        AttachmentError: The data contains characters outside the ASS
            alphabet, ends in a truncated group, or exceeds ``max_size``.
    """
    numbered = _number_lines(lines, lineno)
    size = _check_numbered_lines(numbered, name=name, max_size=max_size)

    text = "".join(lines)
    output = bytearray(size)
    write = 0
    complete_length = len(text) - len(text) % 4

    for i in range(0, complete_length, 4):
        value = (
            ((ord(text[i]) - _CHAR_OFFSET) << 18)
            | ((ord(text[i + 1]) - _CHAR_OFFSET) << 12)
            | ((ord(text[i + 2]) - _CHAR_OFFSET) << 6)
            | (ord(text[i + 3]) - _CHAR_OFFSET)
        )
        output[write] = (value >> 16) & 0xff
        output[write + 1] = (value >> 8) & 0xff
        output[write + 2] = value & 0xff
        write += 3

    remainder = len(text) - complete_length
    if remainder >= 2:
        value = 0
        for char in text[complete_length:]:
            value = (value << 6) | (ord(char) - _CHAR_OFFSET)
        # Left-align the bits of the partial group, then keep whole bytes.
        value <<= (4 - remainder) * 6
        output[write] = (value >> 16) & 0xff
        if remainder == 3:
            output[write + 1] = (value >> 8) & 0xff

    return bytes(output)


class AttachmentMapping(MutableMapping[str, bytes]):
    """
    Decoded, mutable view of one kind of embedded attachment.

    This is the ``bytes``-valued view over :attr:`pysubs2.SSAFile.fonts_opaque`
    or :attr:`pysubs2.SSAFile.graphics_opaque`. Reading an item decodes its
    encoded lines; assigning an item encodes the binary payload. Attachments
    which are not assigned keep their original encoded lines and are written
    back verbatim.

    Instances are created by :attr:`pysubs2.SSAFile.fonts` and
    :attr:`pysubs2.SSAFile.graphics`; there is no need to construct them
    directly.
    """

    def __init__(self, subs: "SSAFile", kind: AttachmentKind) -> None:
        self._subs = subs
        self._kind: AttachmentKind = kind

    @property
    def _opaque(self) -> dict[str, list[str]]:
        if self._kind == "font":
            return self._subs.fonts_opaque
        return self._subs.graphics_opaque

    def __getitem__(self, name: str) -> bytes:
        try:
            lines = self._opaque[name]
        except KeyError:
            raise KeyError(name) from None
        # The lines were validated when the file was read; do not apply the
        # reader's size limit again (a file may have been read without one).
        return decode_attachment(lines, name=name, max_size=None)

    def __setitem__(self, name: str, data: bytes) -> None:
        validate_attachment_name(name)
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError(f"Attachment data must be bytes, not {type(data).__name__}")
        if self._kind == "font":
            self._subs.graphics_opaque.pop(name, None)
        else:
            self._subs.fonts_opaque.pop(name, None)
        # Assigning an existing key keeps its position in the dict, so an
        # edited attachment does not move relative to other attachments.
        self._opaque[name] = encode_attachment(data)

    def __delitem__(self, name: str) -> None:
        del self._opaque[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._opaque)

    def __len__(self) -> int:
        return len(self._opaque)

    @override
    def __contains__(self, name: object) -> bool:
        # Do not decode (which may fail on damaged data) just to answer this.
        return name in self._opaque

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._opaque)!r})"
