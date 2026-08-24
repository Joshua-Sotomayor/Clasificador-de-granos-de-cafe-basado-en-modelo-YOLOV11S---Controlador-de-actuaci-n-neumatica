"""
Script ejecutor de todas las pruebas unitarias
"""
import sys
import os
import unittest

# Asegurar flush inmediato
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Asegurar que el directorio raíz esté en sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def ejecutar_pruebas():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    resultado = runner.run(suite)
    if resultado.wasSuccessful():
        print("\n>>> TODAS LAS PRUEBAS COMPLETADAS CON ÉXITO (100% PASS) <<<")
        os._exit(0)
    else:
        print("\n>>> ALGUNAS PRUEBAS FALLARON <<<")
        os._exit(1)

if __name__ == "__main__":
    ejecutar_pruebas()
