"""Run one bounded OCR tile in a disposable process.

The web process deliberately does not retain an OCR model. This prevents
successive dense screenshot slices from accumulating native inference memory.
"""
import json
import sys


def lines(result):
    if result is None:
        return []
    if hasattr(result, 'txts'):
        return [str(value) for value in result.txts if str(value).strip()]
    if isinstance(result, tuple):
        result = result[0]
    found = []
    for item in result or []:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            value = item[1]
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ''
            if str(value).strip():
                found.append(str(value))
    return found


def main():
    import numpy as np
    from rapidocr import RapidOCR

    width = int(sys.argv[1]); height = int(sys.argv[2])
    if not 1 <= width <= 1200 or not 1 <= height <= 900:
        raise ValueError('OCR tile dimensions out of range')
    raw = sys.stdin.buffer.read(width * height * 3 + 1)
    if len(raw) != width * height * 3:
        raise ValueError('OCR tile data length mismatch')
    image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))
    engine = RapidOCR(params={'Global.use_cls': False, 'Global.log_level': 'error',
                              'EngineConfig.onnxruntime.intra_op_num_threads': 1,
                              'EngineConfig.onnxruntime.inter_op_num_threads': 1})
    sys.stdout.buffer.write(json.dumps({'text': '\n'.join(lines(engine(image)))}, ensure_ascii=False).encode('utf-8'))


if __name__ == '__main__':
    main()
