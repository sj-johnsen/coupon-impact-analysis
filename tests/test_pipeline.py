import json
import shutil

from coupon_analysis import config as C
from coupon_analysis.__main__ import main


def test_full_run_writes_expected_files(tmp_path):
    shutil.copy(C.project_root() / C.DATA_FILENAME, tmp_path / C.DATA_FILENAME)
    assert main(["--root", str(tmp_path), "--no-pdf", "-q"]) == 0
    for name in ("results.json", "appendix.md", "appendix.html", "text.md"):
        assert (tmp_path / name).stat().st_size > 1000, name
    assert len(list((tmp_path / "figures").glob("*.png"))) >= 9
    res = json.loads((tmp_path / "results.json").read_text())
    assert res["did"]["main"]["n_treated"] == 4385
    assert abs(res["did"]["card_krueger"]["did"] - res["did"]["main"]["estimate"]) < 1e-6
    assert res["rd"]["at1000"]["multiple_testing"]["n_reject_holm"] == 0
    assert len(res["rd"]["at1000"]["robustness"]["d34_pre"]) == 10
    assert "{{" not in (tmp_path / "appendix.md").read_text()
    assert "{{" not in (tmp_path / "text.md").read_text()


def test_results_are_deterministic(tmp_path):
    shutil.copy(C.project_root() / C.DATA_FILENAME, tmp_path / C.DATA_FILENAME)
    main(["--root", str(tmp_path), "--no-render", "-q"])
    first = (tmp_path / "results.json").read_text()
    main(["--root", str(tmp_path), "--no-render", "-q"])
    assert first == (tmp_path / "results.json").read_text()


def test_broken_data_gives_exit_code_2(tmp_path, df):
    df.drop(columns=["gender"]).to_csv(tmp_path / C.DATA_FILENAME, index=False)
    assert main(["--root", str(tmp_path), "--no-pdf", "-q"]) == 2


def test_stale_number_gives_exit_code_3(tmp_path):
    shutil.copy(C.project_root() / C.DATA_FILENAME, tmp_path / C.DATA_FILENAME)
    assert main(["--root", str(tmp_path), "--no-pdf", "-q"]) == 0
    text = (tmp_path / "text.md").read_text()
    est = f"{round(json.loads((tmp_path / 'results.json').read_text())['did']['main']['estimate']):,}"
    assert est in text
    (tmp_path / "text.md").write_text(text.replace(est, "9,876", 1))
    assert main(["--root", str(tmp_path), "--no-pdf", "-q"]) == 3


def test_only_report_without_results_is_an_error(tmp_path):
    assert main(["--root", str(tmp_path), "--only", "report", "-q"]) == 2
