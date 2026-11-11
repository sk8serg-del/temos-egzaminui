# Литовская озвучка для странички "Temos egzaminui" (index.html)
#
#   pip install edge-tts
#   python lt_audio.py          -> озвучить все темы
#   python lt_audio.py 1        -> только тему 1;   python lt_audio.py 1 3 -> темы 1 и 3
#
# Озвучиваются литовские фразы (Ona) и их русский перевод (Svetlana).
# Фразы берутся прямо из index.html (массив BUILTIN). Если рядом лежит edits.json
# (текст из кнопки «⇄ Перенести правки» на страничке) — озвучиваются и твои правки.
# Результат: audio/<хеш>.mp3 + audio/timings.json (текст фразы и время каждого слова).
# Уже озвученные фразы повторно не генерируются.
import asyncio, hashlib, json, os, re, sys
import edge_tts

VOICE = "lt-LT-OnaNeural"   # мужской голос: "lt-LT-LeonasNeural"
RU_VOICE = "ru-RU-SvetlanaNeural"  # русский перевод (DmitryNeural у Microsoft часто отвечает «No audio»)
RATE = "-10%"               # чуть медленнее обычного
HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")


def load_topics():
    """Темы из index.html: [{'lt':..., 's':[[lt, ru], ...]}, ...]"""
    html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    block = html[html.index("const BUILTIN = ["):html.index("/* ---------- storage")]
    topics = []
    for line in block.splitlines():
        m = re.match(r'\s*\{\s*lt:(".*?"),\s*ru:(".*?"),\s*s:\[', line)
        if m:
            topics.append({"lt": json.loads(m.group(1)), "s": []})
        elif line.lstrip().startswith('["') and topics:
            topics[-1]["s"].append(json.loads(line.strip().rstrip(",")))
    # правки со странички
    ep = os.path.join(HERE, "edits.json")
    if os.path.exists(ep):
        d = json.load(open(ep, encoding="utf-8"))
        for k, t in (d.get("edits") or {}).items():
            if int(k) < len(topics):
                topics[int(k)] = t
        topics += d.get("custom") or []
    return topics


def key_for(text):
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:12]


def communicate(text, voice):
    try:
        return edge_tts.Communicate(text, voice, rate=RATE, boundary="WordBoundary")
    except TypeError:  # старые версии edge-tts
        return edge_tts.Communicate(text, voice, rate=RATE)


async def synth(text, path, voice):
    audio, words = bytearray(), []
    async for ch in communicate(text, voice).stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append([round(ch["offset"] / 1e7, 3), ch["text"]])
    if not audio:
        raise RuntimeError("пустой ответ")
    open(path, "wb").write(audio)
    return words


async def main():
    only = {int(x) - 1 for x in sys.argv[1:]}
    topics = load_topics()
    os.makedirs(AUDIO, exist_ok=True)
    tpath = os.path.join(AUDIO, "timings.json")
    timings = json.load(open(tpath, encoding="utf-8")) if os.path.exists(tpath) else {}

    todo = []
    for ti, t in enumerate(topics):
        if only and ti not in only:
            continue
        for lt, ru in t["s"]:
            for text, voice, lang in ((lt, VOICE, "lt"), (ru, RU_VOICE, "ru")):
                if not (text or "").strip():
                    continue
                k = key_for(text)
                mp3 = os.path.join(AUDIO, k + ".mp3")
                old = timings.get(k)
                # запись есть и сделана тем же голосом (старые записи без поля voice — голос Ona)
                if old and old.get("voice", VOICE) == voice and os.path.exists(mp3) and os.path.getsize(mp3) > 0:
                    continue
                todo.append((k, text, voice, lang))
    todo = list(dict.fromkeys(todo))
    print(f"Нужно озвучить фраз: {len(todo)}")

    for n, (k, text, voice, lang) in enumerate(todo, 1):
        for attempt in range(6):  # сервис Microsoft иногда отвечает «No audio» — ждём всё дольше
            try:
                timings[k] = {"text": text.strip(), "lang": lang, "voice": voice, "w": await synth(text, os.path.join(AUDIO, k + ".mp3"), voice)}
                break
            except Exception as e:
                print("  повтор:", e)
                await asyncio.sleep(3 * 2 ** attempt)
        json.dump(timings, open(tpath, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"{n}/{len(todo)}  {text}")
    print("Готово.")


asyncio.run(main())
