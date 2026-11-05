import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from text_convert.actions import convert_text_files


class Context:
    def __init__(self):
        self.pane = SimpleNamespace(selected=lambda: [], focused=SimpleNamespace(
            is_file=True, path=r"C:\input\file.txt"))
        self.choices = []
        self.commands = []

    def choose(self, title, items, *, on_result, **kwargs):
        self.choices.append((items, on_result))

    def confirm(self, prompt, *, title, on_result):
        on_result(True)

    def run_program(self, command):
        self.commands.append(command)

    def message(self, text):
        pass


class TextActionTests(unittest.TestCase):
    @patch("text_convert.actions._source_summary", return_value="UTF-8")
    def test_choices_and_packaged_command(self, _summary):
        ctx = Context()
        convert_text_files(ctx)
        ctx.choices.pop()[1](1)
        ctx.choices.pop()[1](2)
        ctx.choices.pop()[1](0)
        command = ctx.commands[0]
        self.assertEqual(Path(command[1]).name, "convert.py")
        self.assertTrue(Path(command[1]).is_file())
        self.assertEqual(command[command.index("--encoding") + 1], "shift-jis")
        self.assertEqual(command[command.index("--newline") + 1], "crlf")
