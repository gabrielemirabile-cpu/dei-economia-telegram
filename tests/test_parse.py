import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def test_parse_list_avvisi_corso():
    items = bot.parse_list(read("avvisi.html"))
    assert len(items) == 10
    assert items[0]["title"] == "Corso di preparazione allo scritto di lingua inglese - Prof.ssa A. Cooper"
    assert items[0]["date"] == "06/10/2026"
    assert items[0]["category"] == "Lezioni"
    assert all(i["url"].startswith("https://www.dei.unict.it/comunicazioni/") for i in items)
    piani = next(i for i in items if i["title"].startswith("Piani di studio"))
    assert piani["date"] == "22/09/2026"
    assert piani["category"] == "Altro (didattica)"


def test_parse_list_avvisi_docente():
    items = bot.parse_list(read("avvisi-docente.html"))
    assert len(items) == 8
    assert all("/content/" in i["url"] for i in items)
    assert all(i["date"] for i in items)
    assert items[0]["title"] == "Ricevimento studenti - Prof.ssa Cuccia"
    assert items[0]["url"] == "https://www.dei.unict.it/content/ricevimento-studenti-profssa-cuccia?cdl=l-33"
    assert items[0]["date"] == "05/10/2026"
    assert items[0]["category"] == "Prof. Tiziana Maria Stella Cuccia"


def test_parse_list_ignores_unrelated_pages():
    html = "<div class='card-body'><div class='category-top'>01/01/2026</div><a href='/corsi/l-33'>x</a></div>"
    assert bot.parse_list(html) == []


def test_parse_article_with_pdf():
    url = "https://www.dei.unict.it/comunicazioni/seduta-di-laurea-straordinaria-aa-2627"
    art = bot.parse_article(read("avviso-con-pdf.html"), url)
    assert art["id"] == "48839"
    assert art["title"] == "Seduta di laurea straordinaria AA 26/27"
    assert "leggere l'avviso" in art["text"]
    assert art["links"] == [("qui", "https://www.dei.unict.it/sites/default/files/Avviso%20dicembre%20aa2627.pdf")]
    assert art["category"] == "Altro (didattica)"
    assert art["date"] == "Sabato, 3 Ottobre, 2026"


def test_parse_article_docente():
    url = "https://www.dei.unict.it/content/ricevimento-studenti-profssa-cuccia?cdl=l-33"
    art = bot.parse_article(read("avviso-docente.html"), url)
    assert art["id"] == "48861"
    assert "Tiziana Cuccia" in art["text"]
    assert "15 ottobre" in art["text"]
    assert all(not h.startswith("mailto:") for _, h in art["links"])


def test_format_message_pdf_uses_filename_and_fits_limit():
    url = "https://www.dei.unict.it/comunicazioni/seduta-di-laurea-straordinaria-aa-2627"
    art = bot.parse_article(read("avviso-con-pdf.html"), url)
    msg = bot.format_message(art, "Avvisi del corso")
    assert msg.startswith("📌 <b>Seduta di laurea straordinaria AA 26/27</b>")
    assert "Sabato, 3 Ottobre, 2026 · Altro (didattica) · Avvisi del corso" in msg
    assert '📎 <a href="https://www.dei.unict.it/sites/default/files/Avviso%20dicembre%20aa2627.pdf">Avviso dicembre aa2627.pdf</a>' in msg
    assert len(msg) <= bot.TG_LIMIT


def test_format_message_truncates_long_text():
    art = {"id": "1", "url": "https://www.dei.unict.it/content/x", "title": "T",
           "text": "parola " * 2000, "links": [], "category": "", "date": ""}
    msg = bot.format_message(art, "Avvisi del corso")
    assert len(msg) <= bot.TG_LIMIT
    assert "[…]" in msg


def test_format_message_escapes_html():
    art = {"id": "1", "url": "https://www.dei.unict.it/content/x", "title": "A & B <c>",
           "text": "1 < 2", "links": [], "category": "", "date": ""}
    msg = bot.format_message(art, "Avvisi del corso")
    assert "A &amp; B &lt;c&gt;" in msg and "1 &lt; 2" in msg


def test_body_lists_are_compact():
    html = "<div><p>Studenti:</p><ul><li><p>Economia</p></li><li><p>Economia aziendale</p></li></ul><p>Fine</p></div>"
    from bs4 import BeautifulSoup
    text, _ = bot.body_to_text(BeautifulSoup(html, "html.parser").div, bot.BASE)
    assert text == "Studenti:\n• Economia\n• Economia aziendale\n\nFine"
