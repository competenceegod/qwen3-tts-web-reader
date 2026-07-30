import base64
import json

from booksite.site.docusaurus import _plain_search_text


def _styled_code_payload() -> str:
    payload = {
        "backgroundColor": "#fafafa",
        "borderColor": "#e1e1e1",
        "fontSizePt": 9.0,
        "lines": [
            [
                {
                    "text": "from ",
                    "color": "#a626a4",
                    "fontFamily": "Consolas",
                    "fontSizePt": 9.0,
                    "bold": False,
                    "italic": False,
                },
                {
                    "text": "langgraph.graph import StateGraph",
                    "color": "#383a42",
                    "fontFamily": "Consolas",
                    "fontSizePt": 9.0,
                    "bold": False,
                    "italic": False,
                },
            ],
            [],
            [
                {
                    "text": "builder.add_node",
                    "color": "#4078f2",
                    "fontFamily": "Consolas",
                    "fontSizePt": 9.0,
                    "bold": False,
                    "italic": False,
                }
            ],
        ],
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_search_text_indexes_code_without_encoded_style_payload() -> None:
    encoded = _styled_code_payload()
    markdown = (
        "Before code.\n\n"
        f'<PdfCodeBlock data="{encoded}" />\n\n'
        "After code."
    )

    search_text = _plain_search_text(markdown)

    assert search_text == (
        "Before code. from langgraph.graph import StateGraph builder.add_node After code."
    )
    assert encoded not in search_text
    assert "backgroundColor" not in search_text
    assert "fontFamily" not in search_text


def test_search_text_ignores_malformed_pdf_code_payload() -> None:
    markdown = 'Before <PdfCodeBlock data="not-base64" /> After'

    assert _plain_search_text(markdown) == "Before After"


def test_search_text_does_not_collide_with_plain_document_text() -> None:
    encoded = _styled_code_payload()
    markdown = (
        "Literal BOOKSITECODETOKEN0Z.\n\n"
        f'<PdfCodeBlock data="{encoded}" />'
    )

    assert _plain_search_text(markdown).startswith(
        "Literal BOOKSITECODETOKEN0Z. from langgraph.graph"
    )
