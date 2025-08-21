# runner.py
import argparse
import subprocess
import sys
import os

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="main.py ile use_cases.json üretir, ardından ai_bot.py ile görevleri çıkarır."
    )
    p.add_argument("--doc", required=True, help="Kaynak DOCX dosyası")
    p.add_argument("--uc-limit", type=int, default=3, help="Maksimum UC sayısı (varsayılan: 3)")
    # Aşağıdaki opsiyonları istersen UI'dan da geçirtebilirsin:
    p.add_argument("--start-title", default="Bileşen Tasarımı", help="Başlangıç başlığı")
    p.add_argument("--stop-titles", default="Veri Tasarımı,Sistem Mimarisi", help="Bitirici üst başlıklar (virgül ile)")
    p.add_argument("--extra-stop-titles", default="hata dönüş kodları,genel tasarım modeli,döküman geliştirmeleri,sms geliştirmeleri,rule engine gereksinimleri,job listesi",
                   help="UC toplamayı durduracak ek başlıklar (virgül ile)")
    p.add_argument("--temp-docx", default="use_cases.docx", help="Geçici docx adı")
    p.add_argument("--output-json", default="use_cases.json", help="main.py JSON çıktısı")
    p.add_argument("--python", default=sys.executable, help="Çalıştırılacak Python yorumlayıcısı")
    return p

def run_pipeline(args):
    env = os.environ.copy()

    main_cmd = [
        args.python, "main.py",
        "--doc", args.doc,
        "--uc-limit", str(args.uc_limit),
        "--start-title", args.start_title,
        "--stop-titles", args.stop_titles,
        "--extra-stop-titles", args.extra_stop_titles,
        "--temp-docx", args.temp_docx,
        "--output-json", args.output_json
    ]

    print("▶️ main.py çalıştırılıyor...")
    try:
        subprocess.run(main_cmd, check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"❌ main.py hata kodu: {e.returncode}")
        sys.exit(e.returncode)

    if not os.path.exists(args.output_json):
        print(f"❌ Beklenen çıktı bulunamadı: {args.output_json}")
        sys.exit(2)

    print("▶️ ai_bot.py çalıştırılıyor...")
    ai_cmd = [args.python, "ai_bot.py"]
    try:
        subprocess.run(ai_cmd, check=True, env=env)
    except subprocess.CalledProcessError as e:
        print(f"❌ ai_bot.py hata kodu: {e.returncode}")
        sys.exit(e.returncode)

    print("✅ Tamamlandı. Çıktılar: use_cases.json ve ollama_output.json")

if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    run_pipeline(args)
