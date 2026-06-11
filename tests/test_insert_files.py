from sqlite_utils import cli, Database
from click.testing import CliRunner
import os
import pathlib
import pytest
import sys


@pytest.mark.parametrize("silent", (False, True))
@pytest.mark.parametrize(
    "pk_args,expected_pks",
    (
        (["--pk", "path"], ["path"]),
        (["--pk", "path", "--pk", "name"], ["path", "name"]),
    ),
)
def test_insert_files(silent, pk_args, expected_pks):
    runner = CliRunner()
    with runner.isolated_filesystem():
        tmpdir = pathlib.Path(".")
        db_path = str(tmpdir / "files.db")
        (tmpdir / "one.txt").write_text("This is file one", "utf-8")
        (tmpdir / "two.txt").write_text("Two is shorter", "utf-8")
        (tmpdir / "nested").mkdir()
        (tmpdir / "nested" / "three.zz.txt").write_text("Three is nested", "utf-8")
        coltypes = (
            "name",
            "path",
            "fullpath",
            "sha256",
            "md5",
            "mode",
            "content",
            "content_text",
            "mtime",
            "ctime",
            "mtime_int",
            "ctime_int",
            "mtime_iso",
            "ctime_iso",
            "size",
            "suffix",
            "stem",
        )
        cols = []
        for coltype in coltypes:
            cols += ["-c", "{}:{}".format(coltype, coltype)]
        result = runner.invoke(
            cli.cli,
            ["insert-files", db_path, "files", str(tmpdir)]
            + cols
            + pk_args
            + (["--silent"] if silent else []),
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.stdout
        db = Database(db_path)
        rows_by_path = {r["path"]: r for r in db["files"].rows}
        one, two, three = (
            rows_by_path["one.txt"],
            rows_by_path["two.txt"],
            rows_by_path[os.path.join("nested", "three.zz.txt")],
        )
        assert {
            "content": b"This is file one",
            "content_text": "This is file one",
            "md5": "556dfb57fce9ca301f914e2273adf354",
            "name": "one.txt",
            "path": "one.txt",
            "sha256": "e34138f26b5f7368f298b4e736fea0aad87ddec69fbd04dc183b20f4d844bad5",
            "size": 16,
            "stem": "one",
            "suffix": ".txt",
        }.items() <= one.items()
        assert {
            "content": b"Two is shorter",
            "content_text": "Two is shorter",
            "md5": "f86f067b083af1911043eb215e74ac70",
            "name": "two.txt",
            "path": "two.txt",
            "sha256": "9368988ed16d4a2da0af9db9b686d385b942cb3ffd4e013f43aed2ec041183d9",
            "size": 14,
            "stem": "two",
            "suffix": ".txt",
        }.items() <= two.items()
        assert {
            "content": b"Three is nested",
            "content_text": "Three is nested",
            "md5": "12580f341781f5a5b589164d3cd39523",
            "name": "three.zz.txt",
            "path": os.path.join("nested", "three.zz.txt"),
            "sha256": "6dd45aaaaa6b9f96af19363a92c8fca5d34791d3c35c44eb19468a6a862cc8cd",
            "size": 15,
            "stem": "three.zz",
            "suffix": ".txt",
        }.items() <= three.items()
        # Assert the other int/str/float columns exist and are of the right types
        expected_types = {
            "ctime": float,
            "ctime_int": int,
            "ctime_iso": str,
            "mtime": float,
            "mtime_int": int,
            "mtime_iso": str,
            "mode": int,
            "fullpath": str,
            "content": bytes,
            "content_text": str,
            "stem": str,
            "suffix": str,
        }
        for colname, expected_type in expected_types.items():
            for row in (one, two, three):
                assert isinstance(row[colname], expected_type)
        assert set(db["files"].pks) == set(expected_pks)


@pytest.mark.parametrize(
    "use_text,encoding,input,expected",
    (
        (False, None, "hello world", b"hello world"),
        (True, None, "hello world", "hello world"),
        (False, None, b"S\xe3o Paulo", b"S\xe3o Paulo"),
        (True, "latin-1", b"S\xe3o Paulo", "S\xe3o Paulo"),
    ),
)
def test_insert_files_stdin(use_text, encoding, input, expected):
    runner = CliRunner()
    with runner.isolated_filesystem():
        tmpdir = pathlib.Path(".")
        db_path = str(tmpdir / "files.db")
        args = ["insert-files", db_path, "files", "-", "--name", "stdin-name"]
        if use_text:
            args += ["--text"]
        if encoding is not None:
            args += ["--encoding", encoding]
        result = runner.invoke(
            cli.cli,
            args,
            catch_exceptions=False,
            input=input,
        )
        assert result.exit_code == 0, result.stdout
        db = Database(db_path)
        row = list(db["files"].rows)[0]
        key = "content"
        if use_text:
            key = "content_text"
        assert {"path": "stdin-name", key: expected}.items() <= row.items()


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Windows has a different way of handling default encodings",
)
def test_insert_files_bad_text_encoding_error():
    runner = CliRunner()
    with runner.isolated_filesystem():
        tmpdir = pathlib.Path(".")
        latin = tmpdir / "latin.txt"
        latin.write_bytes(b"S\xe3o Paulo")
        db_path = str(tmpdir / "files.db")
        result = runner.invoke(
            cli.cli,
            ["insert-files", db_path, "files", str(latin), "--text"],
            catch_exceptions=False,
        )
        assert result.exit_code == 1, result.output
        assert result.output.strip().startswith(
            "Error: Could not read file '{}' as text".format(str(latin.resolve()))
        )


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Windows has a different way of handling default encodings",
)
def test_insert_files_bad_encoding_no_partial_results():
    """A bad-encoding file should leave NO rows in the database."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        tmpdir = pathlib.Path(".")
        (tmpdir / "good1.txt").write_text("Good file one", "utf-8")
        (tmpdir / "good2.txt").write_text("Good file two", "utf-8")
        (tmpdir / "bad.txt").write_bytes(b"\x80\x81\x82 invalid utf-8")
        db_path = str(tmpdir / "files.db")
        result = runner.invoke(
            cli.cli,
            ["insert-files", db_path, "files", str(tmpdir), "--text"],
        )
        assert result.exit_code == 1
        assert "bad.txt" in result.output
        # Verify NO partial results exist in the database
        db = Database(db_path)
        assert not db["files"].exists() or db["files"].count == 0


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Windows has a different way of handling default encodings",
)
def test_insert_files_multiple_bad_encoding_all_reported():
    """All files with encoding errors should be reported, not just the first."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        tmpdir = pathlib.Path(".")
        (tmpdir / "good.txt").write_text("Good file", "utf-8")
        (tmpdir / "bad1.txt").write_bytes(b"\x80\x81 bad one")
        (tmpdir / "bad2.txt").write_bytes(b"\xff\xfe bad two")
        db_path = str(tmpdir / "files.db")
        result = runner.invoke(
            cli.cli,
            ["insert-files", db_path, "files", str(tmpdir), "--text"],
        )
        assert result.exit_code == 1
        assert "bad1.txt" in result.output
        assert "bad2.txt" in result.output
        # Verify no partial results
        db = Database(db_path)
        assert not db["files"].exists() or db["files"].count == 0


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Windows has a different way of handling default encodings",
)
def test_insert_files_rerun_after_fix_succeeds():
    """After fixing a bad file, re-running should succeed with all files."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        tmpdir = pathlib.Path(".")
        (tmpdir / "good.txt").write_text("Good file", "utf-8")
        bad_file = tmpdir / "bad.txt"
        bad_file.write_bytes(b"\x80\x81 bad")
        db_path = str(tmpdir / "files.db")

        # First run fails
        result = runner.invoke(
            cli.cli,
            ["insert-files", db_path, "files", str(tmpdir), "--text"],
        )
        assert result.exit_code == 1

        # Fix the bad file
        bad_file.write_text("Now fixed", "utf-8")

        # Second run succeeds cleanly with all files
        result = runner.invoke(
            cli.cli,
            ["insert-files", db_path, "files", str(tmpdir), "--text"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        db = Database(db_path)
        assert db["files"].count == 2
        rows = {r["path"]: r for r in db["files"].rows}
        assert rows["good.txt"]["content_text"] == "Good file"
        assert rows["bad.txt"]["content_text"] == "Now fixed"


def test_insert_files_binary_directory_unaffected():
    """Binary mode directory import should work regardless of file content."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        tmpdir = pathlib.Path(".")
        (tmpdir / "binary1.bin").write_bytes(b"\x80\x81\x82\x83")
        (tmpdir / "binary2.bin").write_bytes(b"\xff\xfe\x00\x01")
        db_path = str(tmpdir / "files.db")
        result = runner.invoke(
            cli.cli,
            ["insert-files", db_path, "files", str(tmpdir)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        db = Database(db_path)
        assert db["files"].count == 2
