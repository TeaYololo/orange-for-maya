# -*- coding: utf-8 -*-
"""PNG karelerden GIF: python tools/make_gif.py <kare_klasoru> <cikti.gif> [genislik=720] [fps=12] [kirp_yuzde=15]
Kareler yanlardan kirp_yuzde kadar kirpilir (viewport kenarindaki paneller). Pillow gerekir."""
import os
import sys

from PIL import Image


def main(src, out, width=720, fps=12, crop=15):
    names = sorted(f for f in os.listdir(src) if f.endswith('.png'))
    frames = []
    for name in names:
        img = Image.open(os.path.join(src, name)).convert('RGB')
        dx = int(img.width * crop / 100.0)
        img = img.crop((dx, 0, img.width - dx, img.height))
        h = int(img.height * width / float(img.width))
        frames.append(img.resize((width, h), Image.LANCZOS).quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    if not frames:
        raise SystemExit('kare yok: ' + src)
    folder = os.path.dirname(os.path.abspath(out))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
    print('%s  %d kare  %d KB' % (out, len(frames), os.path.getsize(out) // 1024))


if __name__ == '__main__':
    args = sys.argv[1:]
    main(args[0], args[1], *(int(a) for a in args[2:]))
