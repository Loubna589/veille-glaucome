"""Le JavaScript de chaque page doit être syntaxiquement valide : une seule faute (guillemet) vide toute la page."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1] / "site"


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js absent")
def test_javascript_des_pages_valide(tmp_path):
    erreurs = []
    fichiers = [(p.name, s) for p in SITE.glob("*.html") for s in re.findall(r"<script>(.*?)</script>", p.read_text(encoding="utf-8"), re.S)]
    fichiers += [(p.name, p.read_text(encoding="utf-8")) for p in (SITE / "js").glob("*.js")]
    for i, (nom, code) in enumerate(fichiers):
        f = tmp_path / f"s{i}.{'mjs' if 'export ' in code else 'js'}"
        f.write_text(code, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        if r.returncode:
            erreurs.append(f"{nom} : {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else '?'}")
    assert not erreurs, erreurs
