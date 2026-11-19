"""Tests du script de mise à jour : remplacement puis relance (le .bat lui-même ne tourne que sous Windows)."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from updater import build_update_bat, is_newer  # noqa: E402


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.bat = build_update_bat(r"C:\Apps\DofusTeam.exe", r"C:\Apps\DofusTeam_new.exe")
        self.lines = self.bat.split("\r\n")

    def test_remplace_puis_relance_apres_le_ren(self):
        i_ren = next(i for i, l in enumerate(self.lines) if l.startswith("ren "))
        i_start = next(i for i, l in enumerate(self.lines) if l.startswith('start ""'))
        i_giveup = self.lines.index(":giveup")
        self.assertLess(i_ren, i_start)
        self.assertLess(i_start, i_giveup)          # abandon (exe verrouillé) : aucune relance
        self.assertIn(r'start "" "C:\Apps\DofusTeam.exe"', self.bat)

    def test_vide_l_environnement_pyinstaller_avant_la_relance(self):
        i_start = next(i for i, l in enumerate(self.lines) if l.startswith('start ""'))
        before = self.lines[:i_start]
        for var in ("PYINSTALLER_RESET_ENVIRONMENT=1", "_MEIPASS2=", "_PYI_ARCHIVE_FILE=", "_PYI_APPLICATION_HOME_DIR=", "_PYI_PARENT_PROCESS_LEVEL="):
            self.assertIn(f"set {var}", before)

    def test_s_auto_supprime_et_limite_les_tentatives(self):
        self.assertIn("if %tries% GEQ 30 goto giveup", self.bat)
        self.assertEqual(self.lines[-2], 'del /f /q "%~f0"')

    def test_versions(self):
        self.assertTrue(is_newer("V3.07", "V3.06"))
        self.assertFalse(is_newer("V3.06", "V3.06"))


if __name__ == "__main__":
    unittest.main()
