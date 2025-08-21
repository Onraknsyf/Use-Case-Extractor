# Use-Case Extractor

Bu uygulama, verilen **DOCX belgelerinden** *use-case* senaryolarını çıkarır, JSON çıktısı üretir ve [Ollama](https://ollama.ai/) aracılığıyla seçilen dil modeline gönderip sonuçları döndürür.  
Kullanıcı dostu bir **PyQt6 masaüstü arayüzü** ile birlikte gelir.

---

## 🚀 Gereksinimler

- **Python 3.10+**
- **Ollama** ([ollama.ai](https://ollama.ai/download))
- İnternet bağlantısı (ilk kez model indirirken)
- Minimum 7.2 GB hafıza (kullanacağımız modelin boyutu)

---

## 🔧 Kurulum Adımları

### 1. Python Kütüphaneleri
Projeyi indirdikten sonra terminalden şu komutu çalıştırın:

```bash
pip install -r requirements.txt
```

### 2. Ollama ile Model
Gereksinimleri kurduktan sonra yukarıda verilmiş olan adresten Ollama yükleyin. Terminalden yüklemek isterseniz şu komutu çalıştırın:

```bash
winget install Ollama.Ollama
```

Ollama'nın düzgün kurulduğundan emin olmak için terminalde şu komutu çalıştırın:

```bash
ollama --version
```

Yapay Zeka modelini kurmak için şu komutu çalıştırın:

```bash
ollama pull mistral-nemo:12b-instruct-2407-q4_K_S
```

### 3. Dosya Yapısı
Tüm proje dosyalarının aynı klasörde olduğuna emin olun

project/
- app_qt.py
- main.py
- runner.py
- ai_bot.py
- requirements.txt
- README.md

---

## Çalıştırma

### 1. Terminal Üzerinde
Uygulamayı terminal üzerinde çalıştırmak için dosyanın bulunduğu directory'de bulunduğunuzdan emin olun ve şu komutu çalıştırın:

```bash
python app_qt.py
```

### 2. Paketleme Yaparak (Windows kullanıcıları için opsiyonel)
Windows kullanıcıları, programı ".exe" uzantılı hale getirip çalıştırmak için şu komutu çalıştırmalı:

```bash
pip install pyinstaller
pyinstaller --onefile app_qt.py
```

Dosyanın içinde oluşacak /dist klasörünün içinde uygulamayı bulabilirsiniz.

---

## Kullanım

Karşınıza çıkacak pencerede, üzerinde çalışmak istediğiniz ".docx" uzantılı dosyayı seçip, kullanmak istediğiniz use-case sayısını ayarlayıp "Çalıştır" butonuna basıp çalıştırabilirsiniz.

Detay butonuna basarak ara basamaklarda kullanılar çıktıları görebilirsiniz.

Pencerenin altında durum göstergesi vardır, hangi adımda olduğunuzu görebilirsiniz.

Model her bilgisayarda aynı hızda çalışmayacaktır, farklı VRAM-RAM boyutlarına göre farklı sürede çıktı alınması beklenir.