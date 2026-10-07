#!/usr/bin/env python3
"""
The whole site, built from the live Etsy listings: the home page, the shop,
a page per listing, the privacy page, and catalog.csv for Pinterest.

Pinterest takes a catalogue only from the website the account has claimed:
every product's link has to be on kirwana.github.io. So each Etsy listing
gets a page here (p/<listing id>.html: its photos, title, price and a Buy on
Etsy button), and catalog.csv is the feed Pinterest reads.

Run from this folder:  python3 tools/build_catalog.py
It reads Etsy through Print Kit's connection (~/Projects/etsy/print-templates)
and rewrites index.html, shop.html, privacy.html, p/ and catalog.csv. The
images/ folder and style.css are kept as they are. tools/sync.sh runs it daily.
"""
import csv
import html
import json
import os
import re
import shutil
import sys

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://kirwana.github.io"
SHOP = "https://www.etsy.com/shop/MirrorsFineArt"
VERIFY = '<meta name="p:domain_verify" content="db7d2a24295a67bc265e4a4397112539"/>'
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1'
         '&family=Manrope:wght@400;500;600&display=swap">')
sys.path.insert(0, os.path.expanduser("~/Projects/etsy/print-templates"))
import etsy_api as E  # noqa: E402

KINDS = {"art": "Wall art", "set": "Wall art sets", "card": "Greeting cards"}


# ------------------------------------------------------------------ Etsy

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
    imgs = {}
    ids = [str(l["listing_id"]) for l in out]
    for i in range(0, len(ids), 100):
        r = E.api("/listings/batch?listing_ids=%s&includes=Images" % ",".join(ids[i:i + 100]))
        for l in r.get("results") or []:
            imgs[l["listing_id"]] = sorted(l.get("images") or [], key=lambda m: m.get("rank", 99))
    for l in out:
        l["images"] = imgs.get(l["listing_id"], [])
    return [l for l in out if l["images"]]


def price(l):
    p = l["price"]
    return p["amount"] / p["divisor"], p["currency_code"]


def money(l):
    amt, cur = price(l)
    return ("A$%.2f" % amt) if cur == "AUD" else "%s %.2f" % (cur, amt)


def kind(l):
    t = l["title"].lower()
    if re.search(r"\bcard\b", t):
        return "card"
    if re.search(r"\bset of \d|\bgall?e?ry set\b", t):
        return "set"
    return "art"


# Shop words in Etsy titles: what a search engine wants, not a name.
NOISE = re.compile(r"\b(printable|greeting|digital|downloads?|wall art|fine art print|art print|print|"
                   r"black and white|black & white|b&w|monochrome|card|galle?r?y set|instant)\b", re.I)


def names(l):
    """(name, set size or None, other words) from an Etsy title: 'Andean Silver -
    Andes - Peru - Set of 2' -> ('Andean Silver', 2, 'Andes · Peru')."""
    t = html.unescape(l["title"])
    t = re.sub(r"\(.*?\)", "", t).split(",")[0]
    m = re.search(r"\bset of (\d+)\b", t, re.I)
    n = int(m.group(1)) if m else None
    t = re.sub(r"\bset of \d+\b", " - ", t, flags=re.I)
    parts = [re.sub(r"\s{2,}", " ", NOISE.sub(" ", p)).strip(" -·") for p in re.split(r"\s+[-–—|]\s+|\s+-$", t)]
    parts = [p for p in parts if p]
    if not parts:
        return html.unescape(l["title"]), n, ""
    name = next((p for p in parts if len(p.split()) >= 2), parts[0])
    rest = [p for p in parts if p != name]
    return name, n, " · ".join(rest)


def product_title(l):
    name, n, _ = names(l)
    k = kind(l)
    if k == "card":
        return "%s, printable greeting card" % name
    if k == "set":
        return "%s, set of %d prints" % (name, n) if n else "%s, print set" % name
    return "%s, printable wall art" % name


def plain(text):
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text or "")).strip()


def desc_html(text):
    """Etsy's description as paragraphs, its ALL-CAPS lines as headings."""
    out = []
    for block in plain(text).split("\n\n"):
        lines = block.split("\n")
        if lines and re.fullmatch(r"[A-Z0-9 &'’/,.:-]{4,}", lines[0].strip()) and not re.search(r"[a-z]", lines[0]):
            out.append("<h3>%s</h3>" % html.escape(lines[0].strip().capitalize()))
            lines = lines[1:]
        if not lines:
            continue
        if all(re.match(r"\s*[-•*✓✔]", x) for x in lines if x.strip()):
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(re.sub(r"^\s*[-•*✓✔]\s*", "", x))
                                               for x in lines if x.strip()))
        else:
            out.append("<p>%s</p>" % "<br>".join(html.escape(x) for x in lines))
    return "".join(out)


# ------------------------------------------------------------------ layout

def head(title, desc, root, extra=""):
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
%s
<title>%s</title>
<meta name="description" content="%s">
%s
<link rel="stylesheet" href="%sstyle.css">
%s
</head>
<body>
<header class="site-head">
  <div class="bar">
    <a class="mark" href="%sindex.html">Mirrors <em>Fine Art</em></a>
    <nav>
      <a href="%sshop.html">Shop</a>
      <a href="%sshop.html#art">Wall art</a>
      <a href="%sshop.html#set">Sets</a>
      <a href="%sshop.html#card">Cards</a>
      <a href="%sindex.html#about">About</a>
      <a class="etsy" href="%s">Etsy</a>
    </nav>
  </div>
</header>
""" % (VERIFY, html.escape(title), html.escape(desc), FONTS, root, extra,
       root, root, root, root, root, root, SHOP)


def foot(root):
    return """<footer class="site-foot">
  <div class="cols">
    <div>
      <p class="mark">Mirrors <em>Fine Art</em></p>
      <p>Fine art photography by Carolina &amp; Alan, Sydney. Printable wall art and greeting cards, sold through Etsy as instant downloads.</p>
    </div>
    <div>
      <p class="label">Shop</p>
      <a href="%sshop.html#art">Wall art</a><a href="%sshop.html#set">Wall art sets</a><a href="%sshop.html#card">Greeting cards</a>
    </div>
    <div>
      <p class="label">About</p>
      <a href="%sindex.html#about">Our story</a><a href="%s">Etsy shop</a><a href="%sprivacy.html">Privacy</a>
    </div>
  </div>
  <p class="fine">© 2026 Carolina &amp; Alan · All photographs are our own · Orders are placed and paid securely on Etsy</p>
</footer>
</body>
</html>
""" % (root, root, root, root, SHOP, root)


def tile(l, root=""):
    name, n, rest = names(l)
    img = l["images"][0].get("url_570xN") or l["images"][0]["url_fullxfull"]
    sub = {"art": "Wall art", "card": "Greeting card"}.get(kind(l)) or ("Set of %d" % n if n else "Print set")
    return ('<a class="tile" data-kind="%s" href="%sp/%s.html"><span class="ph"><img src="%s" alt="%s" loading="lazy"></span>'
            '<span class="tn">%s</span><span class="tm">%s · %s</span></a>'
            % (kind(l), root, l["listing_id"], html.escape(img), html.escape(name), html.escape(name),
               html.escape(sub), money(l)))


# ------------------------------------------------------------------ pages

def sections(text):
    """The description as (story, [(heading, html)]): the photograph's own story
    shown, everything under an ALL-CAPS heading folded away, and the opening
    note about the photograph moved under 'About the photograph'."""
    story, folds, cur = [], [], None
    for block in plain(text).split("\n\n"):
        lines = [x for x in block.split("\n")]
        if lines and re.fullmatch(r"[A-Z0-9 &'’/,.:()-]{4,}", lines[0].strip()) and not re.search(r"[a-z]", lines[0]):
            cur = [lines[0].strip().capitalize(), []]
            folds.append(cur)
            lines = lines[1:]
        body = [x for x in lines if x.strip()]
        if not body:
            continue
        if all(re.match(r"\s*[-•*✓✔]", x) for x in body):
            h = "<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(re.sub(r"^\s*[-•*✓✔]\s*", "", x)) for x in body)
        else:
            h = "<p>%s</p>" % "<br>".join(html.escape(x) for x in body)
        if cur is not None:
            cur[1].append(h)
        elif not story and re.match(r"(An original photograph|Original photographs)", body[0]):
            folds.insert(0, ["About the photograph", [h]])
        else:
            story.append(h)
    return "".join(story), [(t, "".join(x)) for t, x in folds if x]


def product_page(l, related):
    name, n, rest = names(l)
    k = kind(l)
    photos = [m["url_fullxfull"] for m in l["images"][:10]]
    smalls = [m.get("url_570xN") or m["url_fullxfull"] for m in l["images"][:10]]
    thumbs = "".join('<button type="button" data-i="%d"%s aria-label="Photo %d"><img src="%s" alt="" loading="lazy"></button>'
                     % (i, ' class="on"' if i == 0 else "", i + 1, html.escape(sm)) for i, sm in enumerate(smalls))
    sub = {"art": "Printable wall art", "set": "Set of %d prints" % n if n else "Print set",
           "card": "Printable greeting card"}[k]
    notes = {"art": ["Instant download", "Print-ready at 300 DPI", "Secure checkout on Etsy"],
             "set": ["Instant download, %s files" % (n or "matched"), "Print-ready at 300 DPI", "Secure checkout on Etsy"],
             "card": ["Instant download", "Print at home or a print shop", "Secure checkout on Etsy"]}[k]
    story, folds = sections(l.get("description"))
    acc = "".join('<details%s><summary>%s</summary><div>%s</div></details>' % (" open" if i == 0 and t == "What you receive" else "",
                  html.escape(t), body) for i, (t, body) in enumerate(folds))
    rel = "".join(tile(x, "../") for x in related)
    amt, cur = price(l)
    ld = {"@context": "https://schema.org", "@type": "Product", "name": product_title(l),
          "image": photos[:4], "description": plain(l.get("description"))[:500], "brand": {"@type": "Brand", "name": "Mirrors Fine Art"},
          "offers": {"@type": "Offer", "price": "%.2f" % amt, "priceCurrency": cur, "availability": "https://schema.org/InStock",
                     "url": "%s/p/%s.html" % (BASE, l["listing_id"])}}
    extra = ('<meta property="og:type" content="product"><meta property="og:title" content="%s">'
             '<meta property="og:image" content="%s"><meta property="og:url" content="%s/p/%s.html">'
             '<meta property="product:price:amount" content="%.2f"><meta property="product:price:currency" content="%s">'
             '<meta property="og:availability" content="instock"><script type="application/ld+json">%s</script>'
             % (html.escape(product_title(l)), html.escape(photos[0]), BASE, l["listing_id"], amt, cur,
                json.dumps(ld).replace("</", "<\\/")))
    return head("%s · Mirrors Fine Art" % name, plain(l.get("description"))[:155], "../", extra) + """
<main class="product">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="../shop.html">Shop</a><span>/</span><a href="../shop.html#%(k)s">%(kname)s</a><span>/</span>%(name)s</nav>
  <div class="pgrid">
    <div class="viewer">
      <div class="stage">
        <button type="button" class="zoom" aria-label="View larger"><img id="main" src="%(main)s" alt="%(name)s"></button>
        <button type="button" class="nav prev" aria-label="Previous photo">‹</button>
        <button type="button" class="nav next" aria-label="Next photo">›</button>
        <span class="count"><b id="ci">1</b> / %(np)d</span>
      </div>
      <div class="strip">%(thumbs)s</div>
    </div>
    <div class="buy">
      <p class="eyebrow">%(sub)s</p>
      <h1>%(name)s</h1>
      %(where)s
      <p class="price">%(price)s</p>
      <a class="btn wide" href="%(etsy)s">Buy on Etsy</a>
      <ul class="notes">%(notes)s</ul>
      <div class="story">%(story)s</div>
      <div class="acc">%(acc)s</div>
    </div>
  </div>
  <section class="more">
    <div class="sec-head"><h2>More like this</h2><a href="../shop.html#%(k)s">See all %(kname_l)s</a></div>
    <div class="tiles">%(rel)s</div>
  </section>
</main>
<dialog id="lb" aria-label="Photo"><button type="button" class="lb-close" aria-label="Close">×</button><img id="lbimg" src="" alt="%(name)s"></dialog>
<script>
(function () {
  var photos = %(photos)s, i = 0, main = document.getElementById('main'), ci = document.getElementById('ci'),
      thumbs = document.querySelectorAll('.strip button'), lb = document.getElementById('lb'), lbimg = document.getElementById('lbimg');
  function show(n) {
    i = (n + photos.length) %% photos.length;
    main.src = photos[i]; ci.textContent = i + 1;
    thumbs.forEach(function (t, k) { t.classList.toggle('on', k === i); });
    if (thumbs[i]) thumbs[i].scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (lb.open) lbimg.src = photos[i];
  }
  thumbs.forEach(function (t) { t.addEventListener('click', function () { show(+t.dataset.i); }); });
  document.querySelector('.prev').addEventListener('click', function () { show(i - 1); });
  document.querySelector('.next').addEventListener('click', function () { show(i + 1); });
  document.querySelector('.zoom').addEventListener('click', function () { lbimg.src = photos[i]; lb.showModal(); });
  document.querySelector('.lb-close').addEventListener('click', function () { lb.close(); });
  lb.addEventListener('click', function (e) { if (e.target === lb) lb.close(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'ArrowLeft') show(i - 1); if (e.key === 'ArrowRight') show(i + 1); });
  if (photos.length < 2) document.querySelectorAll('.nav, .count, .strip').forEach(function (x) { x.hidden = true; });
})();
</script>
""" % {"k": k, "kname": KINDS[k], "kname_l": KINDS[k].lower(), "main": html.escape(photos[0]), "name": html.escape(name),
       "np": len(photos), "thumbs": thumbs, "sub": html.escape(sub),
       "where": ('<p class="where">%s</p>' % html.escape(rest)) if rest else "", "price": money(l),
       "etsy": html.escape(l["url"].split("?")[0]), "notes": "".join("<li>%s</li>" % html.escape(x) for x in notes),
       "story": story, "acc": acc, "rel": rel, "photos": json.dumps(photos)} + foot("../")


def shop_page(ls):
    counts = {k: sum(1 for l in ls if kind(l) == k) for k in KINDS}
    chips = '<button type="button" data-k="all" class="on">All <span>%d</span></button>' % len(ls) + "".join(
        '<button type="button" data-k="%s">%s <span>%d</span></button>' % (k, v, counts[k]) for k, v in KINDS.items())
    return head("Shop · Mirrors Fine Art", "Printable wall art, print sets and greeting cards by Mirrors Fine Art.", "") + """
<main class="shop">
  <div class="shop-head">
    <h1>Shop</h1>
    <p>Printable wall art, matched print sets and greeting cards. Every piece is an instant download, bought securely on Etsy.</p>
    <div class="chips" role="tablist">%s</div>
  </div>
  <div class="tiles" id="tiles">%s</div>
</main>
<script>
(function () {
  var chips = document.querySelectorAll('.chips button'), tiles = document.querySelectorAll('#tiles .tile');
  function show(k) {
    chips.forEach(function (c) { c.classList.toggle('on', c.dataset.k === k); });
    tiles.forEach(function (t) { t.hidden = !(k === 'all' || t.dataset.kind === k); });
  }
  chips.forEach(function (c) { c.addEventListener('click', function () { history.replaceState(null, '', c.dataset.k === 'all' ? 'shop.html' : '#' + c.dataset.k); show(c.dataset.k); }); });
  var h = location.hash.replace('#', ''); show(['art', 'set', 'card'].indexOf(h) > -1 ? h : 'all');
  window.addEventListener('hashchange', function () { var k = location.hash.replace('#', ''); show(['art', 'set', 'card'].indexOf(k) > -1 ? k : 'all'); });
})();
</script>
""" % (chips, "".join(tile(l) for l in ls)) + foot("")


def home_page(ls):
    def first(k):
        return next((l for l in ls if kind(l) == k), ls[0])
    ranges = "".join(
        '<a class="range" href="shop.html#%s"><span class="ph"><img src="%s" alt="" loading="lazy"></span><span class="rn">%s</span><span class="rc">%d pieces</span></a>'
        % (k, html.escape(first(k)["images"][0].get("url_570xN") or first(k)["images"][0]["url_fullxfull"]), v,
           sum(1 for l in ls if kind(l) == k)) for k, v in KINDS.items())
    newest = "".join(tile(l) for l in [l for l in ls if kind(l) != "card"][:8])
    return head("Mirrors Fine Art · fine art photography by Carolina & Alan",
                "Fine art photography by Carolina & Alan, Sydney: printable wall art, print sets and greeting cards.", "") + """
<main>
  <section class="hero">
    <img src="images/peru-mountains.jpg" alt="Black and white panorama of the Andes in Peru under clouds">
    <div class="hero-text">
      <p class="eyebrow">Fine art photography · Sydney</p>
      <h1>Quiet places,<br><em>printed for your walls.</em></h1>
      <a class="btn light" href="shop.html">Shop the collection</a>
    </div>
  </section>

  <section class="intro" id="about">
    <h2>About us</h2>
    <div>
      <p>We are Carolina &amp; Alan, photographers based in Sydney. We travel for the light: the high Andes of Peru and Bolivia, the salt flats of the altiplano, the coasts and forests closer to home. Every image in the shop is one we made ourselves.</p>
      <p>Our prints are instant downloads, prepared at 300 DPI in a full range of sizes, so you can print them at home or at a local print shop and frame them your way. Our greeting cards come ready to print and fold.</p>
    </div>
  </section>

  <section class="ranges">%s</section>

  <section class="newest">
    <div class="sec-head"><h2>New work</h2><a href="shop.html">View all</a></div>
    <div class="tiles">%s</div>
  </section>

  <section class="gallery">
    <figure><img src="images/machu-picchu.jpg" alt="Machu Picchu guardhouse in morning light" loading="lazy"><figcaption>Machu Picchu, Peru</figcaption></figure>
    <figure><img src="images/bolivia-volcano.jpg" alt="A volcano above the salt flat in Bolivia" loading="lazy"><figcaption>The altiplano, Bolivia</figcaption></figure>
    <figure><img src="images/milford-sound.jpg" alt="Milford Sound, New Zealand" loading="lazy"><figcaption>Milford Sound, New Zealand</figcaption></figure>
    <figure><img src="images/pier.jpg" alt="A pier reflected in still water" loading="lazy"><figcaption>Still water at the pier</figcaption></figure>
  </section>
</main>
""" % (ranges, newest) + foot("")


def privacy_page():
    return head("Privacy · Mirrors Fine Art", "Privacy at Mirrors Fine Art.", "") + """
<main class="prose">
  <h1>Privacy</h1>
  <p class="muted">Last updated 8 October 2026.</p>
  <h2>This website</h2>
  <p>This site shows our photographs and links to our Etsy shop. It has no forms, no accounts, no cookies and no analytics, and it collects no personal information.</p>
  <h2>Our Pinterest app</h2>
  <p>We use a small private app, for our own Pinterest account only, to post pins of our own Etsy listings: our photographs, with a title, a description and a link to the listing. The app reads our boards so each pin goes to the right one.</p>
  <ul>
    <li>It acts only on our own Pinterest account, with the access we grant it.</li>
    <li>It does not read, collect or store anyone else's information.</li>
    <li>Its access token is kept on our own computer and is never shared or sold.</li>
    <li>We can remove its access at any time in Pinterest's settings.</li>
  </ul>
  <h2>Buying from us</h2>
  <p>Purchases happen on Etsy, under <a href="https://www.etsy.com/legal/privacy/">Etsy's privacy policy</a>. We see only what Etsy shares with sellers to complete an order.</p>
  <h2>Contact</h2>
  <p>Message us through our <a href="%s">Etsy shop</a>.</p>
</main>
""" % SHOP + foot("")


def feed(ls, path):
    """Pinterest's catalogue columns. Digital downloads: always in stock, new."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "title", "description", "link", "image_link", "additional_image_link",
                    "price", "availability", "condition", "brand", "product_type"])
        for l in ls:
            amt, cur = price(l)
            desc = re.sub(r"\s+", " ", plain(l.get("description")))[:9900]
            w.writerow([l["listing_id"], product_title(l)[:500], desc,
                        "%s/p/%s.html" % (BASE, l["listing_id"]),
                        l["images"][0]["url_fullxfull"],
                        ",".join(m["url_fullxfull"] for m in l["images"][1:6]),
                        "%.2f %s" % (amt, cur), "in stock", "new", "Mirrors Fine Art", KINDS[kind(l)]])


def write(path, text):
    with open(os.path.join(SITE, path), "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    ls = listings()
    pdir = os.path.join(SITE, "p")
    shutil.rmtree(pdir, ignore_errors=True)
    os.makedirs(pdir)
    for l in ls:
        same = [x for x in ls if kind(x) == kind(l) and x is not l][:4]
        write(os.path.join("p", "%s.html" % l["listing_id"]), product_page(l, same))
    write("shop.html", shop_page(ls))
    write("index.html", home_page(ls))
    write("privacy.html", privacy_page())
    feed(ls, os.path.join(SITE, "catalog.csv"))
    print("%d listings: %d pages, index, shop, privacy, catalog.csv" % (len(ls), len(ls)))


if __name__ == "__main__":
    main()
