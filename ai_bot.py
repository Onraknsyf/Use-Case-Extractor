# ai_bot.py
import json
import requests
import re
from textwrap import dedent

OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL_NAME  = "mistral-nemo:12b-instruct-2407-q4_K_S"     # JSON disiplininde iyi; istersen "llama3"/"phi3"
OUTPUT_FILE = "ollama_output.json"
TIMEOUT_SEC = 999

def query_ollama(prompt, model=MODEL_NAME):
    payload = {"model": model, "prompt": prompt, "stream": False}
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SEC)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        print(f"❌ API hatası: {e}")
        return ""

def parse_uc_title(full_title):
    sep = "–" if "–" in full_title else "-"
    parts = [p.strip() for p in full_title.split(sep, 1)]
    if len(parts) == 2:
        return full_title.strip(), parts[0], parts[1]
    return full_title.strip(), full_title.strip(), ""

# ---------- JSON çekirdek ayrıştırıcılar ----------

def extract_json_arrays_and_objects(text):
    """ Metindeki JSON array/object parçalarını (code fence içi dahil) ham string olarak döndür. """
    matches = []
    fence_blocks = re.findall(r"```(?:json|JSON)?\s*(.*?)```", text, flags=re.DOTALL)
    blocks = fence_blocks if fence_blocks else [text]
    for block in blocks:
        for m in re.finditer(r"\[\s*{.*?}\s*\]", block, flags=re.DOTALL):
            matches.append(m.group(0))
        for m in re.finditer(r"\{.*?\}", block, flags=re.DOTALL):
            matches.append(m.group(0))
    uniq = []
    for s in matches:
        s2 = s.strip()
        if s2 and s2 not in uniq:
            uniq.append(s2)
    return uniq

def try_load_json_array(text):
    """ Metinden JSON array elde etmeye çalış: tümü, gömülü array, veya toplanmış objectler. """
    t = text.strip()
    if t.startswith("[") and t.endswith("]"):
        return json.loads(t)
    m = re.search(r"\[\s*{.*?}\s*\]", t, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    pieces = extract_json_arrays_and_objects(t)
    objects = []
    for p in pieces:
        try:
            parsed = json.loads(p)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        objects.append(item)
            elif isinstance(parsed, dict):
                objects.append(parsed)
        except Exception:
            continue
    if objects:
        return objects
    raise ValueError("Geçerli JSON array / object bulunamadı.")

def maybe_parse_embedded_json(s):
    """
    Bir string'in içinde JSON array/object var mı? Varsa parse edip dict listesi döndür.
    Yoksa None döndür.
    """
    if not isinstance(s, str):
        return None
    txt = s.strip()
    # code fence içi
    m = re.search(r"```(?:json|JSON)?\s*(.*?)```", txt, flags=re.DOTALL)
    if m:
        txt = m.group(1).strip()
    # json array/object dene
    try:
        parsed = json.loads(txt)
        if isinstance(parsed, list):
            return [o for o in parsed if isinstance(o, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        # gömülü array/object ara
        pieces = extract_json_arrays_and_objects(txt)
        out = []
        for p in pieces:
            try:
                parsed = json.loads(p)
                if isinstance(parsed, list):
                    out += [o for o in parsed if isinstance(o, dict)]
                elif isinstance(parsed, dict):
                    out.append(parsed)
            except Exception:
                continue
        return out or None
    return None

def fallback_tasks_from_text(resp_text, usecase_label):
    """
    JSON array yoksa:
    - code fence içindeki JSON'ları tek tek task'a çevir,
    - yoksa '**Task N**' / 'Task N:' başlıklarına göre parçala,
    - en sonda failsafe tek görev.
    """
    tasks = []

    # 1) code fence içinden JSON çek
    fence_blocks = re.findall(r"```(?:json|JSON)?\s*(.*?)```", resp_text, flags=re.DOTALL)
    for block in fence_blocks:
        try:
            parsed = json.loads(block.strip())
            if isinstance(parsed, dict):
                tasks.append({
                    "usecase": usecase_label,
                    "title": (parsed.get("title") or "TASK").strip(),
                    "description": (parsed.get("description") or "").strip(),
                    "testCase": (parsed.get("testCase") or parsed.get("testcase") or "").strip()
                })
            elif isinstance(parsed, list):
                for obj in parsed:
                    if isinstance(obj, dict):
                        tasks.append({
                            "usecase": usecase_label,
                            "title": (obj.get("title") or "TASK").strip(),
                            "description": (obj.get("description") or "").strip(),
                            "testCase": (obj.get("testCase") or obj.get("testcase") or "").strip()
                        })
        except Exception:
            continue
    if tasks:
        return tasks

    # 2) "Task N" böl
    chunks = re.split(r"(?i)(?=^\s*(\*\*)?\s*task\s*\d+(\*\*)?\s*:?)", resp_text, flags=re.MULTILINE)
    merged, buf = [], ""
    for part in chunks:
        if re.match(r"(?i)^\s*(\*\*)?\s*task\s*\d+(\*\*)?\s*:?", part.strip()):
            if buf:
                merged.append(buf.strip())
            buf = part
        else:
            buf += part
    if buf.strip():
        merged.append(buf.strip())

    for chunk in merged:
        m_title = re.match(r"(?i)^\s*(\*\*)?\s*task\s*(\d+)(\*\*)?\s*:?\s*(.*)", chunk)
        if not m_title:
            continue
        n = m_title.group(2)
        rest = chunk[m_title.end():].strip()
        tc_match = re.search(r"(?i)test\s*case\s*:\s*(.+)", rest, flags=re.DOTALL)
        test_case = tc_match.group(1).strip() if tc_match else ""
        description = rest if not tc_match else rest[: rest.lower().find("test case")].strip()
        tail_title = m_title.group(4).strip()
        title = f"TASK {n}" + (f": {tail_title}" if tail_title else "")
        tasks.append({
            "usecase": usecase_label,
            "title": title,
            "description": description,
            "testCase": test_case
        })

    if tasks:
        return tasks

    # 3) failsafe
    if resp_text.strip():
        return [{
            "usecase": usecase_label,
            "title": "TASK 1",
            "description": resp_text.strip(),
            "testCase": ""
        }]
    return []

# ---------- Prompt'lar ----------

def prompt_for_tasks(bilesen, uc_full_title, uc_description):
    return dedent(f"""
    Aşağıda bir sistemin bileşen tasarımı açıklaması ve bir use case yer almaktadır.
    Gerektiği kadar görev üret ve her görevi AYRI bir JSON nesnesi olarak DİZİ halinde döndür.

    ZORUNLU ÇIKTI:
    - TÜRKÇE olması ZORUNLU ve TARTIŞMASIZ.
    - Kesinlikle İngilizce istemiyorum.
    - SADECE geçerli bir JSON ARRAY döndür.
    - Markdown, açıklama metni, başlık, code fence (```), üç tırnak KULLANMA.
    - Her elemanda alanlar:
      "title": "GÖREV N: <kısa başlık>",
      "description": "<görevin detay açıklaması>",
      "testCase": "<test adımları veya kabul kriterleri>"

    Bileşen Tasarımı:
    {bilesen}

    Use Case:
    {uc_full_title}
    Açıklama:
    {uc_description}

    ÖRNEK FORMAT (içeriği üret):
    [
      {{
        "usecase": "UC - 1",
        "title": "GÖREV 1: ...",
        "description": "...",
        "testCase": "..."
      }},
      {{
        "usecase": "UC - 1",
        "title": "GÖREV 2: ...",
        "description": "...",
        "testCase": "..."
      }}
      {{
        "usecase": "UC - 1",
        "title": "GÖREV 3: ...",
        "description": "...",
        "testCase": "..."
      }}
      ....
      {{
        "usecase": "UC - 2",
        "title": "GÖREV 1: ...",
        "description": "...",
        "testCase": "..."
      }},
      {{
        "usecase": "UC - 2",
        "title": "GÖREV 2: ...",
        "description": "...",
        "testCase": "..."
      }}
      ....
    ]
    """)

def prompt_for_general_tasks(bilesen):
    return dedent(f"""
    Aşağıdaki bileşen tasarımı açıklamasına göre gerektiği kadar görev üret.
    Her görevi AYRI bir JSON nesnesi olarak DİZİ halinde döndür. 

    ZORUNLU ÇIKTI:
    - TÜRKÇE olması ZORUNLU ve TARTIŞMASIZ.
    - Kesinlikle İngilizce istemiyorum.
    - SADECE geçerli bir JSON ARRAY döndür.
    - Markdown, açıklama metni, başlık, code fence (```), üç tırnak KULLANMA.
    - Her elemanda alanlar(TÜRKÇE olması ZORUNLU):
      "title": "GÖREV N: <kısa başlık>",
      "description": "<görevin detay açıklaması>",
      "testCase": "<test adımları veya kabul kriterleri>"

    Bileşen Tasarımı:
    {bilesen}


    ÖRNEK FORMAT (içeriği üret):
    [
      {{
        "title": "GÖREV 1: ...",
        "description": "...",
        "testCase": "..."
      }},
      {{
        "title": "GÖREV 2: ...",
        "description": "...",
        "testCase": "..."
      }}
    ]
    """)

# ---------- Temizleme ----------

def dedupe_and_normalize(tasks):
    seen = set()
    cleaned = []
    for t in tasks:
        title = (t.get("title") or "").strip()
        desc  = (t.get("description") or "").strip()
        tc    = (t.get("testCase") or t.get("testcase") or "").strip()
        uc    = (t.get("usecase") or "").strip()
        if not title:
            continue
        key = (uc, title, desc, tc)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"usecase": uc, "title": title, "description": desc, "testCase": tc})
    return cleaned

def expand_embedded_lists(batch, default_usecase):
    """
    Bazı modeller tek bir objenin description'ına JSON array stringi gömüyor.
    Bu fonksiyon, o iç listeyi parse eder ve ayrı görevlere genişletir.
    """
    expanded = []
    for obj in batch:
        usecase = (obj.get("usecase") or default_usecase).strip()
        title   = (obj.get("title") or "").strip()
        desc    = obj.get("description")
        tc      = (obj.get("testCase") or obj.get("testcase") or "").strip()

        embedded = maybe_parse_embedded_json(desc)
        if embedded:
            # iç listedeki her elemanı ayrı göreve çevir
            for inner in embedded:
                expanded.append({
                    "usecase": usecase,
                    "title": (inner.get("title") or "").strip() or title or "TASK",
                    "description": (inner.get("description") or "").strip() or "",
                    "testCase": (inner.get("testCase") or inner.get("testcase") or "").strip()
                })
        else:
            expanded.append({
                "usecase": usecase,
                "title": title or "TASK",
                "description": (desc or "").strip(),
                "testCase": tc
            })
    return expanded

# ---------- Main ----------

def main():
    with open("use_cases.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    bilesen = (data.get("bilesen_tasarimi") or "").strip()
    use_cases = data.get("use_cases", [])
    all_outputs = []

    if not bilesen:
        print("❌ Bileşen tasarımı açıklaması bulunamadı.")
        return

    if not use_cases:
        # Genel görevler
        prompt = prompt_for_general_tasks(bilesen)
        raw = query_ollama(prompt)
        print("\n— Model ham yanıt (genel) —\n", raw[:800], "...\n")
        try:
            arr = try_load_json_array(raw)
            batch = [{
                "usecase": "GENEL",
                "title": (o.get("title") or "").strip(),
                "description": (o.get("description") or "").strip(),
                "testCase": (o.get("testCase") or o.get("testcase") or "").strip()
            } for o in arr if isinstance(o, dict)]
        except Exception:
            batch = fallback_tasks_from_text(raw, "GENEL")

        batch = expand_embedded_lists(batch, "GENEL")
        batch = dedupe_and_normalize(batch)
        all_outputs.extend(batch)

    else:
        # Her UC için
        for i, uc in enumerate(use_cases, 1):
            uc_full, _, _ = parse_uc_title(uc.get("title") or "")
            uc_desc = (uc.get("description") or "").strip()

            print(f"\n▶️ UC {i} işleniyor: {uc_full}")
            prompt = prompt_for_tasks(bilesen, uc_full, uc_desc)
            raw = query_ollama(prompt)
            print("— Model ham yanıt —\n", raw[:800], "...\n")

            try:
                arr = try_load_json_array(raw)
                batch = [{
                    "usecase": uc_full,
                    "title": (o.get("title") or "").strip(),
                    "description": (o.get("description") or "").strip(),
                    "testCase": (o.get("testCase") or o.get("testcase") or "").strip()
                } for o in arr if isinstance(o, dict)]
            except Exception:
                batch = fallback_tasks_from_text(raw, uc_full)

            # 💥 kritik fix: description içine gömülü JSON array varsa genişlet
            batch = expand_embedded_lists(batch, uc_full)
            batch = dedupe_and_normalize(batch)
            all_outputs.extend(batch)

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_outputs, f, ensure_ascii=False, indent=2)
        print(f"\n✅ {len(all_outputs)} görev '{OUTPUT_FILE}' dosyasına yazıldı.")
    except Exception as e:
        print(f"❌ Yazma hatası: {e}")

if __name__ == "__main__":
    main()
