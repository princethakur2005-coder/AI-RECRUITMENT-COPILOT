import sys, importlib
sys.path.insert(0, 'backend')
mod = importlib.import_module('app.main')
print('IMPORT_OK')
