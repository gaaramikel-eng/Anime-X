#!/usr/bin/env python3
"""Atualiza o Anime X com dados da AniList (API pública e gratuita).
Para cada anime: soma os episódios já lançados e acha o próximo episódio e a data.
Reescreve o bloco AUTO dentro do index.html. Só usa a biblioteca padrão do Python.
Uso: python update_episodes.py [index.html]"""
import json, re, sys, time, datetime, urllib.request, urllib.error

HTML = sys.argv[1] if len(sys.argv) > 1 else "index.html"
API = "https://graphql.anilist.co"
FIELDS = "id title{romaji english} format episodes status nextAiringEpisode{episode airingAt}"
Q_ID = "query($id:Int){Media(id:$id,type:ANIME){%s}}" % FIELDS
Q_SEARCH = "query($s:String){Media(search:$s,type:ANIME,format_in:[TV,TV_SHORT,ONA]){%s}}" % FIELDS


def fetch(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, body, {"Content-Type": "application/json", "Accept": "application/json",
                                             "User-Agent": "AnimeX-updater/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["data"]["Media"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # nada encontrado
            if e.code in (429, 500, 502, 503):
                time.sleep(int(e.headers.get("Retry-After", 5 * (attempt + 1))))
                continue
            raise
        except urllib.error.URLError:
            time.sleep(5 * (attempt + 1))
    return None


def lookup(term):
    return fetch(Q_ID, {"id": term}) if isinstance(term, int) else fetch(Q_SEARCH, {"s": term})


def read_titles(html, overrides):
    sch = json.loads(re.search(r"var SCH=(\[.*?\]);\s*var UP", html, re.S).group(1))
    names = re.findall(r'\{id:\d+,t:"anime",n:"([^"]+)"', html)
    for day in sch:
        names += day
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return {n: overrides.get(n, [n]) for n in out}


def build(titles):
    auto = {}
    for name, terms in titles.items():
        cum, nxt = 0, None
        for term in terms:
            m = lookup(term)
            time.sleep(0.8)  # respeita o limite da AniList (90 req/min)
            if not m:
                print(f"  ! não achei: {term!r} (de {name!r})")
                continue
            n = m["nextAiringEpisode"]
            aired = (n["episode"] - 1) if n else (m["episodes"] or 0)
            if m["status"] == "NOT_YET_RELEASED":
                aired = 0
            if n and not nxt:
                nxt = {"ep": cum + n["episode"], "at": n["airingAt"]}
            title = m["title"]["english"] or m["title"]["romaji"]
            print(f"  {name} <- {title} [{m['status']}] {aired} ep")
            cum += aired
        if cum or nxt:
            auto[name] = {"total": cum, **({"next": nxt} if nxt else {})}
    return auto


def main():
    html = open(HTML, encoding="utf-8").read()
    try:
        overrides = json.load(open("titles.json", encoding="utf-8"))
    except FileNotFoundError:
        overrides = {}
    auto = build(read_titles(html, overrides))
    if not auto:
        sys.exit("Nenhum dado obtido; o arquivo não foi alterado.")
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    block = "/*AUTO:START*/var AUTO=%s;var AUTO_TS=%s;/*AUTO:END*/" % (
        json.dumps(auto, ensure_ascii=False, separators=(",", ":")), json.dumps(ts))
    new, k = re.subn(r"/\*AUTO:START\*/.*?/\*AUTO:END\*/", lambda _: block, html, flags=re.S)
    if k != 1:
        sys.exit("Marcadores AUTO:START/AUTO:END não encontrados no HTML.")
    open(HTML, "w", encoding="utf-8").write(new)
    print(f"OK: {len(auto)} títulos atualizados em {HTML}")


if __name__ == "__main__":
    main()
