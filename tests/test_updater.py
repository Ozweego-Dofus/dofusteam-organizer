"""Tests du script de mise à jour : remplacement puis relance (le .bat lui-même ne tourne que sous Windows)."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from updater import build_update_bat, is_newer, parse_sha_text, file_sha256  # noqa: E402


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

    def test_empreinte_sha256(self):
        h = "a" * 64
        self.assertEqual(parse_sha_text(f"{h.upper()}  DofusTeam.exe\n"), h)
        self.assertEqual(parse_sha_text("pas une empreinte"), "")
        self.assertEqual(parse_sha_text(""), "")
        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"abc"); name = f.name
        try:
            self.assertEqual(file_sha256(name), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        finally:
            os.unlink(name)


if __name__ == "__main__":
    unittest.main()
