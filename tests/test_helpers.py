"""Pure-helper tests - no model, no GPU."""

from app.ocr_core import is_degenerate, post_correct


def test_good_text_not_degenerate():
    txt = (
        "Office of the Director-General, Anti-Corruption Bureau.\n"
        "Sri P. Ramachandra Rao is directed to conduct further "
        "investigation in the matter and submit the report.\n"
        "Copy to the Joint Director, Hyderabad."
    )
    assert is_degenerate(txt) is False


def test_repeated_line_loop_is_degenerate():
    txt = "\n".join(["<signature>Signature</signature>"] * 30)
    assert is_degenerate(txt) is True


def test_number_explosion_is_degenerate():
    txt = "Cr.No. 1/10/11/03/04/05/06/07/08/09/12/01/3/14/15 to D.P.O."
    assert is_degenerate(txt) is True


def test_empty_is_degenerate():
    assert is_degenerate("   \n  \n") is True


def test_post_correct_applies_and_logs():
    txt = "Sri P. Ramachandra Rao, I/C. D.S.R., in Cr.No.5/AOD-NZB/2004."
    out, log = post_correct(txt, {"D.S.R.": "D.S.P.", "AOD-NZB": "ACB-NZB"})
    assert "D.S.P." in out and "ACB-NZB" in out
    assert len(log) == 2


def test_post_correct_noop():
    out, log = post_correct("clean text", {"X": "Y"})
    assert out == "clean text"
    assert log == []
