"""Dataset preparation package.

This is a package rather than a loose folder for one specific reason: `inspect.py` in here
shadows the standard library's `inspect` module, and torch imports `inspect` internally.
Putting `ml/data/` on sys.path — which Python does automatically when you run
`python ml/data/inspect.py` — makes `import torch` fail with a bare
`module 'inspect' has no attribute 'signature'`, which is a genuinely baffling error to
land on at hour six.

Every script in here therefore drops its own directory from sys.path at startup and imports
its siblings as `data.<module>`. See the bootstrap block at the top of each file.
"""
