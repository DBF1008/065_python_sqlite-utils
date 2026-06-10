from sqlite_utils import utils
import csv
import io
import pytest


@pytest.mark.parametrize(
    "input,expected,should_be_is",
    [
        ({}, None, True),
        ({"foo": "bar"}, None, True),
        (
            {"content": {"$base64": True, "encoded": "aGVsbG8="}},
            {"content": b"hello"},
            False,
        ),
    ],
)
def test_decode_base64_values(input, expected, should_be_is):
    actual = utils.decode_base64_values(input)
    if should_be_is:
        assert actual is input
    else:
        assert actual == expected


@pytest.mark.parametrize(
    "size,expected",
    (
        (1, [["a"], ["b"], ["c"], ["d"]]),
        (2, [["a", "b"], ["c", "d"]]),
        (3, [["a", "b", "c"], ["d"]]),
        (4, [["a", "b", "c", "d"]]),
    ),
)
def test_chunks(size, expected):
    input = ["a", "b", "c", "d"]
    chunks = list(map(list, utils.chunks(input, size)))
    assert chunks == expected


def test_hash_record():
    expected = "d383e7c0ba88f5ffcdd09be660de164b3847401a"
    assert utils.hash_record({"name": "Cleo", "twitter": "CleoPaws"}) == expected
    assert (
        utils.hash_record(
            {"name": "Cleo", "twitter": "CleoPaws", "age": 7}, keys=("name", "twitter")
        )
        == expected
    )
    assert (
        utils.hash_record({"name": "Cleo", "twitter": "CleoPaws", "age": 7}) != expected
    )


def test_maximize_csv_field_size_limit():
    # Reset to default in case other tests have changed it
    csv.field_size_limit(utils.ORIGINAL_CSV_FIELD_SIZE_LIMIT)
    long_value = "a" * 131073
    long_csv = "id,text\n1,{}".format(long_value)
    fp = io.BytesIO(long_csv.encode("utf-8"))
    # Using rows_from_file should error
    with pytest.raises(csv.Error):
        rows, _ = utils.rows_from_file(fp, utils.Format.CSV)
        list(rows)
    # But if we call maximize_csv_field_size_limit() first it should be OK:
    utils.maximize_csv_field_size_limit()
    fp2 = io.BytesIO(long_csv.encode("utf-8"))
    rows2, _ = utils.rows_from_file(fp2, utils.Format.CSV)
    rows_list2 = list(rows2)
    assert len(rows_list2) == 1
    assert rows_list2[0]["id"] == "1"
    assert rows_list2[0]["text"] == long_value


@pytest.mark.parametrize(
    "input,expected",
    (
        ({"foo": {"bar": 1}}, {"foo_bar": 1}),
        ({"foo": {"bar": [1, 2, {"baz": 3}]}}, {"foo_bar": [1, 2, {"baz": 3}]}),
        ({"foo": {"bar": 1, "baz": {"three": 3}}}, {"foo_bar": 1, "foo_baz_three": 3}),
    ),
)
def test_flatten(input, expected):
    assert utils.flatten(input) == expected


@pytest.mark.parametrize(
    "input_bytes,expected",
    [
        (b'{"a":1}\n{"b":2}', True),
        (b'{"a":1}\n\n{"b":2}', True),
        (b'{"a":1}\r\n{"b":2}', True),
        (b'  {"a":1}\n{"b":2}', True),
        (b'{"a":1}', False),
        (b'{"a":1}\n', False),
        (b'[{"a":1}]', False),
        (b'{\n"a":1\n}', False),
        (b"name,age\nAlice,30", False),
    ],
)
def test_detect_ndjson(input_bytes, expected):
    assert utils._detect_ndjson(input_bytes) is expected


@pytest.mark.parametrize(
    "input_bytes,expected_format",
    [
        (b'{"a":1}\n{"b":2}\n', utils.Format.NL),
        (b'[{"a":1},{"b":2}]', utils.Format.JSON),
        (b'{"a":1}', utils.Format.JSON),
        (b'{\n"a":1\n}', utils.Format.JSON),
    ],
)
def test_rows_from_file_ndjson_autodetect(input_bytes, expected_format):
    fp = io.BytesIO(input_bytes)
    rows, detected_format = utils.rows_from_file(fp)
    assert detected_format == expected_format
    result = list(rows)
    assert len(result) >= 1
    assert isinstance(result[0], dict)
