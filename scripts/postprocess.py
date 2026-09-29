#!/usr/bin/env python3
"""Post-process the wget mirror in docs/ into a clean static site.

- fetches assets wget missed (srcset etc.) and makes qonsulta.se asset URLs relative
- strips ?ver= query strings from asset filenames
- uses clean directory URLs (kontakt/ instead of kontakt/index.html)
- removes WordPress-only <link> tags (wp-json, xmlrpc, feeds, oembed)
- restores the Företag / Jobbsökande top menu that switches the main nav
- replaces the Ninja Forms contact form with a static form posting to Web3Forms

Safe to re-run.
"""
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "docs"
ORIGIN = "https://qonsulta.se"
STATIC = Path(__file__).resolve().parent / "static"

# Web3Forms access key (public by design; tied to the inbox that receives submissions).
# Create one at https://web3forms.com with the client's email address.
WEB3FORMS_KEY = "116b0b1a-640e-4454-8f73-cb414160ce9e"

# Pages belonging to each side of the site (by URL dir, "" = home).
FORETAG_PAGES = {"", "saljkonsult", "rekrytering", "om-oss", "kontakt"}
KANDIDAT_PAGES = {"jobbsokande", "lediga-tjanster", "karriar"}

TOP_MENU_CSS = """
<style id="qonsulta-top-menu">
.header--row-inner.header-top-inner{padding-top:10px}
.header-top{--rowbcolor:var(--nv-light-bg);--color:var(--nv-text-color);--bgcolor:var(--nv-primary-accent)}
.header-top .builder-item,.header-top .component-wrap{margin:0}
.header-top .hfg-slot.center{padding:0;display:flex;justify-content:center}
.top-menu{gap:10px;align-items:center}
.top-menu .wp-block-button{margin:0;padding:0}
/* Self-contained: WordPress only loaded the button-block CSS on pages that use buttons. */
.top-menu .wp-block-button__link{display:inline-block;margin:0;padding:8px 20px;border:0;border-radius:30px;background-color:#d96b00;color:#fff;font-family:Poppins,Arial,Helvetica,sans-serif;font-size:16px;font-weight:900;line-height:1.2;letter-spacing:1px;text-transform:uppercase;text-decoration:none;white-space:nowrap;transition:opacity .15s}
.top-menu .wp-block-button__link:hover{color:#fff;opacity:.85}
.top-menu .foretag-knapp .wp-block-button__link{padding-left:42px;padding-right:42px}
.top-menu .inactive .wp-block-button__link{background-color:#5d636a;font-weight:400}
body.side-foretag .nav-kandidat,body.side-kandidat .nav-foretag{display:none!important}
.header-top .header-top-inner{background-color:var(--nv-primary-accent)}
.page-id-35 .header-top .header-top-inner,.page-id-37 .header-top .header-top-inner,.page-id-45 .header-top .header-top-inner{background-color:transparent}
@media (max-width:959px){
.header-top .hfg-slot.left,.header-top .hfg-slot.right{display:none}
.header-top .row--wrapper{display:flex;justify-content:center}
.header-top .hfg-slot.center{flex:0 0 auto;max-width:100%}
.top-menu .wp-block-button__link,.top-menu .foretag-knapp .wp-block-button__link{padding:8px 18px;font-size:14px}
}
</style>
"""


def top_menu_html(prefix, side):
    f_cls = "" if side == "foretag" else " inactive"
    k_cls = "" if side == "kandidat" else " inactive"
    return (
        '<div class="hfg-slot center"><div class="builder-item top-menu" style="display:flex">'
        f'<div class="wp-block-button is-style-primary foretag-knapp{f_cls}">'
        f'<a href="{prefix or "./"}" class="wp-block-button__link wp-element-button">Företag</a></div>'
        f'<div class="wp-block-button is-style-primary jobbsokande-knapp{k_cls}">'
        f'<a href="{prefix}jobbsokande/" class="wp-block-button__link wp-element-button">Jobbsökande</a></div>'
        "</div></div>"
    )


def contact_form_html():
    def field(id_, label, tag, required, **attrs):
        req = ' <span class="q-req">*</span>' if required else ""
        a = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        a += " required" if required else ""
        el = f"<textarea id=\"{id_}\"{a}></textarea>" if tag == "textarea" else f"<input id=\"{id_}\"{a}>"
        return f'<div class="q-field"><label for="{id_}">{label}{req}</label>{el}</div>'

    return (
        "<!-- q-contact-form -->"
        '<form class="q-contact-form">'
        f'<input type="hidden" name="access_key" value="{WEB3FORMS_KEY}">'
        '<input type="hidden" name="subject" value="Nytt meddelande från qonsulta.se">'
        '<input type="hidden" name="from_name" value="Qonsulta webbplats">'
        '<input type="checkbox" name="botcheck" class="q-botcheck" tabindex="-1" autocomplete="off" aria-hidden="true">'
        '<p class="q-form-required-note">Fält markerade med en <span class="q-req">*</span> är obligatoriskt</p>'
        + field("q-name", "Namn", "input", True, type="text", name="Namn", autocomplete="name")
        + field("q-email", "E-post", "input", True, type="email", name="email", autocomplete="email")
        + field("q-phone", "Telefon", "input", False, type="tel", name="Telefon", autocomplete="tel")
        + field("q-message", "Meddelande", "textarea", True, name="Meddelande")
        + '<button type="submit">Skicka</button>'
        '<div class="q-form-status" role="status" aria-live="polite"></div>'
        "</form><!-- /q-contact-form -->"
    )


NINJA_SCRIPT_IDS = "underscore-js|backbone-js|googlesitekit-events-provider-ninja-forms-js|nf-front-end-deps-js|nf-front-end-js-extra|nf-front-end-js"


def replace_contact_form(text, prefix):
    """Swap the Ninja Forms embed (or a previous static form) for the static form."""
    form = contact_form_html()
    text = re.sub(
        r'<noscript class="ninja-forms-noscript-message">.*?</noscript>\s*<div id="nf-form-\d+-cont".*?nfForms\.push\(form\);</script>',
        lambda m: form, text, flags=re.S,
    )
    text = re.sub(r"<!-- q-contact-form -->.*?<!-- /q-contact-form -->", lambda m: form, text, flags=re.S)
    # Drop Ninja Forms' assets on every page (underscore/backbone are only used by Ninja Forms).
    text = re.sub(r"<script id=['\"]tmpl-nf-[^'\"]+['\"] type=['\"]text/template['\"]>.*?</script>\s*", "", text, flags=re.S)
    text = re.sub(rf"<script[^>]*id=['\"](?:{NINJA_SCRIPT_IDS})['\"][^>]*>.*?</script>\s*", "", text, flags=re.S)
    text = re.sub(r"<link[^>]*id=['\"]nf-[\w-]+-css['\"][^>]*>\s*", "", text)
    if "q-contact-form" not in text:
        return text
    # Our assets.
    text = re.sub(r'\s*<link rel="stylesheet" href="[./]*assets/contact-form\.css">', "", text)
    text = re.sub(r'\s*<script src="[./]*assets/contact-form\.js" defer></script>', "", text)
    text = text.replace(
        "</head>",
        f'<link rel="stylesheet" href="{prefix}assets/contact-form.css">\n'
        f'<script src="{prefix}assets/contact-form.js" defer></script>\n</head>', 1,
    )
    return text


def local_path_for(url_path):
    """Map an asset URL path (possibly with query) to a clean file path under ROOT."""
    path = urllib.parse.unquote(url_path.split("?")[0].split("#")[0])
    return ROOT / path.lstrip("/")


def fetch(url_path):
    dest = local_path_for(url_path)
    if dest.exists():
        return True
    try:
        with urllib.request.urlopen(ORIGIN + url_path.split("#")[0], timeout=30) as r:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.read())
        print("fetched", url_path)
        return True
    except Exception as e:  # keep absolute URL if it can't be fetched
        print("FAILED", url_path, e)
        return False


def strip_query_filenames():
    """Rename 'foo.css?ver=1.2.css' / 'foo.js?ver=1' to 'foo.css' / 'foo.js'."""
    renames = {}
    for p in list(ROOT.rglob("*")):
        if p.is_file() and "?" in p.name:
            base = p.name.split("?")[0]
            target = p.with_name(base)
            if not target.exists():
                p.rename(target)
            else:
                p.unlink()
            renames[p.name] = base
    return renames


def rel_prefix(html_file):
    depth = len(html_file.relative_to(ROOT).parts) - 1
    return "../" * depth


def process_text(text, prefix, renames):
    # wget-renamed files are referenced URL-encoded ('%3F'); point them at the clean name.
    def fix_query_ref(m):
        ref = m.group(0)
        name = urllib.parse.unquote(ref.rsplit("/", 1)[-1])
        return ref[: len(ref) - len(ref.rsplit("/", 1)[-1])] + renames[name] if name in renames else ref

    text = re.sub(r"[\w./-]+%3F[^\"')\s,]*", fix_query_ref, text)

    # Absolute asset URLs -> relative (download if missing).
    def fix_abs_asset(m):
        url_path = m.group(1)
        if fetch(url_path):
            clean = url_path.split("?")[0]
            return prefix + clean.lstrip("/")
        return m.group(0)

    text = re.sub(
        r"(?:https?:)?//qonsulta\.se(/wp-(?:content|includes)/[^\s\"'),]+?\.(?:webp|jpe?g|png|gif|svg|ico|css|js|woff2?|ttf|eot|pdf|mp4))(?:\?[^\s\"'),]*)?(?=[\s\"'),])",
        fix_abs_asset,
        text,
    )
    return text


def process_html(f, renames):
    prefix = rel_prefix(f)
    text = f.read_text(encoding="utf-8")
    text = process_text(text, prefix, renames)

    # WordPress-only head links.
    text = re.sub(
        r"<link[^>]+(?:wp-json|xmlrpc\.php|/feed/|oembed|rel=['\"]shortlink)[^>]*>\s*", "", text
    )

    # Clean internal page URLs.
    text = re.sub(r'href="(?:\.\./)*kontakt\.html', f'href="{prefix}kontakt/', text)
    text = re.sub(r'href="((?:\.\./)*)([\w-]+/)?index\.html(#[^"]*)?"',
                  lambda m: f'href="{(m.group(1) or "") + (m.group(2) or "") or "./"}{m.group(3) or ""}"', text)

    # Restore the top menu (desktop + mobile header-top rows).
    page = f.parent.relative_to(ROOT).as_posix()
    page = "" if page == "." else page
    side = "kandidat" if page in KANDIDAT_PAGES else "foretag"
    # Remove a previous injection so changes here are re-applied on re-runs.
    text = re.sub(r'\s*<style id="qonsulta-top-menu">.*?</style>\s*', "", text, flags=re.S)
    text = re.sub(r'<div class="hfg-slot center"><div class="builder-item top-menu".*?Jobbsökande</a></div></div></div>', "", text)
    text = re.sub(r'(<body[^>]*class=")side-\w+ ', r"\1", text, count=1)
    text = re.sub(
        r'(data-section="hfg_header_layout_top"\s*>\s*<div class="hfg-slot left"></div>)',
        lambda m: m.group(1) + top_menu_html(prefix, side),
        text,
    )
    text = text.replace("</head>", TOP_MENU_CSS + "</head>", 1)
    text = re.sub(r'(<body[^>]*class=")', rf"\1side-{side} ", text, count=1)

    text = replace_contact_form(text, prefix)
    f.write_text(text, encoding="utf-8")


def main():
    renames = strip_query_filenames()
    stray = ROOT / "kontakt.html"
    if stray.exists():
        stray.unlink()
    for f in ROOT.rglob("*.css"):
        # CSS url()s are relative to the CSS file itself.
        prefix = "../" * (len(f.relative_to(ROOT).parts) - 1)
        t = f.read_text(encoding="utf-8", errors="ignore")
        new = process_text(t, prefix, renames)
        new = re.sub(r"(url\([\"']?[^\"')]*?\.(?:woff2?|ttf|eot|svg))%3F[^\"')#]*", r"\1", new)
        if new != t:
            f.write_text(new, encoding="utf-8")
    for f in ROOT.rglob("*.html"):
        process_html(f, renames)
    shutil.copytree(STATIC, ROOT, dirs_exist_ok=True)
    (ROOT / "CNAME").write_text("qonsulta.se\n")
    (ROOT / ".nojekyll").write_text("")


if __name__ == "__main__":
    main()
