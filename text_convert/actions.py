"""Convert text encoding and newline styles."""

import re
import shutil
import subprocess
from pathlib import Path

from xefm.user_api import xefm_python

ENCODINGS = (
    ("utf-8", "UTF-8"), ("utf-8-bom", "UTF-8 BOM"),
    ("shift-jis", "Shift_JIS (CP932)"), ("euc-jp", "EUC-JP"),
    ("iso-2022-jp", "ISO-2022-JP"), ("keep", "変更しない"),
)
NEWLINES = (
    ("keep", "変更しない"), ("crlf", "Windows (CRLF)"),
    ("lf", "Unix (LF)"), ("cr", "旧Mac (CR)"),
)


def _source_summary(paths):
    nkf = shutil.which("nkf")
    if not nkf:
        raise FileNotFoundError("nkf.exe が PATH に見つかりません")
    counts = {}
    for path in paths:
        with open(path, "rb") as stream:
            sample = stream.read(65536)
        if not sample:
            description = "空ファイル"
        else:
            result = subprocess.run([nkf, "--guess"], input=sample, capture_output=True,
                                    check=True, timeout=10)
            guess = result.stdout.decode("ascii", errors="replace").strip()
            encoding = re.sub(r"\s+\((?:CRLF|LF|CR|MIXED NL|no newline)\)$", "", guess,
                              flags=re.IGNORECASE)
            bom = sample.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00"))
            controls = sum(byte < 32 and byte not in (9, 10, 12, 13, 27) for byte in sample)
            if "BINARY" in guess.upper() or (b"\x00" in sample and not bom) \
                    or (controls / len(sample) > 0.01 and not bom):
                description = "バイナリ (変換対象外)"
            else:
                crlf = sample.count(b"\r\n")
                lf = sample.count(b"\n") - crlf
                cr = sample.count(b"\r") - crlf
                styles = [name for name, count in (("CRLF", crlf), ("LF", lf), ("CR", cr)) if count]
                newline = styles[0] if len(styles) == 1 else ("混在" if styles else "改行なし")
                description = f"{encoding} ({newline})"
        counts[description] = counts.get(description, 0) + 1
    return " / ".join(f"{label} ×{count}" for label, count in counts.items())


def convert_text_files(ctx):
    """Choose output encoding and newline style, then overwrite the selected files."""
    selected = [entry for entry in ctx.pane.selected() if entry.is_file]
    if not selected:
        focused = ctx.pane.focused
        if focused is None or not focused.is_file:
            ctx.message("テキストファイルを選択してください")
            return
        selected = [focused]
    paths = [str(entry.path) for entry in selected]
    local_paths = [path for path in paths if "://" not in path]
    skipped = len(paths) - len(local_paths)
    if skipped:
        ctx.message(f"ローカル以外のファイル {skipped} 件は対象外です")
    if not local_paths:
        return
    try:
        source_summary = _source_summary(local_paths)
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.message(f"入力形式を判定できません: {exc}")
        return
    values = {"encoding": "utf-8", "newline": "crlf"}

    def confirm():
        encoding = dict(ENCODINGS)[values["encoding"]]
        newline = dict(NEWLINES)[values["newline"]]
        summary = (f"入力: {source_summary}\n{len(local_paths)} ファイル / 入力は自動判定 / "
                   f"出力 {encoding} / {newline}")

        def on_confirm(accepted):
            if accepted:
                ctx.run_program([xefm_python, str(Path(__file__).with_name("convert.py")),
                                 "--encoding", values["encoding"], "--newline", values["newline"],
                                 "--", *local_paths])
        ctx.confirm(f"{summary}\n元ファイルを上書きして変換します。続行しますか？",
                    title="文字コード・改行コード変換", on_result=on_confirm)

    def options():
        items = ["変換", f"出力文字コード: {dict(ENCODINGS)[values['encoding']]}",
                 f"改行コード: {dict(NEWLINES)[values['newline']]}"]

        def picked(index):
            if index is None:
                return
            if index == 0:
                confirm()
                return
            key, choices = ("encoding", ENCODINGS) if index == 1 else ("newline", NEWLINES)

            def chosen(selection):
                if selection is not None:
                    values[key] = choices[selection][0]
                options()
            ctx.choose(items[index], [label for _, label in choices], on_result=chosen)
        ctx.choose(f"入力: {source_summary}", items, on_result=picked)

    options()
