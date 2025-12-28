import json
import os
import sys
from pathlib import Path
import requests
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QFileDialog, QMessageBox

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("World Editor - Steampunk Generator")
        self.resize(680, 520)
        self.txt = QTextEdit(self)
        self.btn_gen = QPushButton("Générer Chunk", self)
        self.btn_stats = QPushButton("Voir Stats Chunk", self)
        self.btn_load_cfg = QPushButton("Charger config.json", self)
        lay = QVBoxLayout(self)
        lay.addWidget(self.btn_load_cfg)
        lay.addWidget(self.btn_gen)
        lay.addWidget(self.btn_stats)
        lay.addWidget(self.txt)
        self.cfg = self._load_cfg()
        self.btn_gen.clicked.connect(self.on_generate)
        self.btn_stats.clicked.connect(self.on_stats)
        self.btn_load_cfg.clicked.connect(self.on_load)

    def _load_cfg(self):
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        # default example
        example = Path(__file__).resolve().parents[1] / "config.example.json"
        return json.loads(example.read_text(encoding="utf-8"))

    def on_load(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choisir config.json", str(Path.cwd()), "JSON (*.json)")
        if p:
            with open(p, "r", encoding="utf-8") as f:
                self.cfg = json.load(f)
            QMessageBox.information(self, "Config", "Config chargée.")

    def _headers(self):
        key = self.cfg["api"].get("api_key")
        return {"x-api-key": key} if key else {}

    def on_generate(self):
        base = self.cfg["api"]["base_url"].rstrip("/")
        body = self.cfg["generator"]
        try:
            r = requests.post(f"{base}/api/generate/chunk", json=body, headers=self._headers(), timeout=60)
            r.raise_for_status()
            data = r.json()
            self.txt.setText(json.dumps(data, indent=2))
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def on_stats(self):
        base = self.cfg["api"]["base_url"].rstrip("/")
        chunk_id = None
        try:
            last = json.loads(self.txt.toPlainText() or "{}")
            chunk_id = last.get("chunk_id")
        except Exception:
            pass
        if not chunk_id:
            QMessageBox.warning(self, "Stats", "Aucun chunk_id (générez d'abord)")
            return
        try:
            r = requests.get(f"{base}/api/chunks/{chunk_id}/stats", headers=self._headers(), timeout=30)
            r.raise_for_status()
            data = r.json()
            self.txt.setText(json.dumps(data, indent=2))
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = App()
    w.show()
    sys.exit(app.exec())
