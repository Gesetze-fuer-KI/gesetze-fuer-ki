from urllib.parse import unquote

import laender_pages

README = """<!-- Quelle der Mailadresse -->

# Landesrecht Hessen – nicht verfügbar

**Das Landesrecht von Hessen fehlt.**

```
User-agent: *
Disallow: /
```
*(geprüft am 20.10.2026)*

## Beschwerde schreiben

**An:** Hessisches Ministerium der Justiz – Poststelle@hmdj.hessen.de<br>
**Betreff:** Freier Zugang zum Landesrecht Hessen

> Sehr geehrte Damen und Herren,
>
> bitte machen Sie es frei zugänglich.
>
> Mit freundlichen Grüßen\\
> [Name]

## Bis dahin

- **[Landesrecht Hessen auf dem Landesportal](https://www.rv.hessenrecht.hessen.de)**: von Hand im Browser lesen.
"""


def test_slug():
    assert laender_pages.slug("Baden-Württemberg") == "baden-wuerttemberg"
    assert laender_pages.slug("Thüringen") == "thueringen"


def test_missing_page_carries_template_and_prefilled_mail():
    page = laender_pages.missing_page("he", "Hessen", README)
    assert page.startswith("# Hessen\n")
    assert "<!--" not in page
    assert '??? quote "Auszug aus der robots.txt"' in page
    assert "**Mail:** [Poststelle@hmdj.hessen.de](mailto:Poststelle@hmdj.hessen.de)" in page
    assert "Grüßen<br>" in page
    mailto = page.split("](mailto:Poststelle@hmdj.hessen.de?", 1)[1].split(")", 1)[0]
    assert unquote(mailto).startswith("subject=Freier Zugang zum Landesrecht Hessen&body=Sehr geehrte Damen und Herren,\n\n")
    assert "](https://www.rv.hessenrecht.hessen.de)" in page
