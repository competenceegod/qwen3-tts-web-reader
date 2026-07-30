from booksite.site.docusaurus import _plain_search_text


def test_search_text_omits_encoded_pdf_code_component_payload() -> None:
    markdown = (
        "Before code.\n\n"
        '<PdfCodeBlock data="eyJsaW5lcyI6W119" />\n\n'
        "After code."
    )

    assert _plain_search_text(markdown) == "Before code. After code."
