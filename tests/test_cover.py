"""A distributor's cover sheet in front of an article becomes front matter."""

from scriptor.reflow.core import Page, assign_modes
from scriptor.reflow.cover import distributor_cover

# As the sheets print them (5698, 7228), broken across lines the way the
# backend delivers them.
JSTOR = [
    "The Routes of the Radanites",
    "Author(s): L. Rabinowitz",
    "Source: The Jewish Quarterly Review, New Series, Vol. 35, No. 3 (Jan., 1945), pp. 251-280",
    "Stable URL: http://www.jstor.org/stable/1452187",
    "Your use of the JSTOR archive indicates your acceptance of the Terms & Conditions of Use,",
    "JSTOR is a not-for-",
    "profit service that helps scholars, researchers, and students discover, use, and build upon",
]
PERSEE = [
    "Revue d'histoire de l'Église de France",
    "Le rôle de l'aristocratie dans la christianisation du nord-est de la Gaule",
    "Citer ce document / Cite this document :",
    "Werner Karl Ferdinand. Le rôle de l'aristocratie ... pp. 45-73;",
    "https://www.persee.fr/doc/rhef_0300-9505_1976_num_62_168_1565",
    "Fichier pdf généré le 29/06/2022",
]
PROSE = ["AMONG the many steps taken by Abdal-malik (691-705), the fifth of the Ommayad"] * 12


def test_jstor_and_persee_sheets_are_told_by_their_boilerplate():
    assert distributor_cover(JSTOR) == "JSTOR"
    assert distributor_cover(PERSEE) == "Persée"


def test_one_sign_is_not_enough():
    """A reference in an article's note may print a stable URL."""
    note = ["1 See Stable URL: http://www.jstor.org/stable/1452187 for the edition."]
    assert distributor_cover(PROSE + note) is None


def test_the_sheet_is_front_matter_and_the_article_opens_the_main_text():
    pages = [Page(num=-1, body_lines=JSTOR, index=1),
             Page(num=-1, body_lines=PROSE, index=2),
             Page(num=-1, body_lines=PROSE, index=3)]
    assign_modes(pages)
    assert [p.mode for p in pages] == ["frontmatter", "main", "main"]


def test_only_the_first_page_is_asked():
    pages = [Page(num=-1, body_lines=PROSE, index=1),
             Page(num=-1, body_lines=JSTOR, index=2)]
    assign_modes(pages)
    assert [p.mode for p in pages] == ["main", "main"]
