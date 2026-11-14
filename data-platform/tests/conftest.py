"""Configuration pytest pour les tests de data-platform.

Le dossier "jobs-spark" contient un tiret : Python ne peut pas l'importer comme un
paquet. On l'ajoute donc à la liste des dossiers où Python cherche les modules.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jobs-spark"))
