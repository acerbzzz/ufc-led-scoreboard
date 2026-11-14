"""Display raw 64x32 RGB frames using the original Pi's Python 2 bindings."""
from __future__ import print_function

import subprocess
import sys


class LegacyDisplay(object):
    def __init__(self, args):
        self.process = subprocess.Popen(
            ["/usr/bin/python", "-u", __file__, args.mapping,
             str(args.brightness), str(args.gpio_slowdown)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        if self.process.stdout.readline() != b"READY\n":
            self.Clear()
            raise RuntimeError("Legacy matrix driver failed to start; see the error above.")

    def SetImage(self, image):
        self.process.stdin.write(image.tobytes())
        self.process.stdin.flush()

    def Clear(self):
        try:
            self.process.stdin.close()
        finally:
            self.process.wait()
            self.process.stdout.close()


def run(stream, ready, matrix):
    from PIL import Image
    frame_size = 64 * 32 * 3
    ready.write(b"READY\n")
    ready.flush()
    try:
        while True:
            data = stream.read(frame_size)
            if len(data) != frame_size:
                return
            matrix.SetImage(Image.frombytes("RGB", (64, 32), data))
    finally:
        matrix.Clear()


if __name__ == "__main__":
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    options = RGBMatrixOptions()
    options.rows, options.cols = 32, 64
    options.hardware_mapping = sys.argv[1]
    options.brightness = int(sys.argv[2])
    options.gpio_slowdown = int(sys.argv[3])
    run(getattr(sys.stdin, "buffer", sys.stdin), getattr(sys.stdout, "buffer", sys.stdout),
        RGBMatrix(options=options))
