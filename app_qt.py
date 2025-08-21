# app_qt.py
import json
import os
import sys
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextOption
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFileDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QPlainTextEdit,
    QGroupBox, QDialog, QSizePolicy
)

APP_DIR = Path(os.getcwd())  # runner.py'nin çalışacağı dizin


# -------------------- Arkaplan süreç işçisi --------------------
class RunnerWorker(QThread):
    # Canlı durum (tek satırlık status bar için)
    status = pyqtSignal(str)

    # Tamamlandığında konsol çıktısı
    done = pyqtSignal(str, str)           # stdout, stderr (stderr birleştirilmiş olabilir)
    failed = pyqtSignal(str)              # error text

    # JSON sonuçları (tip serbest: dict/list olabilir)
    finished_ok = pyqtSignal(object, object)  # use_cases(any), ollama_output(any)

    def __init__(self, python_path: str, doc_path: str, uc_limit: int, parent=None):
        super().__init__(parent)
        self.python_path = python_path
        self.doc_path = doc_path
        self.uc_limit = uc_limit

    def run(self):
        try:
            self.status.emit("Çalıştırma başlatılıyor…")
            cmd = [
                self.python_path or "python",
                "-u",  # unbuffered: canlı satır satır akış için
                "runner.py",
                "--doc", self.doc_path,
                "--uc-limit", str(self.uc_limit),
            ]

            # STDOUT ve STDERR'i tek kanalda toplayalım ki sıralı akış olsun
            proc = subprocess.Popen(
                cmd, cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )

            stdout_lines = []
            # Canlı satır okuma
            if proc.stdout is not None:
                for line in proc.stdout:
                    line = line.rstrip("\r\n")
                    if line:
                        stdout_lines.append(line)
                        self.status.emit(line)  # her satır statüs olsun

            ret = proc.wait()
            full_out = "\n".join(stdout_lines)
            full_err = ""  # STDERR'i STDOUT'a yönlendirdik

            if ret != 0:
                self.failed.emit(
                    f"runner.py çıkış kodu: {ret}\n\nKonsol çıktısı:\n{full_out}"
                )
                return

            # runner.py bittiyse json'ları oku
            uc_path = APP_DIR / "use_cases.json"
            oll_path = APP_DIR / "ollama_output.json"

            uc = self._read_json(uc_path)
            if uc_path.exists():
                try:
                    size = uc_path.stat().st_size
                    self.status.emit(f"use_cases.json oluşturuldu ({size} bayt)")
                except Exception:
                    self.status.emit("use_cases.json oluşturuldu")
            else:
                self.status.emit("use_cases.json bulunamadı")

            oll = self._read_json(oll_path)
            if oll_path.exists():
                try:
                    size = oll_path.stat().st_size
                    self.status.emit(f"ollama_output.json oluşturuldu ({size} bayt)")
                except Exception:
                    self.status.emit("ollama_output.json oluşturuldu")
            else:
                self.status.emit("ollama_output.json bulunamadı")

            self.done.emit(full_out, full_err)
            self.finished_ok.emit(uc, oll)

        except Exception as e:
            self.failed.emit(str(e))

    @staticmethod
    def _read_json(path: Path):
        try:
            if not path.exists():
                return {"__missing__": path.name}
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw)   # dict veya list gelebilir
        except Exception as e:
            return {"__read_error__": f"{path.name}: {e}"}


# -------------------- Detay Penceresi --------------------
class DetailsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detaylar")
        self.resize(1000, 700)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # use_cases.json
        grp_uc = QGroupBox("use_cases.json", self)
        self.txtUC = QPlainTextEdit(self); self._mono(self.txtUC); self.txtUC.setReadOnly(True)
        lay_uc = QVBoxLayout(grp_uc)
        lay_uc.addWidget(self.txtUC)

        # Console
        grp_console = QGroupBox("Console Çıktısı (runner.py)", self)
        self.txtStdout = QPlainTextEdit(self); self._mono(self.txtStdout); self.txtStdout.setReadOnly(True)
        self.txtStderr = QPlainTextEdit(self); self._mono(self.txtStderr); self.txtStderr.setReadOnly(True)

        lay_console = QGridLayout(grp_console)
        lay_console.addWidget(QLabel("STDOUT:", self), 0, 0)
        lay_console.addWidget(QLabel("STDERR:", self), 0, 1)
        lay_console.addWidget(self.txtStdout, 1, 0)
        lay_console.addWidget(self.txtStderr, 1, 1)

        lay.addWidget(grp_uc)
        lay.addWidget(grp_console)

        # Esnek büyüme
        grp_uc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grp_console.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _mono(self, txt: QPlainTextEdit):
        f = txt.font()
        f.setFamilies(["Consolas", "Monaco", "DejaVu Sans Mono", "monospace"])
        txt.setFont(f)
        txt.setWordWrapMode(QTextOption.WrapMode.NoWrap)

    # Dışarıdan doldurmak için arayüz:
    def set_use_cases(self, data):
        self.txtUC.setPlainText(self._pretty_json(data, "use_cases.json"))

    def set_stdout(self, text: str):
        self.txtStdout.setPlainText(text or "—")

    def set_stderr(self, text: str):
        self.txtStderr.setPlainText(text or "—")

    @staticmethod
    def _pretty_json(data, name: str):
        try:
            if data is None:
                return f"(Bulunamadı) {name}"
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"(Yazdırma Hatası) {name}\n{e}"


# -------------------- Ana Pencere --------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Use-Case Çıkarıcı (PyQt6)")
        self.resize(1100, 720)

        # Son değerleri tutmak için
        self._last_stdout = ""
        self._last_stderr = ""
        self._last_uc = None
        self._last_oll = None

        self.details_dialog: DetailsDialog | None = None
        self.worker: RunnerWorker | None = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Üst kontrol şeridi
        bar = QHBoxLayout()
        self.txtDoc = QLineEdit(self); self.txtDoc.setPlaceholderText("DOCX yolu…")
        btnBrowse = QPushButton("Gözat…", self); btnBrowse.clicked.connect(self.on_browse)

        self.spinUc = QSpinBox(self); self.spinUc.setMinimum(1); self.spinUc.setMaximum(999); self.spinUc.setValue(3)

        self.txtPython = QLineEdit(self); self.txtPython.setPlaceholderText("Python yolu (boş bırak: python)")
        self.btnRun = QPushButton("Çalıştır", self); self.btnRun.clicked.connect(self.on_run)

        self.btnDetails = QPushButton("Detayları Aç", self)
        self.btnDetails.clicked.connect(self.open_details)

        bar.addWidget(QLabel("DOCX:", self))
        bar.addWidget(self.txtDoc, stretch=1)
        bar.addWidget(btnBrowse)
        bar.addSpacing(16)
        bar.addWidget(QLabel("Use-Case Sayısı:", self))
        bar.addWidget(self.spinUc)
        bar.addSpacing(16)
        bar.addWidget(QLabel("Python:", self))
        bar.addWidget(self.txtPython, stretch=1)
        bar.addWidget(self.btnRun)
        bar.addWidget(self.btnDetails)

        # Bilgi satırı (küçük gri)
        info = QLabel("Çalışma dizini: uygulamanın bulunduğu klasör • Akış: runner.py → main.py → ai_bot.py", self)
        info.setWordWrap(True)
        info.setStyleSheet("color: gray;")

        # OLLAMA alanı (tam alan)
        self.grpOllama = QGroupBox("ollama_output.json", self)
        grpLay = QVBoxLayout(self.grpOllama)
        self.txtOLL = QPlainTextEdit(self)
        self._mono(self.txtOLL)
        self.txtOLL.setReadOnly(True)
        grpLay.addWidget(self.txtOLL)

        # --- STATUS BAR (tek satır) ---
        self.statusBar = QLabel(self)
        self.statusBar.setText("Hazır")
        self.statusBar.setStyleSheet("padding:6px; border-top:1px solid rgba(128,128,128,0.3); color: #2b2b2b;")
        self.statusBar.setMinimumHeight(28)
        self.statusBar.setWordWrap(False)
        self.statusBar.setToolTip("Son durum")

        # Yığma
        root.addLayout(bar)
        root.addWidget(info)
        root.addWidget(self.grpOllama)
        root.addWidget(self.statusBar)

        # OLLAMA paneli aşağı kadar büyüsün
        self.grpOllama.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.txtOLL.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.setStretchFactor(self.grpOllama, 1)

    def _mono(self, txt: QPlainTextEdit):
        f = txt.font()
        f.setFamilies(["Consolas", "Monaco", "DejaVu Sans Mono", "monospace"])
        txt.setFont(f)
        txt.setWordWrapMode(QTextOption.WrapMode.NoWrap)

    # -------------------- Eventler --------------------
    def on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "DOCX Belgesi Seç",
                                              str(Path.home()), "Word Document (*.docx)")
        if path:
            self.txtDoc.setText(path)

    def on_run(self):
        doc = self.txtDoc.text().strip()
        if not doc or not Path(doc).exists():
            self._show_error("(Hata) Lütfen geçerli bir DOCX dosyası seçin.")
            return

        uc_limit = int(self.spinUc.value())
        python_path = self.txtPython.text().strip() or "python"

        self._lock_ui(True)
        self._set_status("Çalıştırma başlatılıyor…")
        self.txtOLL.clear()
        self._last_stdout = ""
        self._last_stderr = ""
        self._last_uc = None
        self._last_oll = None

        self.worker = RunnerWorker(python_path, doc, uc_limit, self)
        self.worker.status.connect(self._on_status)         # canlı durum
        self.worker.done.connect(self._on_done_basic)       # konsol bufferları
        self.worker.failed.connect(self._on_failed)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.start()

    # Canlı durum
    def _on_status(self, msg: str):
        # Son satırı status bar'a yaz
        self._set_status(msg)

    def _on_done_basic(self, stdout: str, stderr: str):
        self._last_stdout = stdout or "—"
        self._last_stderr = stderr or "—"

    def _on_finished_ok(self, use_cases, ollama_output):
        self._last_uc = use_cases
        self._last_oll = ollama_output

        # Ana penceredeki OLLAMA alanını güncelle
        self.txtOLL.setPlainText(self._pretty_json(self._last_oll, "ollama_output.json"))
        self._set_status("Tamamlandı.")

        # Detay penceresi açıksa onu da güncelle
        if self.details_dialog is not None and self.details_dialog.isVisible():
            self.details_dialog.set_stdout(self._last_stdout)
            self.details_dialog.set_stderr(self._last_stderr)
            self.details_dialog.set_use_cases(self._last_uc)

        self._lock_ui(False)

    def _on_failed(self, msg: str):
        # Hata olursa OLLAMA paneline de yaz
        self.txtOLL.setPlainText(msg)
        self._set_status("Hata oluştu.")
        # Detay penceresi açıksa stderr'i doldur
        if self.details_dialog is not None and self.details_dialog.isVisible():
            self.details_dialog.set_stderr(msg)
        self._lock_ui(False)

    def open_details(self):
        if self.details_dialog is None:
            self.details_dialog = DetailsDialog(self)

        # Son değerlerle doldur
        self.details_dialog.set_stdout(self._last_stdout)
        self.details_dialog.set_stderr(self._last_stderr)
        self.details_dialog.set_use_cases(self._last_uc)

        # Modal değil: aynı anda hem ana pencere hem detay açık kalabilir
        self.details_dialog.show()
        self.details_dialog.raise_()
        self.details_dialog.activateWindow()

    def _pretty_json(self, data, name: str):
        try:
            if data is None:
                return f"(Bulunamadı) {name}"
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"(Yazdırma Hatası) {name}\n{e}"

    def _lock_ui(self, lock: bool):
        self.btnRun.setEnabled(not lock)
        self.btnDetails.setEnabled(not lock)

    def _show_error(self, text: str):
        self.txtOLL.setPlainText(text)
        self._set_status("Hata")

    def _set_status(self, text: str):
        # Çok uzun satırlar status bar'ı taşırmasın diye kırp
        maxlen = 140
        if len(text) > maxlen:
            text = text[:maxlen - 1] + "…"
        self.statusBar.setText(text)
        self.statusBar.setToolTip(text)

# -------------------- main --------------------
def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
