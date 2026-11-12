"""Test de DÉMONSTRATION : il échoue exprès si la variable CASSER_TEST_DEMO vaut 1.

But : montrer à l'oral que les tests bloquent bien la publication quand quelque chose casse.
    Windows (PowerShell) :  $env:CASSER_TEST_DEMO="1"; python -m pytest
    GitHub Actions       :  lancer le workflow avec l'option « casser_test_demo » cochée
Sans la variable, il passe toujours.
"""
import os


def test_demo_cassable():
    assert os.getenv("CASSER_TEST_DEMO") != "1", "Échec VOLONTAIRE pour la démo : la publication du site est bloquée."
