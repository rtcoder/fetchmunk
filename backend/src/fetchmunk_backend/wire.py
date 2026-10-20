"""Bounded JSON Lines transport, independent of gallery-dl."""

import json

MAX_FRAME = 1048576


class ProtocolError(ValueError):
    pass


def validate(value):
    if (
        not isinstance(value, dict)
        or type(value.get("protocol")) is not int
        or value["protocol"] != 1
        or not isinstance(value.get("type"), str)
    ):
        raise ProtocolError("invalid envelope")
    return value


def encode_frame(message: dict) -> bytes:
    try:
        raw = (
            json.dumps(
                validate(message),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ProtocolError("invalid message") from exc
    if len(raw) > MAX_FRAME:
        raise ProtocolError("message too large")
    return raw


class FrameDecoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[dict]:
        frames = []
        # Process LF only; CR and Unicode separators are not framing characters.
        start = 0
        while True:
            end = chunk.find(b"\n", start)
            segment = chunk[start:] if end < 0 else chunk[start : end + 1]
            if len(self.buffer) + len(segment) > MAX_FRAME:
                raise ProtocolError("message too large")
            self.buffer.extend(segment)
            if end < 0:
                break
            try:
                obj = json.loads(
                    self.buffer.decode("utf-8"),
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                )
                frames.append(validate(obj))
            except (ValueError, UnicodeError) as exc:
                raise ProtocolError("invalid frame") from exc
            self.buffer.clear()
            start = end + 1
        return frames

    def finish(self):
        if self.buffer:
            raise ProtocolError("truncated frame")
