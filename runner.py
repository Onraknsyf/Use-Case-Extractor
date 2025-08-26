# runner.py
# -*- coding: utf-8 -*-
"""
Akış:
  1) main.py → DOCX'ten use_cases.json üret
  2a) --general ise: use_cases.json içindeki 'use_cases'=[] yap (yalnızca Bileşen Tasarımı)
  2b) değilse: selector.py ile --indices seçim yap → selected_usecases.json
      → seçileni geçici olarak use_cases.json yerine koy
  3) (opsiyonel) ai_bot.py → ollama_output.json üret
  4) seçim modunda use_cases.json yedeğini geri yükle

Notlar:
- Cache bayrakları ai_bot.py'ye iletilir (--use-cache, --force-refresh, --cache-dir).
- Çıktılar anında UI'ya düşsün diye stdout line-buffering açık.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
import shutil
import json

APP_DIR = Path(__file__).resolve().parent


# --- hızlı flush ve ortam bilgisi (debug) ---
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
print(f"[runner] cwd={os.getcwd()}", flush=True)
print(f"[runner] sys.executable={sys.executable}", flush=True)
print(f"[runner] argv={' '.join(sys.argv)}", flush=True)


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="DOCX → main.py → (opsiyonel selector.py) → (opsiyonel) ai_bot.py ardışık çalıştırıcı"
    )
    # Zorunlu
    p.add_argument("--doc", required=True, help="Kaynak DOCX dosyası")
    p.add_argument("--uc-limit", type=int, default=3, help="Maksimum UC sayısı (varsayılan: 3)")

    # GENERAL MODE: Use‑case yok → sadece Bileşen Tasarımı ile çalış
    p.add_argument("--general", action="store_true",
                   help="Use‑case YOK: yalnızca Bileşen Tasarımı ile görev üret (General Tasks)")

    # Seçim modu (general değilse)
    p.add_argument("--indices", help="Seçilecek UC numaraları (ör. 1,3-5)")

    # main.py opsiyonları
    p.add_argument("--start-title", default="Bileşen Tasarımı")
    p.add_argument("--stop-titles", default="Veri Tasarımı,Sistem Mimarisi")
    p.add_argument("--extra-stop-titles",
                   default=("hata dönüş kodları,genel tasarım modeli,döküman geliştirmeleri,"
                            "sms geliştirmeleri,rule engine gereksinimleri,job listesi"))
    p.add_argument("--temp-docx", default="use_cases.docx")
    p.add_argument("--output-json", default="use_cases.json")

    # selector.py / çıktı adı
    p.add_argument("--selected-json", default="selected_usecases.json")

    # ai_bot.py çalıştırmayı atla
    p.add_argument("--skip-ai", action="store_true", help="ai_bot.py çağrısını atlar")

    # Cache bayrakları (ai_bot.py’ye aktarılacak)
    p.add_argument("--use-cache", action="store_true", help="ai_bot için cache kullan")
    p.add_argument("--force-refresh", action="store_true", help="cache’i bypass et (hard refresh)")
    p.add_argument("--cache-dir", default=".ollama_cache", help="cache klasörü")
    p.add_argument("--model", default=None, help="ai_bot.py için model adı (opsiyonel)")
    p.add_argument("--output", default="ollama_output.json", help="ai_bot.py çıktı dosyası adı")

    # Python yolu
    p.add_argument("--python", default=sys.executable, help="Çalıştırılacak Python yorumlayıcısı")
    return p


def run_cmd(cmd, cwd=None):
    safe = [str(x) for x in cmd]
    print("➤", " ".join(safe), flush=True)
    proc = subprocess.run(safe, cwd=cwd, check=False)
    if proc.returncode != 0:
        print(f"❌ Komut hata ile döndü: {proc.returncode}", flush=True)
        raise SystemExit(proc.returncode)


def force_general_mode(json_path: Path):
    """use_cases listesini boşalt, yalnızca bileşen ile general mode'a zorla."""
    if not json_path.exists():
        print(f"❌ General mode için JSON bulunamadı: {json_path}", flush=True)
        raise SystemExit(2)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["use_cases"] = []
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("🟢 General mode aktif: use_cases=[] olarak yazıldı.", flush=True)
    except Exception as e:
        print(f"❌ General mode yazma hatası: {e}", flush=True)
        raise SystemExit(2)


def main():
    args = build_arg_parser().parse_args()
    cwd = str(APP_DIR)

    # 1) main.py: DOCX → use_cases.json
    print("▶️  main.py çalıştırılıyor…", flush=True)
    run_cmd([
        args.python, "main.py",
        "--doc", args.doc,
        "--uc-limit", str(args.uc_limit),
        "--start-title", args.start_title,
        "--stop-titles", args.stop_titles,
        "--extra-stop-titles", args.extra_stop_titles,
        "--temp-docx", args.temp_docx,
        "--output-json", args.output_json
    ], cwd=cwd)

    use_cases_json = APP_DIR / args.output_json

    if args.general:
        # 2.a) GENERAL MODE: selector adımını atla ve use_cases=[] yap
        force_general_mode(use_cases_json)
    else:
        # 2.b) SEÇİM MODU: selector.py ile seçimi uygula (indices zorunlu)
        if not args.indices:
            print("❌ --indices gerekli (ör. --indices 1,3-5) veya --general kullanın.", flush=True)
            raise SystemExit(2)

        print("▶️  selector.py çalıştırılıyor (seçim)…", flush=True)
        run_cmd([
            args.python, "selector.py",
            "--input", args.output_json,
            "--output", args.selected_json,
            "--indices", args.indices
        ], cwd=cwd)

        # selected_usecases.json → use_cases.json olarak geçici yerleştir, ai_bot çalıştır, sonra geri yükle
        selected_json = APP_DIR / args.selected_json
        backup_json   = APP_DIR / "use_cases.backup.json"

        if not selected_json.exists():
            print(f"❌ Seçim dosyası bulunamadı: {selected_json}", flush=True)
            raise SystemExit(3)

        if use_cases_json.exists():
            shutil.copyfile(use_cases_json, backup_json)
        shutil.copyfile(selected_json, use_cases_json)

    # 3) ai_bot.py: çalıştır (opsiyonel)
    if args.skip_ai:
        print("⏭️  --skip-ai verildi; ai_bot.py çalıştırılmayacak.", flush=True)
        print("🏁 Akış tamamlandı.", flush=True)
        return

    print("▶️  ai_bot.py çalıştırılıyor…", flush=True)
    ai_cmd = [args.python, "ai_bot.py", "--output", args.output]
    if args.use_cache:
        ai_cmd.append("--use-cache")
    if args.force_refresh:
        ai_cmd.append("--force-refresh")
    if args.cache_dir:
        ai_cmd += ["--cache-dir", args.cache_dir]
    if args.model:
        ai_cmd += ["--model", args.model]
    try:
        run_cmd(ai_cmd, cwd=cwd)
    finally:
        # yalnız seçim modunda geri yükleme yap
        if not args.general:
            backup_json = APP_DIR / "use_cases.backup.json"
            try:
                if backup_json.exists():
                    shutil.copyfile(backup_json, use_cases_json)
                    backup_json.unlink(missing_ok=True)
            except Exception as e:
                print(f"⚠️  use_cases.json geri yüklenirken sorun: {e}", flush=True)

    print("🏁 Akış tamamlandı. Çıktılar:", flush=True)
    print(f"   - {args.output_json}", flush=True)
    if not args.general:
        print(f"   - {args.selected_json}", flush=True)
    print(f"   - {args.output}", flush=True)


if __name__ == "__main__":
    main()
