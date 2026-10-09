# -*- coding: utf-8 -*-
"""icons/orange.svg -> icons/orange.png (32 px raf ikonu). PySide6 gerekir: python tools/make_icons.py"""
import os
import sys

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(size=32):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])  # noqa: F841
    renderer = QtSvg.QSvgRenderer(os.path.join(HERE, 'icons', 'orange.svg'))
    for px, name in ((size, 'orange.png'), (size * 2, 'orange_64.png')):
        image = QtGui.QImage(px, px, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        out = os.path.join(HERE, 'icons', name)
        image.save(out)
        print(out)


if __name__ == '__main__':
    main()
