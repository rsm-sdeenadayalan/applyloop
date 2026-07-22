from applyloop.discovery.html_text import html_to_text


def test_strips_tags_and_entities():
    html = "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;"
    assert html_to_text(html) == "Hello & welcome"


def test_plain_html():
    assert html_to_text("<ul><li>Python</li><li>SQL</li></ul>") == "Python SQL"
