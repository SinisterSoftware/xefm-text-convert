"""Convert text encodings and newline styles with nkf, replacing files safely."""

import argparse
import os
import re
import shlex
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

site.addsitedir(str(Path.home() / ".xefm" / "site-packages" /
                    f"{sys.version_info.major}.{sys.version_info.minor}"))
import win32file

ENCODINGS = {
    "utf-8": "-w",
    "utf-8-bom": "-w8",
    "shift-jis": "-s",
    "euc-jp": "-e",
    "iso-2022-jp": "-j",
    "keep": None,
}
NEWLINES = {
    "keep": None,
    "crlf": "-Lw",
    "lf": "-Lu",
    "cr": "-Lm",
}
NEWLINE_BYTES = {"keep": None, "crlf": "\r\n", "lf": "\n", "cr": "\r"}


def collect(args):
    if args.files:
        return args.files
    this_dir = os.environ.get("XEFM_THIS_DIR", os.getcwd())
    names = shlex.split(os.environ.get("XEFM_THIS_SELECTED", "")) or \
        shlex.split(os.environ.get("XEFM_THIS_FOCUSED", ""))
    return [name if os.path.isabs(name) else os.path.join(this_dir, name) for name in names]


def _source_codec(data, guess):
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32"
    if data.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"

    label = guess.upper()
    if label.startswith("UTF-8"):
        return "utf-8"
    if label.startswith("SHIFT_JIS") or label.startswith("CP932"):
        return "cp932"
    if label.startswith("EUC-JP"):
        return "euc_jp"
    if label.startswith("ISO-2022-JP"):
        return "iso2022_jp"
    if label.startswith("ASCII"):
        return "ascii"
    raise UnicodeError(f"入力文字コードを特定できません: {guess}")


def _preserve_encoding(data, guess, newline):
    target = NEWLINE_BYTES[newline]
    if target is None:
        return data
    codec = _source_codec(data, guess)
    text = data.decode(codec)
    text = re.sub(r"\r\n|\r|\n", lambda _match: target, text)
    return text.encode(codec)


def convert(path, encoding, newline, nkf):
    stat = os.stat(path)
    with open(path, "rb") as source:
        data = source.read()
    if not data:
        print(f"SKIP empty: {path}")
        return False

    guess = subprocess.run([nkf, "--guess"], input=data, capture_output=True, check=True).stdout
    description = guess.decode("ascii", errors="replace").strip()
    sample = data[:8192]
    has_unicode_bom = sample.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00"))
    controls = sum(byte < 32 and byte not in (9, 10, 12, 13, 27) for byte in sample)
    if "BINARY" in description.upper() or (b"\x00" in sample and not has_unicode_bom) \
            or (sample and controls / len(sample) > 0.01 and not has_unicode_bom):
        print(f"SKIP binary: {path}")
        return False

    if encoding == "keep":
        output = _preserve_encoding(data, description, newline)
    else:
        command = [nkf, ENCODINGS[encoding]]
        newline_flag = NEWLINES[newline]
        if newline_flag:
            command.append(newline_flag)
        result = subprocess.run(command, input=data, capture_output=True, check=True)
        output = result.stdout

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=os.path.dirname(path),
                                         prefix=".xefm-convert-", suffix=".tmp") as target:
            temp_path = target.name
            target.write(output)
            target.flush()
            os.fsync(target.fileno())
        os.utime(temp_path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        win32file.ReplaceFile(path, temp_path, None)
        temp_path = None
        print(f"OK: {path} ({description} -> {encoding}, {newline})")
        return True
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--encoding", choices=ENCODINGS, default="utf-8")
    parser.add_argument("--newline", choices=NEWLINES, default="crlf")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    nkf = shutil.which("nkf")
    if not nkf:
        print("nkf.exe が PATH に見つかりません。Scoop の shims を PATH に追加してください。")
        return 1
    paths = [p for p in collect(args) if os.path.isfile(p)]
    if not paths:
        print("対象ファイルがありません")
        return 0

    failures = 0
    converted = 0
    for path in paths:
        try:
            converted += bool(convert(path, args.encoding, args.newline, nkf))
        except (OSError, subprocess.SubprocessError) as exc:
            failures += 1
            print(f"ERROR: {path}: {exc}")
    print(f"変換 {converted} 件 / 失敗 {failures} 件")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
