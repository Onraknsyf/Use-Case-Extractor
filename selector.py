# selector.py
# -*- coding: utf-8 -*-
"""
use_cases.json içinden istenen UC'leri seçip selected_usecases.json'a yazar.
İsteğe bağlı olarak ai_bot.py'yi, seçili UC'lerle çalışacak şekilde tetikler.

Örnekler:
  # UC listesini gör:
  python selector.py --list

  # 2. ve 4.-6. UC'leri seçip kaydet:
  python selector.py --indices 2,4-6

  # Seçileni kaydedip modeli çalıştır:
  python selector.py --indices 1,3 --run-ai

Notlar:
- ai_bot.py doğrudan 'use_cases.json' dosyasını okuyor. --run-ai kullanıldığında:
  1) mevcut use_cases.json yedeklenir (use_cases.backup.json),
  2) selected_usecases.json -> use_cases.json olarak kopyalanır,
  3) ai_bot.py çalıştırılır,
  4) yedek geri yüklenir.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

APP_DIR = Path(__file__).resolve().parent


def load_use_cases(path: Path) -> Tuple[str, List[dict]]:
    if not path.exists():
        raise FileNotFoundError(f"Girdi bulunamadı: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"JSON okunamadı: {path} ({e})")
    bilesen = (data.get("bilesen_tasarimi") or "").strip()
    use_cases = data.get("use_cases") or []
    if not isinstance(use_cases, list):
        raise ValueError("use_cases alanı beklenen list tipinde değil.")
    return bilesen, use_cases


def save_selected(path: Path, bilesen: str, selected: List[dict]) -> None:
    out = {
        "bilesen_tasarimi": bilesen,
        "use_cases": selected,
    }
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_indices(spec: str, max_len: int) -> List[int]:
    """
    '1,3-5,8' -> [1,3,4,5,8] (1-based giriş, sonuç 0-based indeksler döner)
    """
    picked = set()
    parts = [p.strip() for p in (spec or "").split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            a, b = p.split("-", 1)
            a = a.strip(); b = b.strip()
            if not a.isdigit() or not b.isdigit():
                raise ValueError(f"Geçersiz aralık: {p}")
            start, end = int(a), int(b)
            if start <= 0 or end <= 0:
                raise ValueError(f"Aralık pozitif olmalı: {p}")
            if end < start:
                start, end = end, start
            for k in range(start, end + 1):
                if k <= max_len:
                    picked.add(k - 1)
        else:
            if not p.isdigit():
                raise ValueError(f"Geçersiz sıra: {p}")
            k = int(p)
            if k <= 0:
                raise ValueError(f"Pozitif sıra beklenir: {p}")
            if k <= max_len:
                picked.add(k - 1)
    ordered = sorted(picked)
    if not ordered:
        raise ValueError("Seçim boş. --indices ile en az bir UC belirtin.")
    return ordered


def list_use_cases(use_cases: List[dict]) -> None:
    print("\n--- Kullanılabilir Use Case Listesi ---")
    for i, uc in enumerate(use_cases, 1):
        title = (uc.get("title") or "").strip()
        desc = (uc.get("description") or "").strip()
        short = desc.replace("\r", " ").replace("\n", " ")
        if len(short) > 120:
            short = short[:117] + "..."
        print(f"{i:>2}. {title}")
        if short:
            print(f"    {short}")
    print("---------------------------------------\n")


def run_ai_with_selected(selected_path: Path, python_exe: str = None) -> int:
    """
    ai_bot.py yalnızca 'use_cases.json' okuduğundan:
    - mevcut use_cases.json -> use_cases.backup.json
    - selected_usecases.json -> use_cases.json
    - ai_bot.py çalıştır
    - yedeği geri yükle
    """
    python_exe = python_exe or sys.executable
    use_cases_json = APP_DIR / "use_cases.json"
    backup_json = APP_DIR / "use_cases.backup.json"

    # 1) Yedekle
    if use_cases_json.exists():
        shutil.copyfile(use_cases_json, backup_json)

    # 2) Seçileni aktif dosya adıyla yerleştir
    shutil.copyfile(selected_path, use_cases_json)

    # 3) Çalıştır
    print("▶️  ai_bot.py çalıştırılıyor (seçili UC'ler ile)...")
    try:
        ret = subprocess.run([python_exe, str(APP_DIR / "ai_bot.py")], check=False)
        code = ret.returncode
    except Exception as e:
        code = 1
        print(f"❌ ai_bot.py çalıştırma hatası: {e}")

    # 4) Geri yükle
    try:
        if backup_json.exists():
            shutil.copyfile(backup_json, use_cases_json)
            backup_json.unlink(missing_ok=True)
        else:
            # Yedek yoksa seçili dosyayı orada bırakmayalım:
            # (İsterseniz yorum satırı yapabilirsiniz)
            pass
    except Exception as e:
        print(f"⚠️  use_cases.json geri yüklenirken sorun: {e}")

    return code


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="use_cases.json içinden UC seç ve selected_usecases.json'a yaz."
    )
    p.add_argument("--input", default=str(APP_DIR / "use_cases.json"),
                   help="Girdi JSON yolu (varsayılan: ./use_cases.json)")
    p.add_argument("--output", default=str(APP_DIR / "selected_usecases.json"),
                   help="Çıktı JSON yolu (varsayılan: ./selected_usecases.json)")
    p.add_argument("--indices", default="",
                   help="Seçim: '1,3-5' gibi (1-based). Örn: --indices 2,4-6")
    p.add_argument("--list", action="store_true",
                   help="Sadece UC listesini yazdır ve çık.")
    p.add_argument("--run-ai", action="store_true",
                   help="Seçilen UC'lerle ai_bot.py'yi çalıştır (geçici kopyalama yöntemiyle).")
    p.add_argument("--python", default=sys.executable,
                   help="ai_bot.py için Python yolu (varsayılan: mevcut yorumlayıcı)")
    return p


def main():
    args = build_arg_parser().parse_args()
    in_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()

    bilesen, use_cases = load_use_cases(in_path)

    if args.list or not args.indices:
        # Listeyi her durumda göster; indices yoksa yalnızca bilgi ver.
        list_use_cases(use_cases)
        if not args.indices:
            print("Bilgi: Seçim yapmak için örnek:")
            print("  python selector.py --indices 2,4-6")
            return

    # Seçimi uygula
    idxs = parse_indices(args.indices, len(use_cases))
    selected = [use_cases[i] for i in idxs]

    # Kaydet
    save_selected(out_path, bilesen, selected)
    print(f"✅ Seçilen {len(selected)} UC, '{out_path.name}' dosyasına yazıldı.")

    # İsteğe bağlı model çalıştırma
    if args.run_ai:
        code = run_ai_with_selected(out_path, python_exe=args.python)
        if code == 0:
            print("✅ ai_bot.py başarıyla tamamlandı.")
        else:
            print(f"❌ ai_bot.py hata kodu: {code}")
        sys.exit(code)


if __name__ == "__main__":
    main()
