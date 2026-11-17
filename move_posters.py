import os, re, csv, requests

SITE = "https://vcdpostershow.com"
CK, CS = os.environ["WC_KEY"], os.environ["WC_SECRET"]
DRY = os.environ.get("DRY_RUN", "true") == "true"
END = {"Section C": os.environ["END_C"], "Section D": os.environ["END_D"]}

def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def api(method, path, **kw):
    return requests.request(method, f"{SITE}/wp-json/wc/v3/{path}", auth=(CK, CS), timeout=60, **kw)

def term_ids(names):
    r = api("GET", "products/categories?per_page=100"); r.raise_for_status()
    m = {t["name"].lower(): t["id"] for t in r.json()}
    return {n: m[n.lower()] for n in names}

cat_ids = term_ids(["All", "Section C", "Section D"])

# load every existing product
products, page = [], 1
while True:
    r = api("GET", f"products?per_page=100&page={page}&status=any"); r.raise_for_status()
    batch = r.json()
    if not batch: break
    products += batch; page += 1
print(len(products), "products on site")
by_sku = {p["sku"]: p for p in products if p["sku"]}

def title_of(name):
    return re.sub(r"^\S+\s*[–-]\s*", "", name)

# read the sheet: column 0 = moved to D, column 3 = moved to C
rows = list(csv.reader(open("moves.csv", encoding="utf-8")))[1:]
moves = []
for row in rows:
    row += [""] * 7
    d, c = row[0].strip(), row[3].strip()
    if d:
        parts = d.split("_")
        moves.append((parts[0], parts[1] if len(parts) > 1 else "", " ".join(parts[2:]), "Section D"))
    if c:
        m = re.match(r"^(C\d+)\s*[-–]\s*(.+)$", c)
        if m: moves.append((m.group(1), m.group(2).strip(), "", "Section C"))

for new, title, designer, section in moves:
    if new in by_sku:
        print(f"{new} | already exists, skipped"); continue
    cands = [p for p in products if norm(title_of(p["name"])) == norm(title)]
    if len(cands) > 1 and designer:
        narrowed = [p for p in cands if norm(designer)[:6] in norm(p["description"])]
        cands = narrowed or cands
    if not cands:
        print(f"{new} | {title} | NOT FOUND"); continue
    if len(cands) > 1:
        print(f"{new} | {title} | AMBIGUOUS: " + ", ".join(f'{p["sku"]}(id {p["id"]})' for p in cands)); continue
    p = cands[0]
    print(f'{p["sku"]} -> {new} | {title} | {section} | end {END[section]}')
    if DRY: continue
    u = api("PUT", f'products/{p["id"]}', json={
        "sku": new, "name": f"{new} – {title_of(p['name'])}",
        "categories": [{"id": cat_ids["All"]}, {"id": cat_ids[section]}],
        "meta_data": [{"key": "_auction_dates_to", "value": END[section]}]})
    print("  updated" if u.ok else f"  FAILED: {u.status_code} {u.text[:200]}")
