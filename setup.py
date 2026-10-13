from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize(["stt_engine.py", "floating_mic.py"], compiler_directives={'language_level': "3"})
)
