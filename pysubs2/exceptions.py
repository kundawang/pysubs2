from typing import Any

__all__ = [
    "AttachmentError",
    "FormatAutodetectionError",
    "Pysubs2Error",
    "UnknownFPSError",
    "UnknownFileExtensionError",
    "UnknownFormatIdentifierError",
]


class Pysubs2Error(Exception):
    """Base class for pysubs2 exceptions."""


class UnknownFPSError(Pysubs2Error):
    """Framerate was not specified and couldn't be inferred otherwise."""


class AttachmentError(Pysubs2Error):
    """
    Invalid embedded attachment (font or image) in a SubStation file.

    Raised when an attachment in the ``[Fonts]`` or ``[Graphics]`` section
    cannot be decoded (invalid encoding character, truncated final group,
    oversized payload, duplicate or empty name, data in the wrong section),
    or when an invalid name or payload is passed to the attachment API.

    Attributes:
        message (str): Error description without location details.
        name (str | None): Attachment name, if known.
        line (int | None): Source line number (1-based) of the offending
            line, if known.
    """

    def __init__(self, message: str, name: str | None = None, line: int | None = None) -> None:
        self.message = message
        self.name = name
        self.line = line

        details = []
        if line is not None:
            details.append(f"line {line}")
        if name is not None:
            details.append(f"attachment {name!r}")
        if details:
            message = f"{message} ({', '.join(details)})"

        super().__init__(message)

    def __reduce__(self) -> Any:
        return self.__class__, (self.message, self.name, self.line)


class UnknownFileExtensionError(Pysubs2Error):
    """
    File extension does not pertain to any known subtitle format.

    This exception is raised by `SSAFile.save()` when the ``format_`` parameter
    is not specified. It will try to guess the desired format from output filename
    and raise this exception when it fails.

    Attributes:
        ext (str): File extension
    """

    def __init__(self, ext: str) -> None:
        self.ext = ext
        msg = f"File extension {ext!r} does not match any supported subtitle format"
        super().__init__(msg)

    def __reduce__(self) -> Any:
        return self.__class__, (self.ext,)


class UnknownFormatIdentifierError(Pysubs2Error):
    """
    Unknown subtitle format identifier (ie. string like ``"srt"``).

    This exception is used when interpreting ``format_`` parameter fails,
    eg. in `SSAFile.save()`.

    Attributes:
        format_ (str): Format identifier
    """

    def __init__(self, format_: str) -> None:
        self.format_ = format_
        msg = f"Format identifier {format_!r} does not match any supported subtitle format"
        super().__init__(msg)

    def __reduce__(self) -> Any:
        return self.__class__, (self.format_,)


class FormatAutodetectionError(Pysubs2Error):
    """
    Subtitle format is ambiguous or unknown based on analysis of file fragment

    This exception is raised by `SSAFile.load()` and related methods
    when the ``format_`` parameter is not specified. It will try to guess
    the input format based on reading first few kilobytes of the input file
    and raise this exception if the format cannot be uniquely determined.

    Attributes:
        content (str): Analyzed subtitle file content
        formats (list[str]): Format identifiers for detected formats
    """
    def __init__(self, content: str, formats: list[str]) -> None:
        self.content = content
        self.formats = formats
        if not formats:
            msg = "No suitable formats"
        else:
            msg = f"Multiple suitable formats ({formats!r})"
        super().__init__(msg)

    def __reduce__(self) -> Any:
        return self.__class__, (self.content, self.formats)
