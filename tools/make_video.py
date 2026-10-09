# -*- coding: utf-8 -*-
"""PNG karelerden (tools/demo_capture.py) tanitim videosu ve GIF:
    python tools/make_video.py <kare_klasoru> [cikti.gif] [cikti.mp4] [--gif-width 900] [--mp4-width 1920]
                               [--gif-crop x,y,w,h] [--gif-every 2] [--fps 15]

Kare klasorundeki cursor.json'daki fare konumlarina ok imleci cizilir (ekran yakalama imleci almaz; tikta turuncu halka).
GIF icin istege bagli kirpma (tum Maya penceresi GIF'te kucuk kalir; genelde viewport bolgesi verilir).
MP4 icin ffmpeg gerekir: PATH'teki ffmpeg ya da imageio-ffmpeg paketi (pip install imageio-ffmpeg). Pillow gerekir."""
from __future__ import print_function

import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw


def _ffmpeg():
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def _draw_cursor(img, x, y, state):
    """Beyaz ok imleci, siyah kenar; tikta turuncu halka."""
    d = ImageDraw.Draw(img, 'RGBA')
    if state:
        d.ellipse((x - 22, y - 22, x + 22, y + 22), outline=(232, 163, 61, 230), width=4)
    pts = [(x, y), (x, y + 24), (x + 6, y + 19), (x + 10, y + 28), (x + 14, y + 26), (x + 10, y + 17), (x + 17, y + 17)]
    d.polygon(pts, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    d.line(pts + [pts[0]], fill=(0, 0, 0, 255), width=2)


def frames_with_cursor(src):
    """Kareleri imlec cizilmis olarak verir: (ad, PIL.Image)."""
    names = sorted(f for f in os.listdir(src) if f.endswith('.png'))
    cur = {'frames': []}
    path = os.path.join(src, 'cursor.json')
    if os.path.exists(path):
        with open(path) as fh:
            cur = json.load(fh)
    for i, name in enumerate(names):
        img = Image.open(os.path.join(src, name)).convert('RGB')
        if i < len(cur['frames']):
            x, y, state = cur['frames'][i]
            if 0 <= x < img.width and 0 <= y < img.height:
                _draw_cursor(img, x, y, state)
        yield name, img


def make_gif(src, out, width=900, fps=15, crop=None, every=1):
    """every: her N. kare (GIF boyutu icin; sure korunur)."""
    frames = []
    for i, (_name, img) in enumerate(frames_with_cursor(src)):
        if i % every:
            continue
        if crop:
            x, y, w, h = crop
            img = img.crop((x, y, x + w, y + h))
        h = int(img.height * width / float(img.width))
        frames.append(img.resize((width, h), Image.LANCZOS).quantize(colors=160, method=Image.Quantize.MEDIANCUT, dither=0))
    if not frames:
        raise SystemExit('kare yok: ' + src)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 * every / fps), loop=0, optimize=True)
    print('%s  %d kare  %d KB' % (out, len(frames), os.path.getsize(out) // 1024))


def make_mp4(src, out, width=1920, fps=15):
    exe = _ffmpeg()
    if not exe:
        print('ffmpeg yok, mp4 atlandi (pip install imageio-ffmpeg)')
        return
    tmp = tempfile.mkdtemp(prefix='orange_vid_')
    n = 0
    for _name, img in frames_with_cursor(src):
        h = int(round(img.height * width / float(img.width) / 2.0)) * 2       # h264 cift boyut ister
        img.resize((width, h), Image.LANCZOS).save(os.path.join(tmp, 'f%05d.png' % n))
        n += 1
    cmd = [exe, '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', os.path.join(tmp, 'f%05d.png'),
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'slow', '-movflags', '+faststart', out]
    subprocess.check_call(cmd)
    shutil.rmtree(tmp, ignore_errors=True)
    print('%s  %d kare  %d KB' % (out, n, os.path.getsize(out) // 1024))


def main(argv):
    opts = {'--gif-width': 900, '--mp4-width': 1920, '--fps': 15, '--gif-crop': None, '--gif-every': 1}
    args = []
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    src = args[0]
    fps = int(opts['--fps'])
    crop = tuple(int(v) for v in opts['--gif-crop'].split(',')) if opts['--gif-crop'] else None
    for out in args[1:]:
        if out.lower().endswith('.gif'):
            make_gif(src, out, int(opts['--gif-width']), fps, crop, int(opts['--gif-every']))
        elif out.lower().endswith('.mp4'):
            make_mp4(src, out, int(opts['--mp4-width']), fps)


if __name__ == '__main__':
    main(sys.argv[1:])
