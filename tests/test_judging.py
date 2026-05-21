from tdec.judging import parse_json_response


def test_parse_json_response_accepts_plain_json() -> None:
    parsed = parse_json_response('{"winner": "pro", "confidence": 0.8}')

    assert parsed == {"winner": "pro", "confidence": 0.8}


def test_parse_json_response_extracts_json_from_text() -> None:
    parsed = parse_json_response('Here is my judgement:\n{"winner": "con"}')

    assert parsed == {"winner": "con"}

