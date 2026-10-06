#!/usr/bin/env python3
"""
Invia su Telegram i nuovi avvisi del Corso di laurea in Economia (L-33)
dell'Università di Catania, presi dal sito del Dipartimento di Economia e Impresa.

Fonti (già filtrate per Economia dal sito stesso):
  - https://www.dei.unict.it/corsi/l-33/avvisi          (avvisi del corso)
  - https://www.dei.unict.it/corsi/l-33/avvisi-docente  (avvisi dei docenti)

Uso:
  python bot.py              controlla e invia le novità (richiede le variabili d'ambiente)
  python bot.py --dry-run    mostra cosa invierebbe, senza inviare nulla
  python bot.py --resend 2   invia i 2 avvisi più recenti anche se già visti (per testare)

Variabili d'ambiente:
  TELEGRAM_BOT_TOKEN   token del bot (da @BotFather)
  TELEGRAM_CHAT_ID     id del gruppo/canale di destinazione (es. -1001234567890 o @nomecanale)
  ADMIN_CHAT_ID        (facoltativo) chat a cui segnalare gli errori
"""
import argparse
import html as htmlmod
import json
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

BASE = "https://www.dei.unict.it"
SOURCES = [
    ("Avvisi del corso", f"{BASE}/corsi/l-33/avvisi"),
    ("Avvisi dei docenti", f"{BASE}/corsi/l-33/avvisi-docente"),
]
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")
MAX_IDS = 2000          # quante chiavi ricordare in seen.json
MAX_BODY = 3000         # caratteri massimi del testo dell'avviso nel messaggio
TG_LIMIT = 4096         # limite Telegram per messaggio
TIMEOUT = 30
HEADERS = {"User-Agent": "dei-economia-telegram/1.0 (bot avvisi studenti L-33)"}
BLOCK_TAGS = {"p", "div", "ul", "ol", "table", "tr", "blockquote",
              "h1", "h2", "h3", "h4", "h5", "h6"}
FILE_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|odt|zip)(\?|$)", re.I)


# ----------------------------------------------------------------------------
# Scaricamento e parsing
# ----------------------------------------------------------------------------

def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def parse_list(html: str, base: str = BASE) -> List[Dict[str, str]]:
    """Legge una pagina elenco (avvisi / avvisi-docente) e restituisce gli avvisi
    nell'ordine in cui compaiono.

    Le due pagine hanno schede (.card-body) leggermente diverse:
      - avvisi:          .category-top = "06/10/2026 <strong>- Lezioni</strong>", titolo in <h5>
      - avvisi-docente:  .category-top = "Lun, 05/10/2026", poi link al docente e link all'avviso
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select(".card-body"):
        link = None
        for a in card.select("a[href]"):
            path = urlparse(urljoin(base, a["href"].strip())).path
            if path.startswith("/comunicazioni/") or path.startswith("/content/"):
                link = a
                break
        if link is None:
            continue
        url = urljoin(base, link["href"].strip())
        title = link.get_text(" ", strip=True)
        date = category = ""
        top = card.find(class_="category-top")
        if top:
            m = re.search(r"\d{2}/\d{2}/\d{4}", top.get_text(" ", strip=True))
            date = m.group(0) if m else ""
            strong = top.find("strong")
            if strong:
                category = strong.get_text(" ", strip=True).lstrip("-").strip()
        if not category:
            prof = card.find("a", href=re.compile(r"/docenti/"))
            if prof:
                category = prof.get_text(" ", strip=True)
        items.append({"url": url, "title": title, "date": date, "category": category})
    return items


def body_to_text(el: Tag, base: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Converte il corpo HTML dell'avviso in testo semplice e raccoglie i link."""
    out: List[str] = []
    links: List[Tuple[str, str]] = []

    def walk(node):
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            out.append(str(node))
            return
        name = node.name
        if name in ("script", "style"):
            return
        if name == "br":
            out.append("\n")
            return
        if name == "li":
            out.append("\n• ")
        elif name in BLOCK_TAGS:
            out.append("\n")
        if name == "a" and node.get("href"):
            href = urljoin(base, node["href"].strip())
            if href.startswith("http"):
                links.append((node.get_text(" ", strip=True), href))
        for child in node.children:
            walk(child)
        if name in BLOCK_TAGS:
            out.append("\n")

    walk(el)
    text = "".join(out)
    text = re.sub(r"[ \t\r\f\v\xa0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"•[ \t]*\n+[ \t]*", "• ", text)        # <li><p>…</p></li>: testo sulla riga del punto
    text = re.sub(r"\n+(• )", r"\n\1", text).strip()   # elenchi puntati compatti

    seen = set()
    uniq = []
    for label, href in links:
        if href not in seen:
            seen.add(href)
            uniq.append((label, href))
    return text, uniq


def parse_article(html: str, url: str) -> Dict:
    """Legge la pagina di un singolo avviso."""
    soup = BeautifulSoup(html, "html.parser")

    node_id: Optional[str] = None
    short = soup.find("link", rel="shortlink")
    if short and short.get("href"):
        m = re.search(r"/node/(\d+)", short["href"])
        node_id = m.group(1) if m else None
    if not node_id:
        node = soup.find(id=re.compile(r"^node-\d+$"))
        if node:
            node_id = node["id"].split("-", 1)[1]

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""

    body = soup.select_one(".field-name-body .field-item")
    text, links = body_to_text(body, url) if body else ("", [])

    cat = soup.select_one(".field-name-field-tags .field-item")
    date = soup.select_one(".field-name-field-data-pubblicazione .field-item")

    return {
        "id": node_id,
        "url": url,
        "title": title,
        "text": text,
        "links": links,
        "category": cat.get_text(" ", strip=True) if cat else "",
        "date": date.get_text(" ", strip=True) if date else "",
    }


# ----------------------------------------------------------------------------
# Messaggio Telegram
# ----------------------------------------------------------------------------

def _link_label(label: str, href: str) -> str:
    """Per gli allegati usa il nome del file; per gli altri link il testo del link."""
    if "/sites/default/files/" in href or FILE_RE.search(href):
        return unquote(href.rsplit("/", 1)[-1].split("?")[0])
    label = (label or "").strip()
    if len(label) < 4 or label.lower() in {"qui", "link", "clicca qui", "questo link"}:
        return href
    return label


def format_message(item: Dict, source_name: str, max_body: int = MAX_BODY) -> str:
    def esc(s: str) -> str:
        return htmlmod.escape(s, quote=False)   # Telegram vuole solo < > & escapati
    meta = " · ".join(x for x in (item.get("date"), item.get("category"), source_name) if x)

    footer = [f'🔗 <a href="{htmlmod.escape(item["url"])}">Leggi sul sito</a>']
    for label, href in item.get("links", []):
        if href == item["url"] or href.startswith("mailto:"):
            continue
        icon = "📎" if ("/sites/default/files/" in href or FILE_RE.search(href)) else "↗️"
        footer.append(f'{icon} <a href="{htmlmod.escape(href)}">{esc(_link_label(label, href))}</a>')

    head = [f"📌 <b>{esc(item['title'])}</b>"]
    if meta:
        head.append(f"<i>{esc(meta)}</i>")

    def build(text: str) -> str:
        parts = list(head)
        if text:
            parts += ["", esc(text)]
        parts += [""] + footer
        return "\n".join(parts)

    text = item.get("text", "")
    if len(text) > max_body:
        text = text[:max_body].rsplit(" ", 1)[0] + " […]"
    msg = build(text)
    while len(msg) > TG_LIMIT and text:
        text = text[: max(0, len(text) - 300)].rsplit(" ", 1)[0] + " […]"
        msg = build(text)
    return msg


def tg(method: str, token: str, _retry: bool = True, **payload):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=TIMEOUT)
    data = r.json()
    if data.get("ok"):
        return data["result"]
    if r.status_code == 429 and _retry:
        wait = data.get("parameters", {}).get("retry_after", 5)
        time.sleep(wait + 1)
        return tg(method, token, _retry=False, **payload)
    raise RuntimeError(f"Telegram {method}: {data.get('description', r.text)}")


def send_message(token: str, chat_id: str, html_text: str) -> None:
    try:
        tg("sendMessage", token, chat_id=chat_id, text=html_text, parse_mode="HTML",
           link_preview_options={"is_disabled": True})
    except RuntimeError as e:
        if "can't parse entities" not in str(e):
            raise
        # Ripiego: stesso contenuto senza formattazione
        plain = re.sub(r"<[^>]+>", "", html_text)
        tg("sendMessage", token, chat_id=chat_id, text=htmlmod.unescape(plain),
           link_preview_options={"is_disabled": True})


# ----------------------------------------------------------------------------
# Stato
# ----------------------------------------------------------------------------

def load_state() -> List[str]:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return list(json.load(f).get("ids", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_state(ids: List[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ids": ids[-MAX_IDS:]}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def keys_for(path: str, node_id: Optional[str]) -> List[str]:
    keys = [f"path:{path}"]
    if node_id:
        keys.append(f"node:{node_id}")
    return keys


# ----------------------------------------------------------------------------
# Programma principale
# ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="non invia e non salva, stampa soltanto")
    ap.add_argument("--resend", type=int, metavar="N", default=0,
                    help="invia i N avvisi più recenti anche se già visti (non tocca lo stato)")
    args = ap.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    admin_id = os.environ.get("ADMIN_CHAT_ID", "")
    if not args.dry_run and (not token or not chat_id):
        print("Mancano TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID (usa --dry-run per provare senza).", file=sys.stderr)
        return 2

    ids = load_state()
    seen = set(ids)
    first_run = not seen and not args.resend
    errors: List[str] = []

    # 1. Elenchi: unisco le due fonti, dedup per percorso (senza query string)
    by_path: Dict[str, Tuple[str, Dict]] = {}
    for source_name, url in SOURCES:
        try:
            items = parse_list(fetch(url))
            if not items:
                raise RuntimeError("nessun avviso trovato: la pagina ha cambiato struttura?")
            for it in items:
                by_path.setdefault(urlparse(it["url"]).path, (source_name, it))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{source_name} ({url}): {e}")

    # 2. Scelgo cosa guardare: solo gli avvisi mai visti (o i più recenti con --resend)
    entries = list(by_path.values())
    if args.resend:
        entries = entries[: args.resend]
    else:
        entries = [(s, it) for s, it in entries if f"path:{urlparse(it['url']).path}" not in seen]

    # 3. Apro ogni avviso nuovo e preparo i messaggi
    to_send: List[Tuple[str, Dict]] = []
    for source_name, it in entries:
        path = urlparse(it["url"]).path
        try:
            art = parse_article(fetch(it["url"]), it["url"])
        except Exception as e:  # noqa: BLE001
            errors.append(f"{it['url']}: {e}")
            continue
        art["title"] = art["title"] or it["title"]
        art["date"] = art["date"] or it["date"]
        art["category"] = art["category"] or it["category"]
        art["keys"] = keys_for(path, art["id"])
        if not args.resend and art["id"] and f"node:{art['id']}" in seen:
            ids += art["keys"]          # stesso avviso visto da un altro percorso
            seen.update(art["keys"])
            continue
        to_send.append((source_name, art))

    # dal più vecchio al più recente (così in chat restano in ordine)
    to_send.sort(key=lambda x: int(x[1]["id"]) if (x[1]["id"] or "").isdigit() else 0)

    # 4. Invio
    if first_run:
        for _, art in to_send:
            ids += art["keys"]
        if not args.dry_run:
            save_state(ids)
        print(f"Prima esecuzione: {len(to_send)} avvisi esistenti segnati come già visti, nessun invio.")
    else:
        for source_name, art in to_send:
            msg = format_message(art, source_name)
            if args.dry_run:
                print("=" * 70)
                print(msg)
            else:
                send_message(token, chat_id, msg)
                print(f"Inviato: {art['title']}")
                if not args.resend:
                    ids += art["keys"]
                    save_state(ids)   # salvo subito: se crasha dopo, non reinvia
                time.sleep(1)         # rispetta il limite di Telegram sui canali
        if not to_send:
            print("Nessun avviso nuovo.")
        if not args.dry_run and not args.resend:
            save_state(ids)

    # 5. Errori: li stampo e, se configurato, li segnalo in chat privata
    if errors:
        print("ERRORI:\n  " + "\n  ".join(errors), file=sys.stderr)
        if admin_id and token and not args.dry_run:
            try:
                send_message(token, admin_id,
                             "⚠️ <b>Bot avvisi Economia</b>: problemi nell'ultimo controllo\n\n"
                             + htmlmod.escape("\n".join(errors)))
            except Exception as e:  # noqa: BLE001
                print(f"Impossibile avvisare l'admin: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
