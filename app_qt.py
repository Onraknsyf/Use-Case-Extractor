# app_qt.py
# -*- coding: utf-8 -*-
import json, os, sys, subprocess
from pathlib import Path

try:
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QTextOption
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QFileDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QLineEdit, QPushButton, QSpinBox, QPlainTextEdit, QCheckBox,
        QGroupBox, QDialog, QSizePolicy, QMessageBox
    )
except Exception as e:
    print("PyQt6 yüklenemedi:", e)
    sys.exit(1)

APP_DIR = Path(__file__).resolve().parent  # script'in bulunduğu klasör


# =========================
#   ÇALIŞTIRMA İŞ PARÇACIĞI
# =========================
class RunnerWorker(QThread):
    status = pyqtSignal(str)
    done = pyqtSignal(str, str)
    failed = pyqtSignal(str)
    # use_cases, selected_usecases, ollama_output
    finished_ok = pyqtSignal(object, object, object)

    def __init__(self, python_path: str, doc_path: str, uc_limit: int,
                 indices: str, run_ai: bool, use_cache: bool, force_refresh: bool,
                 cache_dir: str, general_mode: bool, parent=None):
        super().__init__(parent)
        self.python_path = python_path
        self.doc_path = doc_path
        self.uc_limit = uc_limit
        self.indices = indices
        self.run_ai = run_ai
        self.use_cache = use_cache
        self.force_refresh = force_refresh
        self.cache_dir = cache_dir
        self.general_mode = general_mode
        self._proc = None

    def run(self):
        try:
            self.status.emit("Çalıştırma başlatılıyor…")

            runner = APP_DIR / "runner.py"
            mainp  = APP_DIR / "main.py"
            if not runner.exists():
                self.failed.emit(f"'runner.py' {APP_DIR} içinde bulunamadı.")
                return
            if not mainp.exists():
                self.failed.emit(f"'main.py' {APP_DIR} içinde bulunamadı.")
                return

            cmd = [
                self.python_path or "python", "-u", str(runner),
                "--doc", self.doc_path,
                "--uc-limit", str(self.uc_limit),
            ]

            if self.general_mode:
                cmd.append("--general")
            else:
                cmd += ["--indices", self.indices.strip()]

            # cache bayrakları
            if self.use_cache:
                cmd.append("--use-cache")
            if self.force_refresh:
                cmd.append("--force-refresh")
            if self.cache_dir:
                cmd += ["--cache-dir", self.cache_dir]

            if not self.run_ai:
                cmd.append("--skip-ai")

            # Komutu göster
            self.status.emit("Komut:\n" + " ".join([str(x) for x in cmd]))

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"

            self.status.emit("runner.py başlatılıyor…")
            self._proc = subprocess.Popen(
                cmd, cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                encoding="utf-8", errors="replace",
                env=env
            )

            stdout_lines = []
            if self._proc.stdout is not None:
                for line in self._proc.stdout:
                    line = line.rstrip("\r\n")
                    if line:
                        stdout_lines.append(line)
                        self.status.emit(line)

            ret = self._proc.wait()
            full_out = "\n".join(stdout_lines)
            full_err = ""

            if ret != 0:
                self.failed.emit(
                    f"runner.py çıkış kodu: {ret}\n\nKonsol çıktısı:\n{full_out}"
                )
                return

            # --- ÇIKTILARI TOPLA ---
            uc_path = APP_DIR / "use_cases.json"
            sel_path = APP_DIR / "selected_usecases.json"  # general modda oluşmayabilir
            oll_path = APP_DIR / "ollama_output.json"      # ai_bot.py OUTPUT_FILE

            uc_data = self._read_json(uc_path)
            sel_data = self._read_json(sel_path)
            oll_data = self._read_text_or_json(oll_path)

            self.status.emit(f"use_cases.json: {'bulundu' if uc_path.exists() else 'yok'}")
            self.status.emit(f"selected_usecases.json: {'bulundu' if sel_path.exists() else 'yok'}")
            self.status.emit(f"ollama_output.json: {'bulundu' if oll_path.exists() else 'yok'}")

            self.done.emit(full_out, full_err)
            self.finished_ok.emit(uc_data, sel_data, oll_data)

        except Exception as e:
            self.failed.emit(str(e))

    def terminate_gently(self):
        """Devam eden alt süreci nazikçe sonlandır (varsa)."""
        try:
            if self._proc and self._proc.poll() is None:
                self.status.emit("İş iptal ediliyor…")
                self._proc.terminate()
        except Exception:
            pass

    @staticmethod
    def _read_json(path: Path):
        try:
            if not path.exists():
                return {"__missing__": path.name}
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw)
        except Exception as e:
            return {"__read_error__": f"{path.name}: {e}"}

    @staticmethod
    def _read_text_or_json(path: Path):
        if not path.exists():
            return {"__missing__": path.name}
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            return json.loads(raw)  # dizi ya da sözlük olabilir
        except Exception:
            return {"__text__": raw[:200000]}  # ilk 200KB


# =========================
#   DETAY DİYALOĞU
# =========================
class DetailsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detaylar")
        self.resize(1200, 800)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)

        # use_cases.json
        grp_uc = QGroupBox("use_cases.json", self)
        self.txtUC = QPlainTextEdit(self); self._mono(self.txtUC); self.txtUC.setReadOnly(True)
        lay_uc = QVBoxLayout(grp_uc); lay_uc.addWidget(self.txtUC)

        # selected_usecases.json
        grp_sel = QGroupBox("selected_usecases.json", self)
        self.txtSEL = QPlainTextEdit(self); self._mono(self.txtSEL); self.txtSEL.setReadOnly(True)
        lay_sel = QVBoxLayout(grp_sel); lay_sel.addWidget(self.txtSEL)

        # ollama_output.json (veya metin)
        grp_oll = QGroupBox("ollama_output.json", self)
        self.txtOLL = QPlainTextEdit(self); self._mono(self.txtOLL); self.txtOLL.setReadOnly(True)
        lay_oll = QVBoxLayout(grp_oll); lay_oll.addWidget(self.txtOLL)

        # Konsol
        grp_console = QGroupBox("Console Çıktısı (runner.py)", self)
        self.txtStdout = QPlainTextEdit(self); self._mono(self.txtStdout); self.txtStdout.setReadOnly(True)
        self.txtStderr = QPlainTextEdit(self); self._mono(self.txtStderr); self.txtStderr.setReadOnly(True)
        lay_console = QGridLayout(grp_console)
        lay_console.addWidget(QLabel("STDOUT:", self), 0, 0)
        lay_console.addWidget(QLabel("STDERR:", self), 0, 1)
        lay_console.addWidget(self.txtStdout, 1, 0)
        lay_console.addWidget(self.txtStderr, 1, 1)

        lay.addWidget(grp_uc)
        lay.addWidget(grp_sel)
        lay.addWidget(grp_oll)
        lay.addWidget(grp_console)

        for g in (grp_uc, grp_sel, grp_oll, grp_console):
            g.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _mono(self, txt: QPlainTextEdit):
        f = txt.font(); f.setFamilies(["Consolas","Monaco","DejaVu Sans Mono","monospace"])
        txt.setFont(f); txt.setWordWrapMode(QTextOption.WrapMode.NoWrap)

    def set_use_cases(self, data): self.txtUC.setPlainText(self._pretty_json(data, "use_cases.json"))
    def set_selected(self, data): self.txtSEL.setPlainText(self._pretty_json(data, "selected_usecases.json"))
    def set_ollama(self, data): self.txtOLL.setPlainText(self._pretty_json(data, "ollama_output.json"))

    def set_stdout(self, text: str): self.txtStdout.setPlainText(text or "—")
    def set_stderr(self, text: str): self.txtStderr.setPlainText(text or "—")

    @staticmethod
    def _pretty_json(data, name: str):
        try:
            if data is None: 
                return f"(Bulunamadı) {name}"
            # metin geldiyse __text__ anahtarını göster
            if isinstance(data, dict) and "__text__" in data:
                return data["__text__"]
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"(Yazdırma Hatası) {name}\n{e}"


# =========================
#   ANA PENCERE
# =========================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Use-Case Çıkarıcı v2")
        self.resize(1240, 820)
        self.setFixedSize(self.size())
        self._last_stdout = ""; self._last_stderr = ""
        self._last_uc = None; self._last_sel = None; self._last_oll = None
        self.details_dialog = None
        self.worker = None
        # Uygulama kapanınca sileceğimiz ara dosyalar:
        self._temp_files = [
            "use_cases.json",
            "selected_usecases.json",
            "use_cases.backup.json",
        ]
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Üst bar
        bar1 = QHBoxLayout()
        bar2 = QHBoxLayout()
        self.txtDoc = QLineEdit(self); self.txtDoc.setPlaceholderText("DOCX yolu…")
        btnBrowse = QPushButton("Gözat…", self); btnBrowse.clicked.connect(self.on_browse)

        self.spinUc = QSpinBox(self); self.spinUc.setRange(1, 999); self.spinUc.setValue(5)

        # General Tasks modu
        self.chkGeneral = QCheckBox("Use‑case yok (General Tasks)", self)
        self.chkGeneral.stateChanged.connect(self._on_general_toggle)

        self.txtIndices = QLineEdit(self); self.txtIndices.setPlaceholderText("Seçilecek UC'ler: 1,3-5")
        self.chkRunAI = QCheckBox("AI çalıştır (ai_bot.py)", self); self.chkRunAI.setChecked(True)

        # CACHE kontrolü
        self.chkUseCache = QCheckBox("Cache kullan", self); self.chkUseCache.setChecked(True)
        self.chkForceRefresh = QCheckBox("Cache'i bypass et (hard refresh)", self)
        self.txtCacheDir = QLineEdit(self); self.txtCacheDir.setPlaceholderText("Cache klasörü (vars: .ollama_cache)")
        self.txtCacheDir.setText(".ollama_cache")

        self.txtPython = QLineEdit(self); self.txtPython.setPlaceholderText("boş bırakılabilir")
        self.btnRun = QPushButton("Çalıştır", self)
        self.btnRun.setStyleSheet("""
                                  QPushButton {
                                  background-color: #23da62;
                                  }
                                  QPushButton:hover {
                                  background-color: #1ab54a;
                                  }
                                  """)  # soluk yeşil
        self.btnRun.clicked.connect(self.on_run)

        # Reset ve Detay
        self.btnReset = QPushButton("Sıfırla", self)
        self.btnReset.setStyleSheet("""
                                    QPushButton {
                                    background-color: #f08080;
                                    }
                                    QPushButton:hover {
                                    background-color: #e04848;
                                    }
                                    """)  # soluk kırmızı
        self.btnReset.clicked.connect(self.on_reset)

        self.btnDetails = QPushButton("Detayları Aç", self); self.btnDetails.clicked.connect(self.open_details)

        bar1.addWidget(QLabel("DOCX:", self)); bar1.addWidget(self.txtDoc, 2); bar1.addWidget(btnBrowse)
        bar1.addSpacing(12); bar1.addWidget(self.chkGeneral)
        bar1.addSpacing(12); bar1.addWidget(QLabel("UC Limiti:", self)); bar1.addWidget(self.spinUc)
        bar1.addSpacing(12); bar1.addWidget(QLabel("Seçim:", self)); bar1.addWidget(self.txtIndices, 2)
        bar1.addSpacing(12); bar1.addWidget(QLabel("Cache Dir:", self)); bar1.addWidget(self.txtCacheDir, 1)
        bar1.addSpacing(12); bar1.addWidget(self.btnRun); bar1.addWidget(self.btnReset); 
        bar2.addWidget(self.chkRunAI); bar2.addWidget(self.chkUseCache); bar2.addWidget(self.chkForceRefresh,2); 
        bar2.addWidget(QLabel("Python Path:", self)); bar2.addWidget(self.txtPython) ;bar2.addWidget(self.btnDetails)
        info = QLabel(
            "Akış: runner.py → main.py (use_cases.json) → [general ise selector yok | değilse selector.py] → ai_bot.py (ollama_output.json)\n"
            f"Çalışma dizini: {APP_DIR}", self
        )
        info.setWordWrap(True); info.setStyleSheet("color: gray;")

        # Orta: hızlı çıktı görünümü (ollama veya seçili UC)
        self.grpCenter = QGroupBox("Çıktı Önizleme", self)
        grpLay = QVBoxLayout(self.grpCenter)
        self.txtCenter = QPlainTextEdit(self); self._mono(self.txtCenter); self.txtCenter.setReadOnly(True)
        grpLay.addWidget(self.txtCenter)

        # Status bar
        self.statusBar = QLabel(self); self.statusBar.setText("Hazır")
        self.statusBar.setStyleSheet("padding:6px; border-top:1px solid rgba(128,128,128,0.3); color:gray;")
        self.statusBar.setMinimumHeight(28); self.statusBar.setWordWrap(False)

        # compose
        root.addLayout(bar1)
        root.addLayout(bar2)
        root.addWidget(info)
        root.addWidget(self.grpCenter)
        root.addWidget(self.statusBar)
        self.grpCenter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.txtCenter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.setStretchFactor(self.grpCenter, 1)

        self._on_general_toggle()  # başlangıçta UI durumunu uygula

    def _on_general_toggle(self):
        is_general = self.chkGeneral.isChecked()
        self.txtIndices.setEnabled(not is_general)
        self.txtIndices.setPlaceholderText(
            "General Tasks modunda seçim kullanılmaz" if is_general else "Seçilecek UC'ler: 1,3-5"
        )

    def _mono(self, txt: QPlainTextEdit):
        f = txt.font(); f.setFamilies(["Consolas","Monaco","DejaVu Sans Mono","monospace"])
        txt.setFont(f); txt.setWordWrapMode(QTextOption.WrapMode.NoWrap)

    def on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "DOCX Belgesi Seç", str(Path.home()), "Word Document (*.docx)")
        if path: self.txtDoc.setText(path)

    def on_run(self):
        doc = self.txtDoc.text().strip()
        if not doc or not Path(doc).exists():
            return self._show_error("(Hata) Lütfen geçerli bir DOCX dosyası seçin.")

        general_mode = self.chkGeneral.isChecked()
        indices = self.txtIndices.text().strip()
        if not general_mode and not indices:
            return self._show_error("(Hata) Lütfen seçim (ör. 1,3-5) girin ya da 'Use‑case yok (General Tasks)' seçeneğini işaretleyin.")

        uc_limit = int(self.spinUc.value())
        python_path = self.txtPython.text().strip() or "python"
        run_ai = self.chkRunAI.isChecked()
        use_cache = self.chkUseCache.isChecked()
        force_refresh = self.chkForceRefresh.isChecked()
        cache_dir = self.txtCacheDir.text().strip() or ".ollama_cache"

        self._lock_ui(True); self._set_status("Çalıştırma başlatılıyor…")
        self.txtCenter.clear(); self._last_stdout = ""; self._last_stderr = ""
        self._last_uc = None; self._last_sel = None; self._last_oll = None

        self.worker = RunnerWorker(
            python_path, doc, uc_limit,
            indices, run_ai, use_cache, force_refresh, cache_dir, general_mode, self
        )
        self.worker.status.connect(self._on_status)
        self.worker.done.connect(self._on_done_basic)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.start()

    def on_reset(self):
        # 1) Çalışan iş varsa durdur
        if self.worker and self.worker.isRunning():
            ret = QMessageBox.question(
                self, "İşlem sürüyor",
                "Devam eden bir işlem var. İptal etmek istiyor musun?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret == QMessageBox.StandardButton.No:
                return
            try:
                self.worker.terminate_gently()
                self.worker.wait(3000)
            except Exception:
                pass

        # 2) UI / durum temizle
        self._last_stdout = ""; self._last_stderr = ""
        self._last_uc = None; self._last_sel = None; self._last_oll = None
        self.txtCenter.clear()
        self._set_status("Arayüz sıfırlandı.")
        self._lock_ui(False)

        # 3) Kullanıcıya sor: dosyalar da silinsin mi?
        ret = QMessageBox.question(
            self, "Dosyaları da sil?",
            "Çıktı dosyaları (use_cases.json, selected_usecases.json, ollama_output.json) da silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            removed = []
            for name in ("use_cases.json", "selected_usecases.json", "ollama_output.json"):
                p = APP_DIR / name
                try:
                    if p.exists():
                        p.unlink()
                        removed.append(name)
                except Exception as e:
                    QMessageBox.warning(self, "Silme hatası", f"{name} silinemedi: {e}")
            if removed:
                self._set_status("Silinen dosyalar: " + ", ".join(removed))
            else:
                self._set_status("Silinecek dosya yoktu.")

    def _on_status(self, msg: str): self._set_status(msg)

    def _on_done_basic(self, stdout: str, stderr: str):
        self._last_stdout = stdout or "—"; self._last_stderr = stderr or "—"

    @staticmethod
    def _is_present(obj) -> bool:
        # Mevcut sayılma kuralı: obj None değilse ve "__missing__" anahtarını
        # taşıyan bir hata-sözlüğü değilse var kabul et.
        if obj is None:
            return False
        return not (isinstance(obj, dict) and "__missing__" in obj)

    def _on_finished_ok(self, use_cases, selected_usecases, ollama_output):
        self._last_uc = use_cases
        self._last_sel = selected_usecases
        self._last_oll = ollama_output

        # Öncelik: AI çalıştıysa ollama_output, değilse selected_usecases, değilse use_cases
        if self._is_present(self._last_oll):
            self.txtCenter.setPlainText(self._pretty_json(self._last_oll, "ollama_output.json"))
        else:
            if os.path.exists(APP_DIR / "selected_usecases.json"):
                self.txtCenter.setPlainText(self._pretty_json(self._last_sel, "selected_usecases.json"))
            else:
                self.txtCenter.setPlainText(self._pretty_json(self._last_uc, "use_cases.json"))

        self._set_status("Tamamlandı.")
        if self.details_dialog and self.details_dialog.isVisible():
            self.details_dialog.set_stdout(self._last_stdout)
            self.details_dialog.set_stderr(self._last_stderr)
            self.details_dialog.set_use_cases(self._last_uc)
            self.details_dialog.set_selected(self._last_sel)
            self.details_dialog.set_ollama(self._last_oll)
        self._lock_ui(False)

    def _on_failed(self, msg: str):
        self.txtCenter.setPlainText(msg); self._set_status("Hata oluştu.")
        if self.details_dialog and self.details_dialog.isVisible():
            self.details_dialog.set_stderr(msg)
        self._lock_ui(False)

    def open_details(self):
        if not self.details_dialog:
            self.details_dialog = DetailsDialog(self)
        self.details_dialog.set_stdout(self._last_stdout)
        self.details_dialog.set_stderr(self._last_stderr)
        self.details_dialog.set_use_cases(self._last_uc)
        self.details_dialog.set_selected(self._last_sel)
        self.details_dialog.set_ollama(self._last_oll)
        self.details_dialog.show(); self.details_dialog.raise_(); self.details_dialog.activateWindow()

    @staticmethod
    def _pretty_json(data, name: str):
        try:
            if data is None: return f"(Bulunamadı) {name}"
            if isinstance(data, dict) and "__text__" in data:
                return data["__text__"]
            return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e: return f"(Yazdırma Hatası) {name}\n{e}"

    def _lock_ui(self, lock: bool):
        self.btnRun.setEnabled(not lock)
        self.btnDetails.setEnabled(not lock)
        self.btnReset.setEnabled(True)  # reset her zaman kullanılabilsin

    def _show_error(self, text: str):
        self.txtCenter.setPlainText(text); self._set_status("Hata")
        QMessageBox.critical(self, "Hata", text)

    def _set_status(self, text: str):
        maxlen = 400
        if len(text) > maxlen: text = text[:maxlen-1] + "…"
        self.statusBar.setText(text); self.statusBar.setToolTip(text)

    def closeEvent(self, event):
        """Uygulama kapanırken ara dosyaları temizle."""
        # 1) Çalışan iş parçacığını nazikçe durdur
        try:
            if self.worker and self.worker.isRunning():
                self.worker.terminate_gently()
                self.worker.wait(2000)
        except Exception:
            pass

        # 2) Dosyaları sil
        removed = []
        for name in self._temp_files:
            p = (APP_DIR / name)
            try:
                if p.exists():
                    p.unlink()
                    removed.append(name)
            except Exception:
                pass

        event.accept()
# =========================
#   UYGULAMA GİRİŞİ
# =========================
def main():
    app = QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
