"""Run CI checks with periodic stack dumps if a test stops making progress."""
import faulthandler
import unittest

if __name__ == '__main__':
    faulthandler.enable()
    faulthandler.dump_traceback_later(90, repeat=True)
    try:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('.',pattern='test_*.py'))
    finally:
        faulthandler.cancel_dump_traceback_later()
    raise SystemExit(0 if result.wasSuccessful() else 1)
