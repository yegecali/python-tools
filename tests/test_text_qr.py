import json
import random
import string
from pathlib import Path

import pytest

import rsa_crypt
import text_qr as tq

NO_KEY = Path("no-existe-private.pem")


def test_clean_text_joins_lines_and_collapses_spaces():
    assert tq.clean_text("  a \t b\n\n c  ") == "a b c"


def test_clean_text_handles_windows_line_endings():
    assert tq.clean_text("uno\r\ndos\r\ntres") == "uno dos tres"


def test_clean_text_keep_newlines_collapses_blank_runs_to_one():
    assert tq.clean_text("a  b\n\n\n\nc\n", keep_newlines=True) == "a b\n\nc"


def noisy_text(length, seed=1):
    """Random words: they do not compress, so the payload really needs several parts."""
    rng = random.Random(seed)
    words = ["".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(2, 9))) for _ in range(500)]
    out = []
    while sum(len(w) + 1 for w in out) < length:
        out.append(rng.choice(words))
    return " ".join(out)[:length]


def roundtrip(text, chunk, pubkey=None, privkey=NO_KEY, keep_newlines=False):
    cleaned = tq.clean_text(text, keep_newlines)
    mode, payload = tq.make_payload(cleaned, pubkey)
    lines = tq.split_parts(mode, payload, chunk)
    return cleaned, lines, tq.restore(lines, privkey)


def test_plain_roundtrip_in_single_part():
    text = "Informe de configuracion con acentos: ñ, á, 🔑"
    cleaned, lines, restored = roundtrip(text, chunk=1200)
    assert len(lines) == 1
    assert restored == cleaned


def test_plain_roundtrip_splits_into_many_parts_and_restores_in_any_order():
    cleaned, lines, restored = roundtrip(noisy_text(3000), chunk=120)
    assert len(lines) > 3
    assert restored == cleaned

    shuffled = list(reversed(lines))
    assert tq.restore(shuffled, NO_KEY) == cleaned


def test_each_part_respects_chunk_size():
    _, lines, _ = roundtrip(noisy_text(4000, seed=2), chunk=100)
    for line in lines:
        data = tq.parse_part(line)[4]
        assert len(data) <= 100


def test_encrypted_roundtrip(rsa_key_files):
    public_path, private_path = rsa_key_files
    cleaned, lines, restored = roundtrip(
        "texto confidencial de prueba " * 50,
        chunk=400,
        pubkey=public_path,
        privkey=private_path,
    )
    assert tq.parse_part(lines[0])[0] == "E"
    assert restored == cleaned


def test_encrypted_message_with_wrong_key_exits(rsa_key_files, other_rsa_key_files):
    public_path, _ = rsa_key_files
    _, lines, _ = roundtrip("secreto", chunk=1200, pubkey=public_path, privkey=rsa_key_files[1])
    with pytest.raises(SystemExit, match="desencriptar"):
        tq.restore(lines, other_rsa_key_files[1])


def test_missing_part_is_reported_with_its_number():
    _, lines, _ = roundtrip(noisy_text(1500, seed=3), chunk=100)
    assert len(lines) >= 3
    without_second = [line for i, line in enumerate(lines, 1) if i != 2]
    with pytest.raises(SystemExit, match="Faltan las partes: 2"):
        tq.restore(without_second, NO_KEY)


def test_altered_part_fails_checksum():
    _, lines, _ = roundtrip(noisy_text(1500, seed=4), chunk=100)
    fields = lines[1].split("|", 4)
    fields[4] = ("A" if fields[4][0] != "A" else "B") + fields[4][1:]
    lines[1] = "|".join(fields)
    with pytest.raises(SystemExit, match="no coincide"):
        tq.restore(lines, NO_KEY)


def test_parts_from_two_messages_are_not_mixed():
    _, first, _ = roundtrip(noisy_text(400, seed=5), chunk=100)
    _, second, _ = roundtrip(noisy_text(400, seed=6), chunk=100)
    with pytest.raises(SystemExit, match="mensajes distintos"):
        tq.restore(first + second, NO_KEY)


def test_restore_rejects_empty_input_and_foreign_lines():
    with pytest.raises(SystemExit, match="No encontre partes"):
        tq.restore(["", "   "], NO_KEY)
    with pytest.raises(SystemExit, match="no es una parte"):
        tq.restore(["esto no es un QR"], NO_KEY)


def test_parse_part_rejects_malformed_line():
    with pytest.raises(ValueError):
        tq.parse_part("TQR1|P|solo-tres-campos")


def test_payload_of_encrypted_message_is_json_with_hybrid_fields(rsa_key_files):
    mode, payload = tq.make_payload("hola", rsa_key_files[0])
    assert mode == "E"
    assert set(json.loads(payload)) == {"v", "key", "nonce", "data"}
