"""
Tests of SubStation [Fonts] and [Graphics] handling.

Covers the original opaque passthrough behaviour, the decoded binary
attachment API, editing a single attachment, and error handling for
damaged attachment data.
"""

import pickle
import re
from pathlib import Path

import pytest

from pysubs2 import SSAEvent, SSAFile
from pysubs2.attachments import (
    ATTACHMENT_LINE_LENGTH,
    FONT_EXTENSIONS,
    MAX_ATTACHMENT_SIZE,
    decode_attachment,
    encode_attachment,
    guess_attachment_kind,
)
from pysubs2.exceptions import AttachmentError

current_dir = Path(__file__).parent

FONT_SUBS_AEGISUB_PATH = current_dir / "data/subtitle_with_attached_fonts_aegisub.ass"
FONT_SUBS_PYSUBS_PATH = current_dir / "data/subtitle_with_attached_fonts_pysubs2_ref.ass"
FONT_SUBS_NO_EVENTS_PATH = current_dir / "data/subtitle_with_attached_fonts_no_events.ass"
IMAGE_SUBS_AEGISUB_PATH = current_dir / "data/subtitle_with_attached_images_aegisub.ass"
IMAGE_SUBS_PYSUBS_PATH = current_dir / "data/subtitle_with_attached_images_pysubs2_ref.ass"

GARAMOND_REGULAR_PATH = current_dir / "data/EBGaramond08-Regular.ttf"
GARAMOND_ITALIC_PATH = current_dir / "data/EBGaramond08-Italic.ttf"

DATA_DIR = current_dir / "data"

#: Attachment names used in the fonts fixture, in file order.
REGULAR_FONT_NAME = "EBGaramond08-Regular_0.ttf"
ITALIC_FONT_NAME = "EBGaramond08-Italic_0.ttf"


def _read(path: Path) -> bytes:
    with path.open("rb") as fp:
        return fp.read()


# ---------------------------------------------------------------------------
# Original opaque passthrough behaviour (must not regress)
# ---------------------------------------------------------------------------

def test_font_passthrough_from_aegisub() -> None:
    subs_aegisub = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    subs_pysubs2_ref = SSAFile.load(FONT_SUBS_PYSUBS_PATH)
    assert subs_aegisub.equals(subs_pysubs2_ref)  # sanity check for input

    # convert Aegisub, make sure we get the same output as reference
    subs_pysubs2_text = subs_aegisub.to_string("ass")

    with open(FONT_SUBS_PYSUBS_PATH) as fp:
        subs_pysubs2_text_ref = fp.read()

    assert subs_pysubs2_text.strip() == subs_pysubs2_text_ref.strip()

    # check again after loading
    subs_pysubs2 = SSAFile.from_string(subs_pysubs2_text)
    assert subs_pysubs2_ref.equals(subs_pysubs2)


def test_file_ending_with_font_section() -> None:
    subs = SSAFile.load(FONT_SUBS_NO_EVENTS_PATH)
    subs_ref = SSAFile.load(FONT_SUBS_PYSUBS_PATH)
    assert set(subs.fonts_opaque.keys()) == set(subs_ref.fonts_opaque.keys())


def test_image_passthrough_from_aegisub() -> None:
    subs_aegisub = SSAFile.load(IMAGE_SUBS_AEGISUB_PATH)
    subs_pysubs2_ref = SSAFile.load(IMAGE_SUBS_PYSUBS_PATH)
    assert subs_aegisub.equals(subs_pysubs2_ref)  # sanity check for input

    # convert Aegisub, make sure we get the same output as reference
    subs_pysubs2_text = subs_aegisub.to_string("ass")

    with open(IMAGE_SUBS_PYSUBS_PATH) as fp:
        subs_pysubs2_text_ref = fp.read()

    assert subs_pysubs2_text.strip() == subs_pysubs2_text_ref.strip()

    # check again after loading
    subs_pysubs2 = SSAFile.from_string(subs_pysubs2_text)
    assert subs_pysubs2_ref.equals(subs_pysubs2)


# ---------------------------------------------------------------------------
# Decoding attachments to bytes
# ---------------------------------------------------------------------------

def test_decoded_fonts_match_original_files() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)

    assert list(subs.fonts) == [REGULAR_FONT_NAME, ITALIC_FONT_NAME]
    assert subs.fonts[REGULAR_FONT_NAME] == _read(GARAMOND_REGULAR_PATH)
    assert subs.fonts[ITALIC_FONT_NAME] == _read(GARAMOND_ITALIC_PATH)


def test_invalid_character_reports_its_own_line() -> None:
    # The second data line contains the bad character 'a' (ordinal 97).
    with pytest.raises(AttachmentError) as excinfo:
        decode_attachment(["!!!!", "!!a!"], name="x.ttf", lineno=10)
    assert excinfo.value.line == 11
    assert excinfo.value.name == "x.ttf"


def test_decode_handles_multi_line_payload() -> None:
    # Both fonts span thousands of encoded lines; decoding must join them.
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    assert len(subs.fonts_opaque[REGULAR_FONT_NAME]) > 1000
    assert subs.fonts[REGULAR_FONT_NAME][:4] == b"\x00\x01\x00\x00"
    # Line boundaries are irrelevant: the concatenated payload decodes the same.
    one_line = "".join(subs.fonts_opaque[REGULAR_FONT_NAME])
    assert decode_attachment([one_line]) == _read(GARAMOND_REGULAR_PATH)


def test_binary_roundtrip_through_ass() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    text = subs.to_string("ass")
    loaded = SSAFile.from_string(text)

    assert loaded.fonts[REGULAR_FONT_NAME] == _read(GARAMOND_REGULAR_PATH)
    assert loaded.fonts[ITALIC_FONT_NAME] == _read(GARAMOND_ITALIC_PATH)
    assert loaded.equals(subs)


def test_no_events_fixture_decodes_fonts() -> None:
    subs = SSAFile.load(FONT_SUBS_NO_EVENTS_PATH)
    assert subs.fonts[REGULAR_FONT_NAME] == _read(GARAMOND_REGULAR_PATH)
    assert subs.fonts[ITALIC_FONT_NAME] == _read(GARAMOND_ITALIC_PATH)


def test_decoded_images_are_valid_binary() -> None:
    subs = SSAFile.load(IMAGE_SUBS_AEGISUB_PATH)

    assert list(subs.graphics) == ["github.jpg", "github.png"]
    jpeg = subs.graphics["github.jpg"]
    png = subs.graphics["github.png"]

    assert jpeg.startswith(b"\xff\xd8\xff")
    assert jpeg.endswith(b"\xff\xd9")
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png.endswith(b"IEND\xaeB`\x82")


def test_image_binary_roundtrip_through_ass() -> None:
    subs = SSAFile.load(IMAGE_SUBS_AEGISUB_PATH)
    expected = dict(subs.graphics)

    loaded = SSAFile.from_string(subs.to_string("ass"))
    assert dict(loaded.graphics) == expected
    assert loaded.equals(subs)


def test_get_attachment_searches_both_sections() -> None:
    fonts = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    images = SSAFile.load(IMAGE_SUBS_AEGISUB_PATH)

    assert fonts.get_attachment(REGULAR_FONT_NAME) == _read(GARAMOND_REGULAR_PATH)
    assert images.get_attachment("github.png") == images.graphics["github.png"]
    assert images.get_attachment("github.png", kind="graphics") == images.graphics["github.png"]

    with pytest.raises(KeyError):
        fonts.get_attachment("missing.ttf")
    with pytest.raises(KeyError):
        images.get_attachment(REGULAR_FONT_NAME)
    with pytest.raises(KeyError):
        images.get_attachment("github.png", kind="font")
    with pytest.raises(ValueError):
        images.get_attachment("github.png", kind="video")


# ---------------------------------------------------------------------------
# Editing one attachment only re-encodes that attachment
# ---------------------------------------------------------------------------

def test_modifying_one_font_only_reencodes_that_font() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    original_italic_lines = list(subs.fonts_opaque[ITALIC_FONT_NAME])
    original_regular_bytes = subs.fonts[REGULAR_FONT_NAME]

    new_data = b"\x00\x01\x00\x00" + b"replacement font" * 100
    subs.fonts[REGULAR_FONT_NAME] = new_data

    # The untouched attachment keeps its exact encoded lines.
    assert subs.fonts_opaque[ITALIC_FONT_NAME] == original_italic_lines
    # The modified attachment was re-encoded from the new bytes.
    assert subs.fonts_opaque[REGULAR_FONT_NAME] == encode_attachment(new_data)
    assert subs.fonts_opaque[REGULAR_FONT_NAME] != encode_attachment(original_regular_bytes)

    loaded = SSAFile.from_string(subs.to_string("ass"))
    assert loaded.fonts[REGULAR_FONT_NAME] == new_data
    assert loaded.fonts[ITALIC_FONT_NAME] == _read(GARAMOND_ITALIC_PATH)


def test_replacing_one_font_preserves_events_styles_and_order() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    events_before = [ev.as_dict() for ev in subs.events]
    styles_before = {name: sty.as_dict() for name, sty in subs.styles.items()}
    order_before = list(subs.fonts)
    italic_lines_before = list(subs.fonts_opaque[ITALIC_FONT_NAME])

    subs.replace_attachment(REGULAR_FONT_NAME, b"thin replacement")

    assert list(subs.fonts) == order_before
    assert subs.fonts_opaque[ITALIC_FONT_NAME] == italic_lines_before
    assert [ev.as_dict() for ev in subs.events] == events_before
    assert {name: sty.as_dict() for name, sty in subs.styles.items()} == styles_before

    text = subs.to_string("ass")
    assert re.findall(r"^fontname: (.+)$", text, re.MULTILINE) == order_before


def test_replacement_output_differs_only_in_one_attachment_block() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    baseline_lines = subs.to_string("ass").splitlines()

    subs.replace_attachment(REGULAR_FONT_NAME, _read(GARAMOND_ITALIC_PATH))
    modified_lines = subs.to_string("ass").splitlines()

    start = baseline_lines.index(f"fontname: {REGULAR_FONT_NAME}")
    end = baseline_lines.index("", start)
    modified_start = modified_lines.index(f"fontname: {REGULAR_FONT_NAME}")
    modified_end = modified_lines.index("", modified_start)

    assert baseline_lines[:start] == modified_lines[:modified_start]
    assert baseline_lines[end:] == modified_lines[modified_end:]
    assert modified_lines[modified_start:modified_end] == [
        f"fontname: {REGULAR_FONT_NAME}",
        *encode_attachment(_read(GARAMOND_ITALIC_PATH)),
    ]


def test_unmodified_attachments_are_written_back_verbatim() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    pinned = {name: list(lines) for name, lines in subs.fonts_opaque.items()}

    # Decoding for reading does not replace the stored encoded lines.
    _ = subs.fonts[REGULAR_FONT_NAME]
    _ = subs.get_attachment(ITALIC_FONT_NAME)

    assert subs.fonts_opaque == pinned
    with open(FONT_SUBS_PYSUBS_PATH) as fp:
        assert subs.to_string("ass").strip() == fp.read().strip()


def test_add_attachment_new_font_and_image() -> None:
    subs = SSAFile()
    subs.events.append(SSAEvent(text="test subtitle"))

    font_data = _read(GARAMOND_REGULAR_PATH)
    image_data = b"\x89PNG\r\n\x1a\n" + bytes(range(256))

    subs.add_attachment("MyFont.ttf", font_data)
    subs.add_attachment("image.png", image_data)

    assert "MyFont.ttf" in subs.fonts
    assert "image.png" in subs.graphics

    loaded = SSAFile.from_string(subs.to_string("ass"))
    assert loaded.fonts["MyFont.ttf"] == font_data
    assert loaded.graphics["image.png"] == image_data
    # New font goes to [Fonts], image to [Graphics].
    assert loaded.fonts_opaque.keys() == {"MyFont.ttf"}
    assert loaded.graphics_opaque.keys() == {"image.png"}


def test_add_attachment_rejects_duplicates() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    with pytest.raises(KeyError):
        subs.add_attachment(REGULAR_FONT_NAME, b"data")
    # Nothing was modified.
    assert subs.fonts[REGULAR_FONT_NAME] == _read(GARAMOND_REGULAR_PATH)


def test_attachment_mapping_supports_mutation_protocol() -> None:
    subs = SSAFile.load(IMAGE_SUBS_AEGISUB_PATH)
    assert len(subs.graphics) == 2
    assert set(iter(subs.graphics)) == {"github.jpg", "github.png"}
    assert "github.jpg" in subs.graphics
    assert "missing.png" not in subs.graphics

    del subs.graphics["github.jpg"]
    assert list(subs.graphics) == ["github.png"]
    with pytest.raises(KeyError):
        subs.graphics["github.jpg"]

    subs.remove_attachment("github.png")
    assert len(subs.graphics) == 0


def test_mapping_assignment_moves_attachment_between_sections() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    data = subs.fonts[REGULAR_FONT_NAME]

    subs.graphics[REGULAR_FONT_NAME] = data

    assert REGULAR_FONT_NAME not in subs.fonts_opaque
    assert subs.graphics_opaque[REGULAR_FONT_NAME] == encode_attachment(data)
    assert subs.get_attachment(REGULAR_FONT_NAME) == data


def test_rename_attachment_keeps_position() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    data = subs.fonts[REGULAR_FONT_NAME]

    subs.rename_attachment(REGULAR_FONT_NAME, "Renamed.ttf")
    assert list(subs.fonts) == ["Renamed.ttf", ITALIC_FONT_NAME]
    assert subs.fonts["Renamed.ttf"] == data
    assert subs.fonts_opaque["Renamed.ttf"] == encode_attachment(data)

    with pytest.raises(KeyError):
        subs.rename_attachment("missing.ttf", "Other.ttf")
    with pytest.raises(ValueError):
        subs.rename_attachment("Renamed.ttf", ITALIC_FONT_NAME)
    with pytest.raises(ValueError):
        subs.rename_attachment("Renamed.ttf", "")


def test_import_attachments() -> None:
    source = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    target = SSAFile.load(IMAGE_SUBS_AEGISUB_PATH)
    target.import_attachments(source)

    assert set(target.fonts) == {REGULAR_FONT_NAME, ITALIC_FONT_NAME}
    assert target.fonts[REGULAR_FONT_NAME] == _read(GARAMOND_REGULAR_PATH)
    # Original graphics are retained.
    assert set(target.graphics) == {"github.jpg", "github.png"}


def test_import_attachments_without_overwrite_and_self_import() -> None:
    source = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    target = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    target.replace_attachment(REGULAR_FONT_NAME, b"kept")
    target.import_attachments(source, overwrite=False)
    assert target.fonts[REGULAR_FONT_NAME] == b"kept"

    # Importing a file into itself is a no-op, not a mutation-during-iteration error.
    target.import_attachments(target)
    assert set(target.fonts) == {REGULAR_FONT_NAME, ITALIC_FONT_NAME}


# ---------------------------------------------------------------------------
# The encoding itself
# ---------------------------------------------------------------------------

def test_encode_matches_aegisub_lines_exactly() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)

    lines = encode_attachment(_read(GARAMOND_REGULAR_PATH))
    assert lines == subs.fonts_opaque[REGULAR_FONT_NAME]
    assert all(len(line) == ATTACHMENT_LINE_LENGTH for line in lines[:-1])
    assert 0 < len(lines[-1]) <= ATTACHMENT_LINE_LENGTH


@pytest.mark.parametrize("payload", [
    b"",
    b"\x00",
    b"\x00\x01",
    b"\x00\x01\x02",
    b"\x00\x01\x02\x03",
    bytes(range(256)),
    bytes(range(256)) * 100,
])
def test_encode_decode_roundtrip(payload: bytes) -> None:
    assert decode_attachment(encode_attachment(payload)) == payload


def test_encoding_alphabet_and_tail_groups() -> None:
    # One remaining byte is two characters, two bytes three, three bytes four.
    for payload, expected_chars in [(b"a", 2), (b"ab", 3), (b"abc", 4)]:
        assert len("".join(encode_attachment(payload))) == expected_chars

    assert encode_attachment(b"") == []
    assert set("".join(encode_attachment(bytes(range(256))))) <= set(map(chr, range(33, 97)))
    assert decode_attachment(["!!"]) == b"\x00"
    assert decode_attachment(["!!!"]) == b"\x00\x00"
    assert decode_attachment(["!!!!"]) == b"\x00\x00\x00"


def test_known_encoding_vectors() -> None:
    assert encode_attachment(b"\x00\x00\x00") == ["!!!!"]
    assert encode_attachment(b"\xff\xff\xff") == ["````"]
    assert encode_attachment(bytes([0x00, 0x00, 0x01])) == ['!!!"']
    assert encode_attachment(bytes([0x10, 0x20, 0x30])) == ["%#!Q"]
    assert decode_attachment(["%#!Q"]) == bytes([0x10, 0x20, 0x30])

    # The first fixture line decodes to the first 60 bytes of the font.
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    first_line = subs.fonts_opaque[REGULAR_FONT_NAME][0]
    assert decode_attachment([first_line]) == _read(GARAMOND_REGULAR_PATH)[:60]
    assert encode_attachment(decode_attachment([first_line])) == [first_line]


def test_lines_are_split_at_80_characters() -> None:
    payload = bytes(range(256)) * 4
    lines = encode_attachment(payload)

    assert all(len(line) == ATTACHMENT_LINE_LENGTH for line in lines[:-1])
    assert decode_attachment(lines) == payload
    # Line boundaries do not affect decoding.
    assert decode_attachment(["".join(lines)]) == payload

    with pytest.raises(ValueError):
        encode_attachment(b"abc", line_length=10)  # not a multiple of four


def test_guess_attachment_kind() -> None:
    for name in ("font.ttf", "FONT.TTF", "font.ttc", "font.otf", "font.pfb"):
        assert guess_attachment_kind(name) == "font"
    for name in ("image.png", "image.jpg", "no-extension"):
        assert guess_attachment_kind(name) == "graphics"
    assert FONT_EXTENSIONS == {".ttf", ".ttc", ".otf", ".pfb"}


def test_attachment_api_rejects_bad_names_and_data() -> None:
    subs = SSAFile()
    with pytest.raises(TypeError):
        subs.set_attachment("font.ttf", "not bytes")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        subs.set_attachment(1, b"data")  # type: ignore[arg-type]
    for bad_name in ("", "   ", " leading.ttf", "trailing.ttf ", "new\nline.ttf"):
        with pytest.raises(ValueError):
            subs.set_attachment(bad_name, b"data")
    with pytest.raises(ValueError):
        subs.set_attachment("font.ttf", b"data", kind="video")
    assert len(subs.fonts_opaque) == 0


def test_attachment_name_with_inner_spaces_is_accepted() -> None:
    subs = SSAFile()
    subs.set_attachment("my font.ttf", b"\x00\x01\x02")
    assert list(subs.fonts) == ["my font.ttf"]

    loaded = SSAFile.from_string(subs.to_string("ass"))
    assert loaded.fonts["my font.ttf"] == b"\x00\x01\x02"


# ---------------------------------------------------------------------------
# Errors for damaged attachment data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,message,line", [
    ("damaged_duplicate_name.ass", "duplicate attachment name", 12),
    ("damaged_empty_name.ass", "attachment name must not be empty", 9),
    ("damaged_invalid_char.ass", "invalid character", 10),
    ("damaged_orphan_data.ass", "attachment data appears before any attachment name", 9),
    ("damaged_truncated_tail.ass", "truncated attachment data", 10),
    ("damaged_wrong_section.ass", "'filename' is not valid in the [Fonts] section", 9),
    ("damaged_wrong_section_graphics.ass", "'fontname' is not valid in the [Graphics] section", 9),
])
def test_damaged_attachment_reports_line_number(filename: str, message: str, line: int) -> None:
    with pytest.raises(AttachmentError) as excinfo:
        SSAFile.load(DATA_DIR / filename)

    assert message in str(excinfo.value)
    assert excinfo.value.line == line
    assert f"line {line}" in str(excinfo.value)


def test_duplicate_attachment_error_carries_name() -> None:
    with pytest.raises(AttachmentError) as excinfo:
        SSAFile.load(DATA_DIR / "damaged_duplicate_name.ass")
    assert excinfo.value.name == "same.ttf"
    assert "same.ttf" in str(excinfo.value)


def test_truncated_tail_error_points_at_last_data_line() -> None:
    with pytest.raises(AttachmentError) as excinfo:
        SSAFile.load(DATA_DIR / "damaged_truncated_tail.ass")
    assert excinfo.value.line == 10
    assert excinfo.value.name == "broken.ttf"


def test_oversized_attachment_is_rejected() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    text = subs.to_string("ass")

    with pytest.raises(AttachmentError) as excinfo:
        SSAFile.from_string(text, format_="ass", max_attachment_size=1024)
    assert "too large" in str(excinfo.value)
    assert excinfo.value.name == REGULAR_FONT_NAME
    # The limit is reported once the boundary is crossed, at the data line.
    assert excinfo.value.line is not None
    assert excinfo.value.line > 19

    # The limit can be raised or disabled.
    loaded = SSAFile.from_string(text, format_="ass", max_attachment_size=MAX_ATTACHMENT_SIZE)
    assert loaded.fonts[REGULAR_FONT_NAME] == _read(GARAMOND_REGULAR_PATH)
    loaded = SSAFile.from_string(text, format_="ass", max_attachment_size=None)
    assert loaded.fonts[ITALIC_FONT_NAME] == _read(GARAMOND_ITALIC_PATH)


def test_duplicate_attachment_across_sections_is_rejected() -> None:
    text = """\
[Script Info]
ScriptType: v4.00+

[Fonts]
fontname: shared.bin
!!%!!!!3!1!!!!

[Graphics]
filename: shared.bin
!!%!!!!3!1!!!!

[Events]
"""
    with pytest.raises(AttachmentError) as excinfo:
        SSAFile.from_string(text, format_="ass")
    assert "duplicate attachment name" in str(excinfo.value)
    assert excinfo.value.line == 9


def test_decoding_corrupt_opaque_data_raises() -> None:
    subs = SSAFile()
    subs.fonts_opaque["broken.ttf"] = ['!!%!!!!3!1!!"a']
    subs.fonts_opaque["outside.ttf"] = ["!!!!Z"]

    with pytest.raises(AttachmentError):
        subs.fonts["broken.ttf"]
    with pytest.raises(AttachmentError):
        subs.get_attachment("broken.ttf")
    with pytest.raises(AttachmentError):
        subs.fonts["outside.ttf"]


def test_attachment_error_is_picklable() -> None:
    error = AttachmentError("message", name="font.ttf", line=42)
    restored = pickle.loads(pickle.dumps(error))

    assert isinstance(restored, AttachmentError)
    assert restored.name == "font.ttf"
    assert restored.line == 42
    assert restored.message == "message"
    assert str(restored) == str(error)


# ---------------------------------------------------------------------------
# The opaque dicts remain the storage of record
# ---------------------------------------------------------------------------

def test_decoded_access_does_not_pollute_opaque_storage() -> None:
    subs = SSAFile.load(FONT_SUBS_AEGISUB_PATH)
    before = {name: list(lines) for name, lines in subs.fonts_opaque.items()}

    _ = subs.fonts[REGULAR_FONT_NAME]
    _ = subs.get_attachment(ITALIC_FONT_NAME)

    assert subs.fonts_opaque == before
    assert subs.equals(SSAFile.load(FONT_SUBS_PYSUBS_PATH))
