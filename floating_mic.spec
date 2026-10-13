# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

def get_zipformer_src():
    candidates = [
        'SpeechFunc/SherpaONNX/sherpa-onnx-zipformer',
        '../SherpaONNX/sherpa-onnx-zipformer',
        '../SpeechFunc/SherpaONNX/sherpa-onnx-zipformer'
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return 'SpeechFunc/SherpaONNX/sherpa-onnx-zipformer'

datas = [
    ('app_icon.ico', '.'),
    ('config.json', '.'),
    (get_zipformer_src(), 'SpeechFunc/SherpaONNX/sherpa-onnx-zipformer')
]

binaries = [
    ('floating_mic.*.pyd', '.'),
    ('stt_engine.*.pyd', '.')
]

hiddenimports = [
    'floating_mic',
    'stt_engine',
    'sounddevice',
    'pyperclip',
    'win32gui',
    'win32con',
    'win32api',
    'win32process',
    'sherpa_onnx',
    'numpy'
]

excludes = [
    'unittest', 'pydoc', 'email', 'html', 'http', 'xml', 'xmlrpc',
    'curses', 'sqlite3', 'asyncio', 'websockets', 'torch', 'matplotlib', 'PIL', 'scipy', 'pandas'
]

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

from PyInstaller.building.splash import Splash

splash = Splash(
    'splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    always_on_top=True
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FloatingMic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico'
)
