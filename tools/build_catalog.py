#!/usr/bin/env python3
"""
The shop on this site, built from the live Etsy listings, for Pinterest's
product catalogue.

Pinterest takes a catalogue only from the website the account has claimed:
every product's link has to be on kirwana.github.io. So each Etsy listing
gets a page here (p/<listing id>.html: its photos, title, price and a Buy on
Etsy button), shop.html lists them all, and catalog.csv is the feed Pinterest
reads, in its own columns.

Run from this folder:  python3 tools/build_catalog.py
It reads Etsy through Print Kit's connection (~/Projects/etsy/print-templates),
rewrites p/, shop.html and catalog.csv, and leaves the rest of the site alone.
Then commit and push, and Pinterest picks the feed up on its next daily read.
"""
import csv
import html
import os
import re
import shutil
import sys

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://kirwana.github.io"
SHOP = "https://www.etsy.com/shop/MirrorsFineArt"
VERIFY = '<meta name="p:domain_verify" content="db7d2a24295a67bc265e4a4397112539"/>'
sys.path.insert(0, os.path.expanduser("~/Projects/etsy/print-templates"))
import etsy_api as E  # noqa: E402


def listings():
    sid = E.api("/users/me")["shop_id"]
    out, offset = [], 0
    while True:
        # the shop owner's own listing call: the public one stops at 100
        r = E.api("/shops/%s/listings?state=active&limit=100&offset=%d" % (sid, offset))
        out += r.get("results") or []
        offset += 100
        if offset >= (r.get("count") or 0):
            break
    # their photos, a hundred at a time
    imgs = {}
    ids = [str(l["listing_id"]) for l in out]
    for i in range(0, len(ids), 100):
        r = E.api("/listings/batch?listing_ids=%s&includes=Images" % ",".join(ids[i:i + 100]))
        for l in r.get("results") or []:
            imgs[l["listing_id"]] = sorted(l.get("images") or [], key=lambda m: m.get("rank", 99))
    for l in out:
        l["images"] = imgs.get(l["listing_id"], [])
    return out


def price(l):
    p = l["price"]
    return p["amount"] / p["divisor"], p["currency_code"]


def kind(l):
    t = l["title"].lower()
    if "card" in t:
        return "Printable greeting card"
    if re.search(r"\bset of \d|\bset\b", t):
        return "Printable wall art set"
    return "Printable wall art"


def plain(text):
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text or "")).strip()


def page(l):
    amt, cur = price(l)
    title = html.escape(html.unescape(l["title"]))
    desc = plain(l.get("description"))
    paras = "".join("<p>%s</p>" % html.escape(p).replace("\n", "<br>") for p in desc.split("\n\n")[:6])
    photos = [m["url_fullxfull"] for m in l["images"][:5] if m.get("url_fullxfull")]
    main = photos[0] if photos else ""
    thumbs = "".join('<img src="%s" alt="" loading="lazy">' % html.escape(u) for u in photos[1:])
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
%(verify)s
<title>%(title)s · Mirrors Fine Art</title>
<meta name="description" content="%(short)s">
<meta property="og:type" content="product">
<meta property="og:title" content="%(title)s">
<meta property="og:image" content="%(main)s">
<meta property="og:url" content="%(url)s">
<meta property="product:price:amount" content="%(amt).2f">
<meta property="product:price:currency" content="%(cur)s">
<meta property="og:availability" content="instock">
<link rel="stylesheet" href="../style.css">
</head>
<body>
<main class="wrap product">
  <p class="eyebrow"><a href="../index.html">Mirrors Fine Art</a> · <a href="../shop.html">Shop</a></p>
  <div class="product-grid">
    <div class="photos"><img class="main" src="%(main)s" alt="%(title)s">%(thumbs)s</div>
    <div class="info">
      <h1>%(title)s</h1>
      <p class="price">%(cur)s %(amt).2f</p>
      <p class="kind">%(kind)s · instant digital download</p>
      <p><a class="button" href="%(etsy)s">Buy on Etsy</a></p>
      <div class="desc">%(paras)s</div>
    </div>
  </div>
</main>
<footer class="wrap">
  <p>© Carolina &amp; Alan, Mirrors Fine Art. All photographs are our own.</p>
  <p><a href="../shop.html">Shop</a> · <a href="%(shop)s">Etsy shop</a> · <a href="../privacy.html">Privacy</a></p>
</footer>
</body>
</html>
""" % {"verify": VERIFY, "title": title, "short": html.escape(desc[:155]), "main": html.escape(main),
       "url": "%s/p/%s.html" % (BASE, l["listing_id"]), "amt": amt, "cur": cur, "thumbs": thumbs,
       "kind": kind(l), "etsy": html.escape(l["url"].split("?")[0]), "paras": paras, "shop": SHOP}


def shop_page(ls):
    cards = []
    for l in ls:
        amt, cur = price(l)
        img = l["images"][0]["url_570xN"] if l["images"] else ""
        cards.append('<a class="card" href="p/%s.html"><img src="%s" alt="" loading="lazy"><span>%s</span><b>%s %.2f</b></a>'
                     % (l["listing_id"], html.escape(img), html.escape(html.unescape(l["title"])), cur, amt))
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
%s
<title>Shop · Mirrors Fine Art</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="wrap">
  <p class="eyebrow"><a href="index.html">Mirrors Fine Art</a></p>
  <h1>Shop</h1>
  <p class="lede">Printable wall art and greeting cards, each an instant digital download. Every piece is sold through our Etsy shop.</p>
</header>
<main class="wrap shop">%s</main>
<footer class="wrap">
  <p>© Carolina &amp; Alan, Mirrors Fine Art. All photographs are our own.</p>
  <p><a href="%s">Etsy shop</a> · <a href="privacy.html">Privacy</a></p>
</footer>
</body>
</html>
""" % (VERIFY, "".join(cards), SHOP)


def feed(ls, path):
    """Pinterest's catalogue columns. Digital downloads: always in stock, new."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "title", "description", "link", "image_link", "additional_image_link",
                    "price", "availability", "condition", "brand", "product_type"])
        for l in ls:
            if not l["images"]:
                continue
            amt, cur = price(l)
            desc = re.sub(r"\s+", " ", plain(l.get("description")))[:9900]
            w.writerow([l["listing_id"], html.unescape(l["title"])[:500], desc,
                        "%s/p/%s.html" % (BASE, l["listing_id"]),
                        l["images"][0]["url_fullxfull"],
                        ",".join(m["url_fullxfull"] for m in l["images"][1:6]),
                        "%.2f %s" % (amt, cur), "in stock", "new", "Mirrors Fine Art", kind(l)])


def main():
    ls = listings()
    pdir = os.path.join(SITE, "p")
    shutil.rmtree(pdir, ignore_errors=True)
    os.makedirs(pdir)
    for l in ls:
        with open(os.path.join(pdir, "%s.html" % l["listing_id"]), "w", encoding="utf-8") as fh:
            fh.write(page(l))
    with open(os.path.join(SITE, "shop.html"), "w", encoding="utf-8") as fh:
        fh.write(shop_page(ls))
    feed(ls, os.path.join(SITE, "catalog.csv"))
    print("%d listings: %d pages, shop.html, catalog.csv (%d with photos)"
          % (len(ls), len(ls), sum(1 for l in ls if l["images"])))


if __name__ == "__main__":
    main()
