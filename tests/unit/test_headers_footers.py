from booksite.normalize.headers_footers import MarginalLine, find_repeated_marginal_text


def test_repeated_top_and_bottom_lines_are_detected_without_body_false_positive() -> None:
    lines = []
    for page in range(10):
        lines.extend(
            [
                MarginalLine(page, "Generative AI with LangChain", 0.03),
                MarginalLine(page, "Repeated words in body", 0.5),
                MarginalLine(page, str(page + 1), 0.96),
            ]
        )

    repeated = find_repeated_marginal_text(lines, page_count=10, minimum_ratio=0.4)

    assert "generative ai with langchain" in repeated
    assert "<page-number>" in repeated
    assert "repeated words in body" not in repeated
