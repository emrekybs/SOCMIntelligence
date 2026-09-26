"""
Kelime aramasi modulu - SOCMIntelligence platformu (social-searcher tarzi).

Tool: tools/keyword_osint.py (Bluesky + Reddit + Mastodon herkese acik arama; anahtar gerekmez)
  Input: bir kelime veya kisa ifade (hedef hesap gerekmez)
Graph: arama dugumu + en aktif hesaplar, etiketler, topluluklar (subreddit).
"""
from __future__ import annotations

from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class KeywordAdapter(PlatformAdapter):
    platform = "keyword"
    script = "keyword_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos arama sorgusu")
        if len(t) > 200:
            raise ValueError("Arama sorgusu cok uzun")
        return ("keyword", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=120)
        raise_tool_error(result, "Arama")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return KeywordGraphConverter.convert(data)


class KeywordGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        q = d.get("query")
        if not q:
            return g.export()
        qid = g.node(f"kw_{slug(q)}", "content", f"“{q}”", {
            "Tür": "Arama", "Toplam gönderi": d.get("total"), **{k.title(): v for k, v in (d.get("by_platform") or {}).items()},
        })
        for a in (d.get("top_accounts") or [])[:25]:
            if a.get("author"):
                g.social(qid, a.get("platform") or "bluesky", a["author"],
                         etype="tagged", source="Kelimeyi kullanan", extra={"Gönderi": a.get("count")})
        for h in (d.get("hashtags") or [])[:20]:
            g.hashtag(qid, h.get("hashtag", ""), "Arama", weight=h.get("count"))
        # subreddit topluluklari
        subs = {}
        for p in d.get("posts") or []:
            if p.get("subreddit"):
                subs[p["subreddit"]] = subs.get(p["subreddit"], 0) + 1
        for sub, c in sorted(subs.items(), key=lambda x: -x[1])[:15]:
            sid = g.node(f"d_reddit_sub_{slug(sub)}", "community", f"r/{sub}", {"Platform": "Reddit", "Gönderi": c})
            g.edge(qid, sid, "appears_in", c)
        return g.export()


router = make_router("keyword", KeywordAdapter,
                     ["ransomware", "veri sızıntısı", "#osint"],
                     max_targets=3, input_types=["keyword"])
