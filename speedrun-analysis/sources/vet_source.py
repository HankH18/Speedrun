# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Two-gate licence vetting for candidate source documents (PubMed Central).

WHY THIS EXISTS
---------------
OpenStax was the obvious first choice for medical source text and it was
rejected for TWO INDEPENDENT reasons:

  (a) LICENCE. "Anatomy & Physiology 2e" and "Microbiology" are
      CC BY-NC-SA 4.0, not CC BY 4.0. The NC (NonCommercial) and SA
      (ShareAlike) terms both conflict with this repository's
      AGPL-3.0-or-later licence.

  (b) AI/LLM TERMS. The same pages carry an explicit prohibition on using
      the work to train large language models. That kills the use case
      regardless of what the licence says.

And the trap that made (a) easy to get wrong: openstax.org's SITE-WIDE
FOOTER still advertises CC BY 4.0 while the per-book licence is CC BY-NC-SA.
A footer, a catalogue entry, or a third-party OER index is NOT the licence.
Only the work's own licence statement is.

So the check has two gates, and both must pass:

  GATE A - LICENCE. The article must carry an explicit, MACHINE-READABLE
      Creative Commons licence field whose URI is CC BY 4.0 and nothing
      else. Prose alone does not count. CC BY-NC*, CC BY-*-ND, CC BY 3.0,
      CC0 and "no licence element at all" are all rejected.
      As a direct guard against the stale-footer trap, gate A also
      cross-checks every Creative Commons URI that appears on the article's
      own landing page against the machine-readable field, and FAILS on a
      conflict rather than trusting either one.

  GATE B - AI / TEXT-MINING TERMS. The landing page is fetched and scanned
      for any AI / LLM / generative-AI / text-and-data-mining prohibition.
      Any match that reads as a PROHIBITION fails the gate, and the matched
      text is reported VERBATIM.

The script EXITS NON-ZERO if either gate fails for any article.

HONEST LIMITATIONS - read these before trusting a PASS
------------------------------------------------------
1. Gate B is a keyword-plus-context heuristic over the rendered landing
   page. It cannot read a linked PDF of terms, a publisher's separate
   Terms of Service page, a click-through agreement, or a robots.txt /
   ai.txt directive. A PASS means "no prohibition was found on the page we
   fetched", NOT "no prohibition exists".
2. Gate B classifies weaker signals ("restricted", "reserved", "all rights")
   as REVIEW rather than failing on them, to stay usable on biomedical text
   where those words occur innocently. REVIEW items are printed verbatim and
   are a human's job.
3. Only the PMC landing page is fetched by default. Pass --publisher to also
   resolve the DOI and scan the publisher's own article page; if that fetch
   fails the result is recorded as UNKNOWN, never as a pass.
4. The PMC OA web service reports a coarse licence string ("CC BY") with no
   version. It is recorded for cross-checking but gate A is decided on the
   versioned URI in the JATS <license> element.

USAGE
-----
    python3 vet_source.py PMC8570039 PMC7095030
    python3 vet_source.py --json out.json PMC8570039
    python3 vet_source.py --save-text DIR PMC8570039   # writes vetted text
    python3 vet_source.py --self-test                  # offline, no network

Exit codes: 0 = every article passed both gates. 1 = at least one gate
failed. 2 = usage / network / parse error.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OA_SERVICE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
PMC_ARTICLE = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"

USER_AGENT = "speedrun-vet-source/1.0 (Anki speedrun source vetting; stdlib urllib)"

#: The ONLY licence gate A accepts, in normalised form.
GATE_A_ACCEPTED = "creativecommons.org/licenses/by/4.0"

#: Terms that put us in AI / text-mining territory. Presence alone is NOT a
#: failure - biomedical papers discuss machine learning constantly.
AI_TERMS = (
    "large language model",
    "large language models",
    "llm",
    "llms",
    "generative ai",
    "generative artificial intelligence",
    "artificial intelligence",
    "machine learning",
    "text and data mining",
    "text- and data-mining",
    "text mining",
    "text-mining",
    "data mining",
    "data-mining",
    "tdm",
    "ai training",
    "training data",
    "model training",
    "neural network",
    "web scraping",
    "scraping",
    "crawler",
    "automated extraction",
    "systematic downloading",
    "bulk download",
)

#: Phrases that turn a mention into a PROHIBITION. Regexes, case-insensitive.
#: These are deliberately permission-shaped, not merely negative, so that
#: "growth restriction" in an abstract does not fail an article.
PROHIBITION_PATTERNS = (
    r"may\s+not\s+be\s+(?:used|ingested|reproduced|copied|stored|reused)",
    r"must\s+not\s+be\s+(?:used|ingested|reproduced|copied|stored|reused)",
    r"shall\s+not\s+be\s+(?:used|ingested|reproduced|copied|stored|reused)",
    r"cannot\s+be\s+(?:used|ingested)\s+(?:in|for|to)\s+(?:the\s+)?train",
    r"not\s+be\s+used\s+in\s+the\s+training",
    r"not\s+be\s+ingested",
    r"training\s+of\s+large\s+language\s+models",
    r"ingested\s+into\s+large\s+language\s+models",
    r"(?:is|are)\s+(?:expressly\s+|strictly\s+)?prohibited",
    r"\bprohibit(?:s|ed)\s+(?:the\s+)?(?:use|ingestion|training|mining)",
    r"(?:is|are)\s+not\s+permitted",
    r"(?:is|are)\s+not\s+allowed",
    r"without\s+(?:the\s+)?(?:\w+[’']s\s+|prior\s+|express\s+|written\s+){0,3}"
    r"(?:permission|consent|authori[sz]ation|licen[cs]e)",
    r"no\s+licen[cs]e\s+(?:is|are)\s+granted",
    r"no\s+rights?\s+(?:is|are)\s+granted",
    r"expressly\s+reserv",
    r"reserv\w*\s+(?:the\s+)?rights?\s+to\s+(?:text|data|mine|mining)",
    r"opt(?:s|ed)?\s+out\s+of",
    r"\bforbidden\b",
    r"unauthori[sz]ed\s+(?:use|access|copying|mining)",
)

#: Weaker signals. Reported verbatim as REVIEW, never an automatic failure.
REVIEW_PATTERNS = (
    r"all\s+rights\s+reserved",
    r"\brestrict(?:s|ed|ion|ions)\b",
    r"\breserved\b",
    r"terms\s+(?:of|and)\s+(?:use|conditions)",
)

CONTEXT_WINDOW = 320  # chars either side of an AI term
SNIPPET_PAD = 40  # extra chars kept when reporting a verbatim match

CC_URI_RE = re.compile(
    r"https?://(?:www\.)?creativecommons\.org/"
    r"(licenses/[a-z\-]+/\d\.\d|publicdomain/(?:zero|mark)/\d\.\d)",
    re.I,
)

#: Creative Commons licences named in PROSE. PMC article pages state the
#: licence in words and carry no creativecommons.org URI at all, so a
#: URI-only cross-check would be inert - which is exactly how the OpenStax
#: footer trap slips through. These patterns catch the prose form.
#: NOTE the deliberately loose `Commer\w*` / `Deriv\w*` stems. OpenStax's own
#: site footer misspells the licence as "Attribution-NonCommerical-ShareAlike"
#: (sic). A strict "NonCommercial" spelling silently reads that string as plain
#: "Creative Commons Attribution" - i.e. it manufactures the exact CC BY
#: misreading this whole check exists to prevent. Stay tolerant here.
CC_NAME_RE = re.compile(
    r"(?:"
    r"Creative\s+Commons\s+(?:Attribution|Public\s+Domain|CC0|Zero)"
    r"(?:[\s‐-―-]*Non[\s-]?Commer\w*)?"
    r"(?:[\s‐-―-]*Share[\s-]?Alike)?"
    r"(?:[\s‐-―-]*No[\s-]?Deriv\w*)?"
    r"(?:\s+\d\.\d)?"
    r"|"
    r"\bCC[\s‐-―-]?BY(?:[\s‐-―-]?NC)?(?:[\s‐-―-]?SA)?"
    r"(?:[\s‐-―-]?ND)?(?:\s+\d\.\d)?"
    r"|"
    r"\bCC0(?:\s+\d\.\d)?"
    r")",
    re.I,
)


def cc_family_from_name(matched):
    """Map a prose CC licence name to a family token, e.g. 'by-nc-sa'."""
    s = re.sub(r"[‐-―]", "-", matched.lower())
    if re.search(r"\bcc0\b|public\s+domain|zero", s):
        return "cc0"
    if not re.search(r"attribution|\bcc[\s-]?by\b", s):
        return ""
    parts = ["by"]
    if re.search(r"non[\s-]?commer\w*|\bnc\b", s):
        parts.append("nc")
    if re.search(r"share[\s-]?alike|\bsa\b", s):
        parts.append("sa")
    if re.search(r"no[\s-]?deriv|\bnd\b", s):
        parts.append("nd")
    return "-".join(parts)


def cc_family_from_uri(normalised):
    m = re.match(r"creativecommons\.org/licenses/([a-z\-]+)/\d\.\d$", normalised or "")
    if m:
        return m.group(1)
    if "/publicdomain/" in (normalised or ""):
        return "cc0"
    return ""


def cc_names_on_page(text):
    """Every CC licence named in a page's visible text, deduped, verbatim."""
    out = {}
    for m in CC_NAME_RE.finditer(text):
        verbatim = re.sub(r"\s+", " ", m.group(0)).strip()
        family = cc_family_from_name(verbatim)
        if not family:
            continue
        out.setdefault(family, verbatim)
    return out

REQUEST_PAUSE_S = 0.4  # NCBI asks for <= 3 requests/second without an API key


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class FetchResult:
    def __init__(self, url, ok, status=None, text="", error=""):
        self.url = url
        self.ok = ok
        self.status = status
        self.text = text
        self.error = error

    def as_dict(self):
        return {
            "url": self.url,
            "fetched": self.ok,
            "http_status": self.status,
            "bytes": len(self.text),
            "error": self.error,
        }


def fetch(url, timeout=45, browser_ua=False):
    """GET a URL with stdlib only. Never raises; returns a FetchResult."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        if browser_ua
        else USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return FetchResult(
                resp.geturl(), True, resp.status, raw.decode("utf-8", "replace")
            )
    except urllib.error.HTTPError as exc:
        return FetchResult(url, False, exc.code, "", "HTTPError %s" % exc.code)
    except Exception as exc:  # noqa: BLE001 - network is allowed to fail any way it likes
        return FetchResult(url, False, None, "", "%s: %s" % (type(exc).__name__, exc))


# ---------------------------------------------------------------------------
# HTML -> visible text
# ---------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._depth += 1
        # rel="license" and href attributes carry licence URIs that never
        # appear as visible text; keep them so the footer trap is detectable.
        for name, value in attrs:
            if name in ("href", "content") and value and "creativecommons.org" in value:
                self.chunks.append(" %s " % value)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if not self._depth:
            self.chunks.append(data)


def visible_text(page_html):
    parser = _TextExtractor()
    try:
        parser.feed(page_html)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup must not abort a vet run
        pass
    text = html.unescape("".join(parser.chunks))
    return re.sub(r"[ \t\r\f\v]*\n[ \t\r\f\v]*", "\n", re.sub(r"[ \t]+", " ", text))


# ---------------------------------------------------------------------------
# Licence normalisation
# ---------------------------------------------------------------------------


def normalise_cc_uri(uri):
    """Reduce a Creative Commons URI to 'creativecommons.org/licenses/by/4.0'.

    Returns "" for anything that is not a creativecommons.org URI.
    """
    if not uri:
        return ""
    u = uri.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("?")[0].split("#")[0]
    u = re.sub(r"/(?:legalcode|deed)(?:\.[a-z\-]+)?/?$", "", u)
    u = u.rstrip("/")
    if not u.startswith("creativecommons.org/"):
        return ""
    return u


def describe_cc_uri(normalised):
    """Human label for a normalised CC URI, or '' if unrecognised."""
    m = re.match(r"creativecommons\.org/licenses/([a-z\-]+)/(\d\.\d)$", normalised)
    if m:
        return "CC %s %s" % (m.group(1).upper(), m.group(2))
    m = re.match(r"creativecommons\.org/publicdomain/(zero|mark)/(\d\.\d)$", normalised)
    if m:
        return "CC0 %s" % m.group(2) if m.group(1) == "zero" else "CC PDM %s" % m.group(2)
    return ""


# ---------------------------------------------------------------------------
# PMC access
# ---------------------------------------------------------------------------


def normalise_pmcid(raw):
    s = str(raw).strip().upper()
    if s.startswith("PMC"):
        s = s[3:]
    if not s.isdigit():
        raise ValueError("not a PMCID: %r" % raw)
    return "PMC" + s


def oa_service_record(pmcid):
    """Coarse licence + citation from the PMC OA web service."""
    url = "%s?id=%s" % (OA_SERVICE, pmcid)
    res = fetch(url)
    out = {
        "url": url,
        "fetched": res.ok,
        "http_status": res.status,
        "error": res.error,
        "license_verbatim": None,
        "citation_verbatim": None,
        "retracted": None,
        "in_oa_subset": False,
        "oa_package_href": None,
        "service_error": None,
    }
    if not res.ok:
        return out
    try:
        root = ET.fromstring(res.text)
    except ET.ParseError as exc:
        out["service_error"] = "unparseable XML: %s" % exc
        return out
    err = root.find("error")
    if err is not None:
        out["service_error"] = "%s: %s" % (err.get("code"), (err.text or "").strip())
        return out
    rec = root.find("./records/record")
    if rec is None:
        out["service_error"] = "no <record> returned"
        return out
    out["in_oa_subset"] = True
    out["license_verbatim"] = rec.get("license")
    out["citation_verbatim"] = rec.get("citation")
    out["retracted"] = rec.get("retracted")
    link = rec.find("link")
    if link is not None:
        out["oa_package_href"] = link.get("href")
    return out


def efetch_jats(pmcid):
    url = "%s/efetch.fcgi?db=pmc&id=%s&retmode=xml" % (EUTILS, pmcid[3:])
    res = fetch(url)
    return url, res


ALI_NS = "{http://www.niso.org/schemas/ali/1.0/}"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _itertext(node):
    return "".join(node.itertext()).strip()


def extract_licence(article_el):
    """Pull the machine-readable licence field out of a JATS <article>.

    Returns a dict; `uri` is the machine-readable licence URI or None.
    """
    out = {
        "found_license_element": False,
        "license_type_attr": None,
        "uri": None,
        "uri_source": None,
        "uri_normalised": None,
        "uri_label": None,
        "license_p_verbatim": None,
        "copyright_statement_verbatim": None,
        "copyright_year": None,
        "copyright_holder": None,
        "ali_free_to_read": False,
        "raw_permissions_xml": None,
    }
    perms = article_el.find(".//permissions")
    if perms is None:
        return out
    out["raw_permissions_xml"] = re.sub(
        r"\s+", " ", ET.tostring(perms, encoding="unicode")
    ).strip()
    for tag, key in (
        ("copyright-statement", "copyright_statement_verbatim"),
        ("copyright-year", "copyright_year"),
        ("copyright-holder", "copyright_holder"),
    ):
        el = perms.find(tag)
        if el is not None:
            out[key] = _itertext(el)
    if perms.find(ALI_NS + "free_to_read") is not None:
        out["ali_free_to_read"] = True
    lic = perms.find("license")
    if lic is None:
        return out
    out["found_license_element"] = True
    out["license_type_attr"] = lic.get("license-type")
    ref = lic.find(ALI_NS + "license_ref")
    if ref is not None and (ref.text or "").strip():
        out["uri"] = (ref.text or "").strip()
        out["uri_source"] = "ali:license_ref"
    elif lic.get(XLINK_HREF):
        out["uri"] = lic.get(XLINK_HREF).strip()
        out["uri_source"] = "license/@xlink:href"
    else:
        ext = lic.find(".//ext-link")
        if ext is not None and ext.get(XLINK_HREF):
            out["uri"] = ext.get(XLINK_HREF).strip()
            out["uri_source"] = "license//ext-link/@xlink:href"
    lp = lic.find("license-p")
    if lp is not None:
        out["license_p_verbatim"] = re.sub(r"\s+", " ", _itertext(lp))
    if out["uri"]:
        out["uri_normalised"] = normalise_cc_uri(out["uri"])
        out["uri_label"] = describe_cc_uri(out["uri_normalised"])
    return out


def extract_metadata(article_el):
    meta = {
        "title": None,
        "journal": None,
        "journal_abbrev": None,
        "publisher": None,
        "year": None,
        "volume": None,
        "issue": None,
        "elocation_or_pages": None,
        "doi": None,
        "pmid": None,
        "pmcid": None,
        "article_types": [],
        "authors": [],
    }
    front = article_el.find("front")
    if front is None:
        return meta
    jm = front.find("journal-meta")
    if jm is not None:
        for path, key in (
            ("journal-title-group/journal-title", "journal"),
            ("journal-title", "journal"),
            ("publisher/publisher-name", "publisher"),
        ):
            el = jm.find(path)
            if el is not None and not meta[key]:
                meta[key] = _itertext(el)
        for jid in jm.findall("journal-id"):
            if jid.get("journal-id-type") in ("nlm-ta", "iso-abbrev") and not meta["journal_abbrev"]:
                meta["journal_abbrev"] = _itertext(jid)
    am = front.find("article-meta")
    if am is None:
        return meta
    t = am.find("title-group/article-title")
    if t is not None:
        meta["title"] = re.sub(r"\s+", " ", _itertext(t))
    for aid in am.findall("article-id"):
        kind = aid.get("pub-id-type")
        if kind == "doi":
            meta["doi"] = _itertext(aid)
        elif kind == "pmid":
            meta["pmid"] = _itertext(aid)
        elif kind in ("pmc", "pmcid"):
            meta["pmcid"] = _itertext(aid)
    for cat in am.findall("article-categories//subject"):
        s = _itertext(cat)
        if s:
            meta["article_types"].append(s)
    for pd in am.findall("pub-date"):
        y = pd.find("year")
        if y is not None and not meta["year"]:
            meta["year"] = _itertext(y)
    for path, key in (
        ("volume", "volume"),
        ("issue", "issue"),
        ("elocation-id", "elocation_or_pages"),
    ):
        el = am.find(path)
        if el is not None:
            meta[key] = _itertext(el)
    if not meta["elocation_or_pages"]:
        fp = am.find("fpage")
        lp = am.find("lpage")
        if fp is not None:
            meta["elocation_or_pages"] = (
                "%s-%s" % (_itertext(fp), _itertext(lp)) if lp is not None else _itertext(fp)
            )
    for contrib in am.findall(".//contrib"):
        if contrib.get("contrib-type") not in (None, "author"):
            continue
        sur = contrib.find("name/surname")
        given = contrib.find("name/given-names")
        if sur is not None:
            name = _itertext(sur)
            if given is not None:
                name = "%s %s" % (name, _itertext(given))
            meta["authors"].append(name)
        else:
            coll = contrib.find("collab")
            if coll is not None:
                meta["authors"].append(_itertext(coll))
    return meta


def build_attribution(meta, pmcid, licence_label):
    authors = meta["authors"]
    if not authors:
        who = "[author list UNKNOWN - not present in the JATS record]"
    elif len(authors) <= 6:
        who = ", ".join(authors)
    else:
        who = ", ".join(authors[:6]) + ", et al."
    bits = [who + "."]
    bits.append("%s." % (meta["title"] or "[title UNKNOWN]"))
    journal = meta["journal"] or meta["journal_abbrev"] or "[journal UNKNOWN]"
    ref = journal
    if meta["year"]:
        ref += ". %s" % meta["year"]
    if meta["volume"]:
        ref += ";%s" % meta["volume"]
        if meta["issue"]:
            ref += "(%s)" % meta["issue"]
    if meta["elocation_or_pages"]:
        ref += ":%s" % meta["elocation_or_pages"]
    bits.append(ref + ".")
    if meta["doi"]:
        bits.append("doi:%s." % meta["doi"])
    bits.append("%s." % pmcid)
    bits.append("Licensed %s." % (licence_label or "UNKNOWN"))
    return " ".join(bits)


def extract_article_text(article_el):
    """Flatten title + abstract + body into plain text."""
    lines = []
    meta = extract_metadata(article_el)
    if meta["title"]:
        lines.append("# " + meta["title"])
        lines.append("")
    front = article_el.find("front")
    if front is not None:
        for abst in front.findall(".//abstract"):
            label = abst.get("abstract-type") or "Abstract"
            lines.append("## " + label.title())
            for para in abst.iter("p"):
                s = re.sub(r"\s+", " ", _itertext(para))
                if s:
                    lines.append(s)
                    lines.append("")
    body = article_el.find("body")
    if body is not None:
        _flatten_sec(body, lines, depth=2)
    out, blank = [], False
    for line in lines:
        if not line.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(line.rstrip())
    return "\n".join(out).strip() + "\n"


def _flatten_sec(node, lines, depth):
    for child in node:
        tag = child.tag
        if tag == "sec":
            title = child.find("title")
            if title is not None:
                lines.append("")
                lines.append("#" * min(depth, 6) + " " + re.sub(r"\s+", " ", _itertext(title)))
                lines.append("")
            _flatten_sec(child, lines, depth + 1)
        elif tag in ("p", "disp-quote"):
            s = re.sub(r"\s+", " ", _itertext(child))
            if s:
                lines.append(s)
                lines.append("")
        elif tag == "list":
            for item in child.findall("list-item"):
                s = re.sub(r"\s+", " ", _itertext(item))
                if s:
                    lines.append("- " + s)
            lines.append("")
        elif tag in ("fig", "table-wrap"):
            cap = child.find(".//caption")
            lab = child.find("label")
            parts = []
            if lab is not None:
                parts.append(_itertext(lab))
            if cap is not None:
                parts.append(re.sub(r"\s+", " ", _itertext(cap)))
            if parts:
                lines.append("[%s]" % " ".join(parts))
                lines.append("")
        elif tag == "title":
            continue
        elif tag in ("ref-list", "back", "ack", "fn-group", "glossary"):
            continue
        else:
            _flatten_sec(child, lines, depth)


# ---------------------------------------------------------------------------
# Gate B - AI / text-mining prohibition scanner
# ---------------------------------------------------------------------------


def _snippet(text, start, end):
    a = max(0, start - SNIPPET_PAD)
    b = min(len(text), end + SNIPPET_PAD)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def scan_ai_terms(text):
    """Find AI/TDM prohibitions in `text`.

    Returns (prohibitions, reviews, mentions). Each entry carries the matched
    text VERBATIM plus the sentence-ish window it came from.
    """
    low = text.lower()
    prohibitions, reviews, mentions = [], [], []
    seen_pro, seen_rev = set(), set()

    for term in AI_TERMS:
        start = 0
        while True:
            i = low.find(term, start)
            if i < 0:
                break
            start = i + len(term)
            # word-boundary check for short/ambiguous terms
            if term in ("llm", "llms", "tdm", "ai training", "scraping", "crawler"):
                before = low[i - 1] if i else " "
                after = low[start] if start < len(low) else " "
                if before.isalnum() or after.isalnum():
                    continue
            w0 = max(0, i - CONTEXT_WINDOW)
            w1 = min(len(text), start + CONTEXT_WINDOW)
            window = text[w0:w1]
            hit_pro = False
            for pat in PROHIBITION_PATTERNS:
                m = re.search(pat, window, re.I)
                if m:
                    verbatim = _snippet(window, m.start(), m.end())
                    key = (term, verbatim)
                    if key not in seen_pro:
                        seen_pro.add(key)
                        prohibitions.append(
                            {
                                "ai_term": text[i:start],
                                "trigger_pattern": pat,
                                "matched_text_verbatim": verbatim,
                                "context_verbatim": re.sub(r"\s+", " ", window).strip(),
                            }
                        )
                    hit_pro = True
            if hit_pro:
                continue
            hit_rev = False
            for pat in REVIEW_PATTERNS:
                m = re.search(pat, window, re.I)
                if m:
                    verbatim = _snippet(window, m.start(), m.end())
                    key = (term, verbatim)
                    if key not in seen_rev:
                        seen_rev.add(key)
                        reviews.append(
                            {
                                "ai_term": text[i:start],
                                "trigger_pattern": pat,
                                "matched_text_verbatim": verbatim,
                            }
                        )
                    hit_rev = True
            if not hit_rev:
                mentions.append(text[i:start])
    return prohibitions, reviews, sorted(set(m.lower() for m in mentions))


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def gate_a(licence, page_cc_uris, page_cc_names=None):
    """LICENCE gate. Only CC BY 4.0, only from a machine-readable field."""
    page_cc_names = page_cc_names or {}
    reasons = []
    if not licence["found_license_element"]:
        reasons.append(
            "no <license> element in the JATS record - there is NO machine-readable "
            "licence field to check"
        )
    elif not licence["uri"]:
        reasons.append(
            "the <license> element carries no machine-readable URI "
            "(no ali:license_ref and no xlink:href); prose alone is not enough"
        )
    else:
        norm = licence["uri_normalised"]
        if not norm:
            reasons.append(
                "licence URI %r is not a creativecommons.org URI" % licence["uri"]
            )
        elif norm != GATE_A_ACCEPTED:
            label = licence["uri_label"] or norm
            if "/publicdomain/" in norm:
                reasons.append(
                    "licence is %s (public-domain dedication, not CC BY 4.0); "
                    "rejected because a CC0 waiver alone leaves attribution and "
                    "third-party-rights status unclear for our purposes" % label
                )
            else:
                extra = ""
                if "-nc" in norm:
                    extra += " NonCommercial conflicts with AGPL-3.0-or-later."
                if norm.endswith("-sa/4.0") or "-sa/" in norm:
                    extra += " ShareAlike conflicts with AGPL-3.0-or-later."
                if "-nd/" in norm:
                    extra += " NoDerivatives forbids the transformation we need."
                reasons.append("licence is %s, not CC BY 4.0.%s" % (label, extra))

    # ---- stale-footer / conflict cross-check -------------------------------
    # The OpenStax trap: openstax.org's site-wide footer advertises CC BY 4.0
    # while the per-book licence is CC BY-NC-SA 4.0. Never trust one statement
    # in isolation - compare every licence the page states against the
    # machine-readable field, and FAIL on disagreement rather than pick one.
    own_norm = licence.get("uri_normalised") or ""
    own_family = cc_family_from_uri(own_norm)
    own_version = ""
    m = re.search(r"/(\d\.\d)$", own_norm)
    if m:
        own_version = m.group(1)
    conflicts, agreements = [], []
    accepted_on_page = False
    for uri in page_cc_uris:
        norm = normalise_cc_uri(uri)
        if not norm:
            continue
        if norm == GATE_A_ACCEPTED:
            accepted_on_page = True
        if not own_norm:
            continue
        if norm == own_norm:
            agreements.append("URI %s" % uri)
        else:
            conflicts.append("URI %s" % uri)
    for family, verbatim in sorted(page_cc_names.items()):
        if not own_family:
            continue
        page_version = ""
        vm = re.search(r"(\d\.\d)", verbatim)
        if vm:
            page_version = vm.group(1)
        same = family == own_family and (
            not page_version or not own_version or page_version == own_version
        )
        if same:
            agreements.append("prose %r" % verbatim)
        else:
            conflicts.append(
                "prose %r (reads as CC %s%s)"
                % (verbatim, family.upper(), " " + page_version if page_version else "")
            )
    if conflicts and own_family:
        reasons.append(
            "STALE-FOOTER / CONFLICT CHECK: the machine-readable field says CC %s "
            "but the landing page also states %s. A page can advertise one licence "
            "while the work carries another - that is exactly the OpenStax footer "
            "trap. Resolve by hand before using this article."
            % (own_family.upper(), "; ".join(sorted(set(conflicts))))
        )

    return {
        "gate": "a_licence",
        "result": "PASS" if not reasons else "FAIL",
        "requirement": "explicit machine-readable CC BY 4.0 (%s) and nothing else"
        % GATE_A_ACCEPTED,
        "licence_field_verbatim": licence["license_p_verbatim"],
        "licence_uri_verbatim": licence["uri"],
        "licence_uri_source": licence["uri_source"],
        "licence_uri_normalised": licence["uri_normalised"],
        "licence_label": licence["uri_label"],
        "license_type_attr": licence["license_type_attr"],
        "copyright_statement_verbatim": licence["copyright_statement_verbatim"],
        "raw_permissions_xml": licence["raw_permissions_xml"],
        "cc_uris_on_landing_page": sorted(set(page_cc_uris)),
        "cc_names_on_landing_page_verbatim": page_cc_names,
        "landing_page_agrees_with_field": sorted(set(agreements)),
        "landing_page_conflicts_with_field": sorted(set(conflicts)),
        "landing_page_confirms_cc_by_4": accepted_on_page,
        "reasons": reasons,
    }


def gate_b(pages):
    """AI / LLM / text-mining gate over one or more fetched pages."""
    per_page, reasons = [], []
    any_scanned = False
    for page in pages:
        entry = dict(page["fetch"])
        entry["role"] = page["role"]
        if not page["fetch"]["fetched"]:
            entry["scan"] = "UNKNOWN - page could not be fetched"
            if page["required"]:
                reasons.append(
                    "%s page could not be fetched (%s), so no AI/LLM terms check was "
                    "possible - recorded as UNKNOWN, not as a pass"
                    % (page["role"], page["fetch"]["error"] or page["fetch"]["status"])
                )
            per_page.append(entry)
            continue
        any_scanned = True
        pro, rev, mentions = scan_ai_terms(page["text"])
        entry["prohibitions"] = pro
        entry["review_items"] = rev
        entry["incidental_mentions"] = mentions
        entry["scan"] = "SCANNED"
        per_page.append(entry)
        for p in pro:
            reasons.append(
                "%s page: AI/text-mining PROHIBITION found near %r -> %r"
                % (page["role"], p["ai_term"], p["matched_text_verbatim"])
            )
    if not any_scanned:
        reasons.append("no page was successfully scanned")
    return {
        "gate": "b_ai_llm_terms",
        "result": "PASS" if not reasons else "FAIL",
        "requirement": (
            "no AI / LLM / generative-AI / text-and-data-mining prohibition on the "
            "article's landing page"
        ),
        "pages": per_page,
        "reasons": reasons,
        "caveat": (
            "PASS means no prohibition was found on the page(s) fetched. It does not "
            "prove none exists; linked PDFs, separate ToS pages and click-through "
            "agreements are not read by this tool."
        ),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def vet(pmcid, check_publisher=False, want_text=False):
    pmcid = normalise_pmcid(pmcid)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    report = {
        "pmcid": pmcid,
        "retrieval_date_utc": now_utc.isoformat(timespec="seconds"),
        "retrieval_date": now_utc.date().isoformat(),
        "source_url": PMC_ARTICLE.format(pmcid=pmcid),
        "tool": "speedrun-analysis/sources/vet_source.py",
    }

    report["oa_service"] = oa_service_record(pmcid)
    time.sleep(REQUEST_PAUSE_S)

    efetch_url, efetch_res = efetch_jats(pmcid)
    report["efetch"] = efetch_res.as_dict()
    report["efetch"]["url"] = efetch_url
    time.sleep(REQUEST_PAUSE_S)

    article_el = None
    if efetch_res.ok:
        try:
            root = ET.fromstring(efetch_res.text)
            article_el = root.find(".//article")
        except ET.ParseError as exc:
            report["efetch"]["error"] = "unparseable XML: %s" % exc

    if article_el is None:
        report["metadata"] = None
        report["gate_a"] = {
            "gate": "a_licence",
            "result": "FAIL",
            "reasons": [
                "could not retrieve/parse the JATS record, so there is no "
                "machine-readable licence field to check"
            ],
        }
        report["gate_b"] = {
            "gate": "b_ai_llm_terms",
            "result": "FAIL",
            "reasons": ["not evaluated: the article record could not be retrieved"],
        }
        report["overall"] = "FAIL"
        return report, None

    licence = extract_licence(article_el)
    meta = extract_metadata(article_el)
    report["metadata"] = meta

    pages = []
    landing = fetch(report["source_url"], browser_ua=True)
    landing_text = visible_text(landing.text) if landing.ok else ""
    pages.append(
        {
            "role": "pmc_landing",
            "required": True,
            "fetch": landing.as_dict(),
            "text": landing_text,
        }
    )
    page_cc_uris = CC_URI_RE.findall(landing.text) if landing.ok else []
    page_cc_uris = [m if m.startswith("http") else "https://creativecommons.org/" + m for m in page_cc_uris]
    page_cc_names = cc_names_on_page(landing_text) if landing.ok else {}

    if check_publisher and meta.get("doi"):
        time.sleep(REQUEST_PAUSE_S)
        pub_url = "https://doi.org/%s" % meta["doi"]
        pub = fetch(pub_url, browser_ua=True)
        pages.append(
            {
                "role": "publisher_landing",
                "required": False,
                "fetch": pub.as_dict(),
                "text": visible_text(pub.text) if pub.ok else "",
            }
        )
        if pub.ok:
            page_cc_uris += [
                m if m.startswith("http") else "https://creativecommons.org/" + m
                for m in CC_URI_RE.findall(pub.text)
            ]
            for family, verbatim in cc_names_on_page(pages[-1]["text"]).items():
                page_cc_names.setdefault(family, verbatim)

    report["gate_a"] = gate_a(licence, page_cc_uris, page_cc_names)
    report["gate_b"] = gate_b(pages)
    report["publisher_page_checked"] = bool(check_publisher and meta.get("doi"))
    report["overall"] = (
        "PASS"
        if report["gate_a"]["result"] == "PASS" and report["gate_b"]["result"] == "PASS"
        else "FAIL"
    )
    report["attribution"] = build_attribution(
        meta, pmcid, report["gate_a"].get("licence_label")
    )

    text = extract_article_text(article_el) if want_text else None
    return report, text


TEXT_HEADER = """\
================================================================================
SOURCE PROVENANCE - do not separate this header from the text below
================================================================================
PMCID              : {pmcid}
Source URL         : {url}
Retrieved (UTC)    : {retrieved}
Retrieval method   : NCBI E-utilities EFetch, db=pmc (JATS XML), flattened to text
                     by speedrun-analysis/sources/vet_source.py

LICENCE FIELD, VERBATIM (from the JATS <license> element of the article record):
  machine-readable URI ({uri_source}):
    {uri}
  license-type attribute: {ltype}
  license-p text, verbatim:
    "{licence_p}"
  copyright statement, verbatim:
    "{copyright}"

PMC OA web service licence string, verbatim: {oa_licence}
  (coarse and unversioned; the versioned URI above is authoritative)

ATTRIBUTION (required by CC BY 4.0):
  {attribution}

TWO-GATE VETTING RESULT
  Gate A - licence is exactly CC BY 4.0 .............. {gate_a}
  Gate B - no AI/LLM/text-mining prohibition found ... {gate_b}
  Both gates were run by vet_source.py on {retrieved_date}.
  Gate B caveat: a PASS means no prohibition was found on the landing page that
  was fetched. It is not proof that none exists elsewhere.

MODIFICATIONS: the text below is the article body flattened from JATS XML to
plain text. References, author affiliations, funding statements and figure
images were dropped; figure/table captions were kept in [brackets]. No wording
was altered. CC BY 4.0 requires that changes be indicated - this paragraph is
that indication.
================================================================================

"""


def write_article_files(report, text, outdir):
    os.makedirs(outdir, exist_ok=True)
    pmcid = report["pmcid"]
    ga = report["gate_a"]
    header = TEXT_HEADER.format(
        pmcid=pmcid,
        url=report["source_url"],
        retrieved=report["retrieval_date_utc"],
        retrieved_date=report["retrieval_date"],
        uri_source=ga.get("licence_uri_source") or "UNKNOWN",
        uri=ga.get("licence_uri_verbatim") or "UNKNOWN",
        ltype=ga.get("license_type_attr") or "(absent)",
        licence_p=ga.get("licence_field_verbatim") or "UNKNOWN",
        copyright=ga.get("copyright_statement_verbatim") or "UNKNOWN",
        oa_licence=report["oa_service"].get("license_verbatim") or "UNKNOWN",
        attribution=report.get("attribution") or "UNKNOWN",
        gate_a=ga["result"],
        gate_b=report["gate_b"]["result"],
    )
    body = header + text
    txt_path = os.path.join(outdir, "%s.txt" % pmcid)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    report["text_file"] = os.path.basename(txt_path)
    report["text_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    report["text_chars"] = len(text)
    json_path = os.path.join(outdir, "%s.provenance.json" % pmcid)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return txt_path, json_path


def print_report(report):
    ga, gb = report["gate_a"], report["gate_b"]
    print("=" * 78)
    print("%s  ->  %s" % (report["pmcid"], report["overall"]))
    print("=" * 78)
    meta = report.get("metadata") or {}
    if meta.get("title"):
        print("  title    : %s" % meta["title"])
        print("  journal  : %s (%s)" % (meta.get("journal"), meta.get("year")))
        print("  types    : %s" % ", ".join(meta.get("article_types") or []) or "UNKNOWN")
        print("  doi      : %s" % (meta.get("doi") or "UNKNOWN"))
    print("  retrieved: %s" % report["retrieval_date_utc"])
    print("  url      : %s" % report["source_url"])
    print()
    print("  GATE A (licence) : %s" % ga["result"])
    print("    licence URI verbatim : %s" % (ga.get("licence_uri_verbatim") or "NONE"))
    print("    licence URI source   : %s" % (ga.get("licence_uri_source") or "NONE"))
    print("    licence label        : %s" % (ga.get("licence_label") or "UNKNOWN"))
    print("    OA service string    : %s" % (report["oa_service"].get("license_verbatim") or "UNKNOWN"))
    lp = ga.get("licence_field_verbatim")
    if lp:
        print("    license-p verbatim   : %s" % lp)
    print("    CC URIs on page      : %s" % (", ".join(ga.get("cc_uris_on_landing_page") or []) or "none"))
    named = ga.get("cc_names_on_landing_page_verbatim") or {}
    print(
        "    CC named on page     : %s"
        % (", ".join("%s -> %r" % (k.upper(), v) for k, v in sorted(named.items())) or "none")
    )
    print("    page agrees / conflicts: %d / %d" % (
        len(ga.get("landing_page_agrees_with_field") or []),
        len(ga.get("landing_page_conflicts_with_field") or []),
    ))
    for r in ga.get("reasons") or []:
        print("    ! %s" % r)
    print()
    print("  GATE B (AI/LLM terms) : %s" % gb["result"])
    for page in gb.get("pages") or []:
        print("    page %s: %s (%s)" % (page.get("role"), page.get("scan"), page.get("http_status")))
        for p in page.get("prohibitions") or []:
            print("      PROHIBITION near %r:" % p["ai_term"])
            print("        VERBATIM: %s" % p["matched_text_verbatim"])
        for r in page.get("review_items") or []:
            print("      REVIEW near %r: %s" % (r["ai_term"], r["matched_text_verbatim"]))
        mentions = page.get("incidental_mentions") or []
        if mentions:
            print("      incidental AI-word mentions (no restrictive context): %s" % ", ".join(mentions))
    for r in gb.get("reasons") or []:
        print("    ! %s" % r)
    print()


# ---------------------------------------------------------------------------
# Self-test (offline)
# ---------------------------------------------------------------------------

_JATS = """<article xmlns:xlink="http://www.w3.org/1999/xlink"><front>
<journal-meta><journal-title-group><journal-title>Test J</journal-title></journal-title-group></journal-meta>
<article-meta><title-group><article-title>T</article-title></title-group>
<contrib-group><contrib contrib-type="author"><name><surname>Doe</surname><given-names>J</given-names></name></contrib></contrib-group>
<pub-date><year>2024</year></pub-date>
<permissions>{perm}</permissions></article-meta></front><body><sec><title>S</title><p>Hello.</p></sec></body></article>"""

_PERM_CCBY4 = (
    '<copyright-statement>(c) 2024 Doe.</copyright-statement>'
    '<license license-type="open-access">'
    '<ali:license_ref xmlns:ali="http://www.niso.org/schemas/ali/1.0/">'
    "https://creativecommons.org/licenses/by/4.0/</ali:license_ref>"
    "<license-p>Open access under CC BY.</license-p></license>"
)
_PERM_CCBY4_XLINK = (
    '<license license-type="open-access" xlink:href="http://creativecommons.org/licenses/by/4.0/">'
    "<license-p>CC BY 4.0.</license-p></license>"
)
_PERM_NCSA = (
    '<license license-type="open-access" xlink:href="https://creativecommons.org/licenses/by-nc-sa/4.0/">'
    "<license-p>CC BY-NC-SA.</license-p></license>"
)
_PERM_NC = (
    '<license xlink:href="https://creativecommons.org/licenses/by-nc/4.0/"><license-p>nc</license-p></license>'
)
_PERM_ND = (
    '<license xlink:href="https://creativecommons.org/licenses/by-nc-nd/4.0/"><license-p>ncnd</license-p></license>'
)
_PERM_BY3 = (
    '<license xlink:href="https://creativecommons.org/licenses/by/3.0/"><license-p>by3</license-p></license>'
)
_PERM_CC0 = (
    '<license xlink:href="https://creativecommons.org/publicdomain/zero/1.0/"><license-p>cc0</license-p></license>'
)
_PERM_PROSE_ONLY = (
    '<license license-type="open-access"><license-p>This article is distributed under the '
    "terms of the Creative Commons Attribution 4.0 International License.</license-p></license>"
)
_PERM_NONE = "<copyright-statement>(c) 2024 Someone. All rights reserved.</copyright-statement>"

OPENSTAX_AI_CLAUSE = (
    "This book may not be used in the training of large language models or "
    "otherwise be ingested into large language models or generative AI "
    "offerings without OpenStax's permission."
)

_PAGE_CLEAN = (
    "<html><body><p>Community-acquired pneumonia is common.</p>"
    '<a rel="license" href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'
    "</body></html>"
)
_PAGE_AI_BAN = "<html><body><footer><p>%s</p></footer></body></html>" % OPENSTAX_AI_CLAUSE
_PAGE_ML_ABSTRACT = (
    "<html><body><p>We applied machine learning to chest radiographs. Fetal growth "
    "restriction was an exclusion criterion. Artificial intelligence models were "
    "trained on 1200 images.</p></body></html>"
)
_PAGE_STALE_FOOTER = (
    "<html><body><p>Licensed under CC BY-NC-SA 4.0: "
    '<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">here</a></p>'
    '<footer><a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a></footer>'
    "</body></html>"
)
_PAGE_TDM_OPTOUT = (
    "<html><body><p>The publisher expressly reserves the right to text and data "
    "mining of this content.</p></body></html>"
)


def _parse_perm(perm):
    return ET.fromstring(_JATS.format(perm=perm))


def _page(role, page_html, required=True):
    return {
        "role": role,
        "required": required,
        "fetch": {"url": "test://" + role, "fetched": True, "http_status": 200, "bytes": len(page_html), "error": ""},
        "text": visible_text(page_html),
    }


def self_test():
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append("%s: expected %r, got %r" % (name, want, got))
            print("  FAIL  %s (expected %r, got %r)" % (name, want, got))
        else:
            print("  ok    %s" % name)

    print("normalise_cc_uri")
    check("https + slash", normalise_cc_uri("https://creativecommons.org/licenses/by/4.0/"), GATE_A_ACCEPTED)
    check("http, no slash", normalise_cc_uri("http://creativecommons.org/licenses/by/4.0"), GATE_A_ACCEPTED)
    check("legalcode suffix", normalise_cc_uri("https://creativecommons.org/licenses/by/4.0/legalcode"), GATE_A_ACCEPTED)
    check("deed suffix", normalise_cc_uri("https://creativecommons.org/licenses/by/4.0/deed.en"), GATE_A_ACCEPTED)
    check("www prefix", normalise_cc_uri("https://www.creativecommons.org/licenses/by/4.0/"), GATE_A_ACCEPTED)
    check("non-cc uri", normalise_cc_uri("https://example.com/licence"), "")
    check("label nc-sa", describe_cc_uri("creativecommons.org/licenses/by-nc-sa/4.0"), "CC BY-NC-SA 4.0")

    print("gate A")
    cases = [
        ("CC BY 4.0 via ali:license_ref", _PERM_CCBY4, "PASS"),
        ("CC BY 4.0 via xlink:href", _PERM_CCBY4_XLINK, "PASS"),
        ("CC BY-NC-SA 4.0 (the OpenStax licence)", _PERM_NCSA, "FAIL"),
        ("CC BY-NC 4.0", _PERM_NC, "FAIL"),
        ("CC BY-NC-ND 4.0", _PERM_ND, "FAIL"),
        ("CC BY 3.0 (wrong version)", _PERM_BY3, "FAIL"),
        ("CC0 1.0", _PERM_CC0, "FAIL"),
        ("prose only, no machine-readable URI", _PERM_PROSE_ONLY, "FAIL"),
        ("no <license> element at all", _PERM_NONE, "FAIL"),
    ]
    for name, perm, want in cases:
        lic = extract_licence(_parse_perm(perm))
        check(name, gate_a(lic, [])["result"], want)

    lic = extract_licence(_parse_perm(_PERM_CCBY4))
    res = gate_a(lic, ["https://creativecommons.org/licenses/by-nc-sa/4.0/"])
    check("stale-footer conflict (URI) fails gate A", res["result"], "FAIL")
    check(
        "conflict reason names the trap",
        any("STALE-FOOTER" in r for r in res["reasons"]),
        True,
    )
    res = gate_a(lic, ["https://creativecommons.org/licenses/by/4.0/"])
    check("agreeing page does not fail gate A", res["result"], "PASS")

    print("stale-footer detection in PROSE (PMC pages carry no CC URI at all)")
    check("prose family: plain attribution", cc_family_from_name("Creative Commons Attribution License"), "by")
    check(
        "prose family: NC-SA spelled out",
        cc_family_from_name("Creative Commons Attribution-NonCommercial-ShareAlike 4.0"),
        "by-nc-sa",
    )
    check("prose family: CC BY-NC-ND abbreviation", cc_family_from_name("CC BY-NC-ND"), "by-nc-nd")
    check("prose family: CC0", cc_family_from_name("CC0 1.0"), "cc0")
    # Regression: openstax.org's live site footer misspells "NonCommercial" as
    # "NonCommerical". A strict spelling read that string as plain CC BY -
    # fabricating the very misreading this check exists to catch.
    misspelt = "Creative Commons Attribution-NonCommerical-ShareAlike 4.0 International License"
    check(
        "OpenStax footer misspelling 'NonCommerical' is still read as NC-SA",
        cc_family_from_name(CC_NAME_RE.search(misspelt).group(0)),
        "by-nc-sa",
    )
    openstax_page = visible_text(
        "<html><body><p>This work is licensed under a Creative Commons "
        "Attribution-NonCommercial-ShareAlike 4.0 International License.</p>"
        "<footer><p>&copy; 1999-2026, Rice University. Except where otherwise noted, "
        "textbooks on this site are licensed under a Creative Commons Attribution 4.0 "
        "International License.</p></footer></body></html>"
    )
    named = cc_names_on_page(openstax_page)
    check("both licences detected on an OpenStax-shaped page", sorted(named), ["by", "by-nc-sa"])
    res = gate_a(lic, [], named)
    check("prose conflict fails gate A", res["result"], "FAIL")
    res = gate_a(lic, [], {"by": "Creative Commons Attribution License (CC BY)"})
    check("agreeing prose does not fail gate A", res["result"], "PASS")
    res = gate_a(lic, [], {"by": "Creative Commons Attribution 3.0"})
    check("same family, wrong version on page IS a conflict", res["result"], "FAIL")
    nc = extract_licence(_parse_perm(_PERM_NC))
    res = gate_a(nc, ["https://creativecommons.org/licenses/by-nc/4.0/"], {"by-nc": "CC BY-NC 4.0"})
    check(
        "a page that agrees with a non-CC-BY field raises no conflict "
        "(it still fails on the licence itself)",
        [r for r in res["reasons"] if "STALE-FOOTER" in r],
        [],
    )

    print("gate B")
    res = gate_b([_page("clean", _PAGE_CLEAN)])
    check("clean page passes", res["result"], "PASS")

    res = gate_b([_page("openstax", _PAGE_AI_BAN)])
    check("OpenStax AI clause fails", res["result"], "FAIL")
    pro = res["pages"][0]["prohibitions"]
    check("prohibition reported", bool(pro), True)
    check(
        "verbatim match contains the clause wording",
        any("training of large language models" in p["matched_text_verbatim"].lower() for p in pro),
        True,
    )

    res = gate_b([_page("ml_abstract", _PAGE_ML_ABSTRACT)])
    check("machine-learning research prose is NOT a prohibition", res["result"], "PASS")
    check(
        "…but the mention is still reported",
        "machine learning" in (res["pages"][0]["incidental_mentions"] + [r["ai_term"].lower() for r in res["pages"][0]["review_items"]]),
        True,
    )

    res = gate_b([_page("tdm", _PAGE_TDM_OPTOUT)])
    check("TDM opt-out reservation fails", res["result"], "FAIL")

    res = gate_b(
        [
            {
                "role": "pmc_landing",
                "required": True,
                "fetch": {"url": "x", "fetched": False, "http_status": 403, "bytes": 0, "error": "HTTPError 403"},
                "text": "",
            }
        ]
    )
    check("unfetchable required page fails (never a silent pass)", res["result"], "FAIL")

    print("stale-footer detection on raw HTML")
    uris = sorted(set(CC_URI_RE.findall(_PAGE_STALE_FOOTER)))
    check("both licences seen on the trap page", len(uris), 2)

    print("text extraction")
    art = _parse_perm(_PERM_CCBY4)
    txt = extract_article_text(art)
    check("body text extracted", "Hello." in txt, True)
    check("attribution built", "PMC1." in build_attribution(extract_metadata(art), "PMC1", "CC BY 4.0"), True)

    print()
    if failures:
        print("SELF-TEST FAILED: %d assertion(s)" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("SELF-TEST PASSED")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Two-gate licence vetting for PMC articles (gate A: CC BY 4.0 only; "
        "gate B: no AI/LLM/text-mining prohibition).",
    )
    ap.add_argument("pmcids", nargs="*", help="PMCIDs, e.g. PMC8570039 or 8570039")
    ap.add_argument("--self-test", action="store_true", help="run offline unit tests and exit")
    ap.add_argument("--json", metavar="PATH", help="write the full machine-readable report here")
    ap.add_argument("--save-text", metavar="DIR", help="on PASS, write <PMCID>.txt and <PMCID>.provenance.json here")
    ap.add_argument("--publisher", action="store_true", help="also resolve the DOI and scan the publisher page")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.pmcids:
        ap.error("give at least one PMCID, or --self-test")

    reports, failed = [], 0
    for raw in args.pmcids:
        try:
            report, text = vet(raw, check_publisher=args.publisher, want_text=bool(args.save_text))
        except ValueError as exc:
            print("ERROR: %s" % exc, file=sys.stderr)
            return 2
        if args.save_text and report["overall"] == "PASS" and text:
            txt_path, json_path = write_article_files(report, text, args.save_text)
            print("wrote %s" % txt_path)
            print("wrote %s" % json_path)
        print_report(report)
        reports.append(report)
        if report["overall"] != "PASS":
            failed += 1

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(reports, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    print("%d/%d passed both gates" % (len(reports) - failed, len(reports)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
