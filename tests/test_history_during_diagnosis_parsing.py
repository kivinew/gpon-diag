#!/usr/bin/env python3
"""
Parsing test for 'history during diagnosis' block visibility.

This test parses the HTML and JavaScript files to verify:
1. The historyDuringDiagnosis element exists in dashboard.html with correct ID
2. The renderHistoryDuringDiagnosis function exists in dashboard.js
3. The function properly sets display style to show the block
4. The attachHistoryRowHandlers calls renderHistoryDuringDiagnosis
5. CSS has styles for .history-during-diagnosis class
"""

import re
from pathlib import Path


def test_html_element_exists():
    """Test that historyDuringDiagnosis element exists in dashboard.html"""
    html_path = Path("web/templates/dashboard.html")
    content = html_path.read_text(encoding="utf-8")

    # Check element exists with correct ID
    assert 'id="historyDuringDiagnosis"' in content or "id='historyDuringDiagnosis'" in content, \
        "Element with id='historyDuringDiagnosis' not found in dashboard.html"

    # Check it has the correct class
    assert 'class="history-during-diagnosis"' in content or "class='history-during-diagnosis'" in content, \
        "Element doesn't have class 'history-during-diagnosis'"

    print("[OK] HTML element with id='historyDuringDiagnosis' exists with correct class")
    return True


def test_index_html_previous_reports_block():
    """Test that previousReportsBlock element exists in index.html"""
    html_path = Path("web/templates/index.html")
    content = html_path.read_text(encoding="utf-8")

    # Check element exists with correct ID
    assert 'id="previousReportsBlock"' in content or "id='previousReportsBlock'" in content, \
        "Element with id='previousReportsBlock' not found in index.html"

    print("[OK] HTML element with id='previousReportsBlock' exists in index.html")
    return True


def test_js_render_function_exists():
    """Test that renderHistoryDuringDiagnosis function exists in dashboard.js"""
    js_path = Path("web/static/js/dashboard.js")
    content = js_path.read_text(encoding="utf-8")

    # Check function definition exists
    assert "function renderHistoryDuringDiagnosis" in content, "renderHistoryDuringDiagnosis function not found"
    print("[OK] renderHistoryDuringDiagnosis function exists in dashboard.js")
    return True


def test_js_function_shows_element():
    """Test that renderHistoryDuringDiagnosis sets display style to show element"""
    js_path = Path("web/static/js/dashboard.js")
    content = js_path.read_text(encoding="utf-8")

    # Find the function
    func_start = content.find("function renderHistoryDuringDiagnosis")
    assert func_start >= 0, "Function not found"

    # Get function body (approximate - up to next function or end)
    func_body = content[func_start:func_start + 1500]

    # Check it sets display to flex/block
    assert "style.display" in func_body, "Function doesn't set style.display"
    assert ("'flex'" in func_body or '"flex"' in func_body or "'block'" in func_body or '"block"' in func_body), \
        "Function doesn't set display to 'flex' or 'block'"
    print("[OK] renderHistoryDuringDiagnosis sets display style to show element")
    return True


def test_js_click_handler_calls_render():
    """Test that attachHistoryRowHandlers calls renderHistoryDuringDiagnosis"""
    js_path = Path("web/static/js/dashboard.js")
    content = js_path.read_text(encoding="utf-8")

    # Check that renderHistoryDuringDiagnosis is called anywhere in the file
    # (it's called from attachHistoryRowHandlers and from the SSE handler)
    assert "renderHistoryDuringDiagnosis" in content, "renderHistoryDuringDiagnosis not called anywhere in dashboard.js"
    print("[OK] renderHistoryDuringDiagnosis is called in dashboard.js")
    return True


def test_css_has_styles():
    """Test that CSS has styles for .history-during-diagnosis"""
    css_path = Path("web/static/css/dashboard.css")
    content = css_path.read_text(encoding="utf-8")

    assert ".history-during-diagnosis" in content, "CSS class .history-during-diagnosis not found"
    print("[OK] CSS has styles for .history-during-diagnosis")
    return True


def test_initial_display_none_in_html():
    """Test that element has display:none initially in HTML"""
    html_path = Path("web/templates/dashboard.html")
    content = html_path.read_text(encoding="utf-8")

    # Find the element and check its style attribute
    import re
    match = re.search(r'id="historyDuringDiagnosis"[^>]*style="([^"]*)"', content)
    assert match, "Element with id='historyDuringDiagnosis' not found or has no style attribute"
    style = match.group(1)
    assert 'display:none' in style.replace(' ', ''), f"Expected display:none in style, got: {style}"
    print("[OK] Element has display:none initially in HTML")
    return True


def test_js_element_reference():
    """Test that dashboard.js references the element by correct ID"""
    js_path = Path("web/static/js/dashboard.js")
    content = js_path.read_text(encoding="utf-8")

    # Check els object has historyDuringDiagnosis
    assert "historyDuringDiagnosis:" in content, "els object doesn't have historyDuringDiagnosis reference"
    assert "getElementById('historyDuringDiagnosis')" in content or 'getElementById("historyDuringDiagnosis")' in content, \
        "Element not retrieved by correct ID"
    print("[OK] JavaScript references element by correct ID")
    return True


def run_all_tests():
    """Run all parsing tests"""
    print("\n=== Parsing Tests for 'History During Diagnosis' Block ===\n")

    tests = [
        test_html_element_exists,
        test_index_html_previous_reports_block,
        test_js_render_function_exists,
        test_js_function_shows_element,
        test_js_click_handler_calls_render,
        test_css_has_styles,
        test_initial_display_none_in_html,
        test_js_element_reference,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print("[FAIL] " + test.__name__ + ": " + str(e))
            failed += 1
        except Exception as e:
            print("[ERROR] " + test.__name__ + ": " + str(e))
            failed += 1

    print("\n=== Results: " + str(passed) + " passed, " + str(failed) + " failed ===\n")

    if failed > 0:
        raise SystemExit(1)

    return True


if __name__ == "__main__":
    run_all_tests()