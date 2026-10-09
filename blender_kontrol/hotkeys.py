# -*- coding: utf-8 -*-
"""Orange komutlari Maya Hotkey Editor'da: her komut 'Orange' kategorisinde bir runTimeCommand.

Orange, Maya'nin kisayollarina ve etkin hotkey setine dokunmaz. Bu moduldeki komutlar yalnizca gorunur
kilinir: kullanici isterse Hotkey Editor'da kendi tusuna, rafa ya da marking menu'ye baglar (Orange
kapaliyken de calisir). Komutlar kullanici komutu olarak olusturulur (default=True olanlar silinemiyor):
Maya tercihlere kaydeder, boylece kullanicinin bunlara bagladigi tuslar Orange ac/kapa ile bozulmaz.
Her acilista guncellenir; yalnizca 'Orange'i kaldir' siler (installer.remove_runtime_commands).
"""
from __future__ import absolute_import, division, print_function

import re

import maya.cmds as cmds

from .core import _warn
from .i18n import EN
from .util import _last_view_panel
from .keymap import BINDINGS, _run_binding

CATEGORY = 'Orange'
PREFIX = 'Orange_'


def command_name(action_id):
    """Kararli, okunur ad: Ingilizce basliktan CamelCase ('Loop cut' -> Orange_LoopCut)."""
    title = EN.get(BINDINGS[action_id]['title'], BINDINGS[action_id]['title'])
    title = re.sub(r'\(.*?\)', ' ', title)
    words = re.findall(r'[A-Za-z0-9]+', title)
    return PREFIX + ''.join(w[:1].upper() + w[1:] for w in words)[:60]


def command_names():
    """{eylem: runTimeCommand adi}; ayni ada dusenler kombinasyonla ayrilir."""
    out, used = {}, set()
    for action, binding in sorted(BINDINGS.items()):
        if not binding.get('title'):
            continue
        name = command_name(action)
        if name in used:
            name = '%s_%s' % (name, re.sub(r'[^A-Za-z0-9]', '_', action))
        used.add(name)
        out[action] = name
    return out


def run_action(action_id):
    """runTimeCommand'larin cagirdigi giris noktasi."""
    binding = BINDINGS.get(action_id)
    if binding is None:
        _warn('Orange: %s' % action_id)
        return
    _run_binding(binding, _last_view_panel())


def register():
    """Komutlari olustur (var olanlari guncelle). Donus: olusturulan ad sayisi."""
    count = 0
    for action, name in command_names().items():
        title = BINDINGS[action]['title']
        annotation = 'Orange: %s  [%s]' % (EN.get(title, title), action)
        command = 'import blender_kontrol.hotkeys as _oh; _oh.run_action(%r)' % action
        try:
            if cmds.runTimeCommand(name, exists=True):
                if (cmds.runTimeCommand(name, q=True, command=True) == command and
                        cmds.runTimeCommand(name, q=True, annotation=True) == annotation):
                    count += 1
                    continue        # degismemis: kullanicinin tus atamasina dokunma
                cmds.runTimeCommand(name, edit=True, delete=True)
            cmds.runTimeCommand(name, category=CATEGORY, annotation=annotation, command=command,
                                commandLanguage='python')
            count += 1
        except Exception as exc:
            _warn('runTimeCommand %s: %s' % (name, exc))
    return count


def unregister():
    """Tum Orange komutlarini sil (yalnizca kaldirirken; ac/kapa'da kullanicinin tuslari bozulmasin)."""
    removed = 0
    for name in cmds.runTimeCommand(q=True, commandArray=True) or []:
        if name.startswith(PREFIX):
            try:
                if cmds.runTimeCommand(name, q=True, category=True) == CATEGORY:
                    cmds.runTimeCommand(name, edit=True, delete=True)
                    removed += 1
            except Exception:
                pass
    return removed
