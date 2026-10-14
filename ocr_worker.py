"""Single long-lived RapidOCR process using a small framed stdio protocol."""
import json
import os
import struct
import sys
import time


def lines(result):
    if result is None:
        return []
    if hasattr(result, 'txts'):
        return [str(value) for value in (result.txts or []) if str(value).strip()]
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


def peak_mb():
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1024 if sys.platform != 'darwin' else 1024 * 1024), 1)
    except (ImportError, OSError):
        return None


def read_exact(size):
    chunks = []
    while size:
        chunk = sys.stdin.buffer.read(size)
        if not chunk:
            raise EOFError
        chunks.append(chunk); size -= len(chunk)
    return b''.join(chunks)


def respond(payload):
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('!I', len(raw)) + raw)
    sys.stdout.buffer.flush()


def main():
    import numpy as np
    from rapidocr import RapidOCR

    initialized = time.perf_counter()
    engine = RapidOCR(params={'Global.use_cls': False, 'Global.log_level': 'error',
                              'Det.limit_type': 'max', 'Det.limit_side_len': 736,
                              'Rec.rec_batch_num': 1,
                              'EngineConfig.onnxruntime.enable_cpu_mem_arena': False,
                              'EngineConfig.onnxruntime.intra_op_num_threads': 1,
                              'EngineConfig.onnxruntime.inter_op_num_threads': 1})
    init_ms = round((time.perf_counter() - initialized) * 1000)
    while True:
        try:
            width, height, byte_count = struct.unpack('!III', read_exact(12))
        except EOFError:
            return
        try:
            if not 1 <= width <= 12000 or not 1 <= height <= 12000 or width * height > 1700000 or byte_count != width * height * 3:
                raise ValueError('OCR tile dimensions out of range')
            raw = read_exact(byte_count)
            image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))
            started = time.perf_counter(); result = engine(image)
            respond({'text': '\n'.join(lines(result)), 'initMs': init_ms,
                     'inferenceMs': round((time.perf_counter() - started) * 1000),
                     'peakMb': peak_mb(), 'pid': os.getpid()})
            init_ms = 0
        except Exception as exc:
            respond({'error': f'{type(exc).__name__}: {exc}', 'peakMb': peak_mb(), 'pid': os.getpid()})


if __name__ == '__main__':
    main()
