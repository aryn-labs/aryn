"""Owner-file parsing only: every credential is synthetic, no network dispatch."""
import json
import importlib.util
import os
import sys
import stat
from types import SimpleNamespace

import pytest

from scripts import github_uat as uat

TOKEN = "github_pat_" + "s" * 82
VALUES = {"ARYN_GITHUB_UAT_TOKEN": TOKEN, "ARYN_GITHUB_UAT_REPOSITORY": "aryn-labs/aryn",
    "ARYN_GITHUB_UAT_ISSUE_NUMBER": "42", "ARYN_GITHUB_UAT_ENABLE_LIVE": "1"}


def write_config(tmp_path, values=None):
    path = tmp_path / ".env.github-uat"
    path.write_text("\n".join(key + "=" + value for key, value in (values or VALUES).items()), encoding="ascii")
    return path


def test_allowlisted_file_yields_masked_secret_without_environment_mutation(tmp_path, caplog, monkeypatch):
    for name in uat.VARIABLES:
        monkeypatch.setenv(name, "synthetic-ambient-value")
    before = {name: os.environ[name] for name in uat.VARIABLES}
    config = uat.load_config(write_config(tmp_path), confirmed=True)
    assert config.plan.repository == "aryn-labs/aryn" and config.plan.issue_number == 42
    assert config.token.get_secret_value() == TOKEN
    assert TOKEN not in repr(config) + str(config.token) + config.plan.model_dump_json() + caplog.text
    assert {name: os.environ[name] for name in uat.VARIABLES} == before


def test_confirmation_precedes_any_file_read(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing confirmation must not open any owner file.")
    monkeypatch.setattr(os, "open", forbidden)
    with pytest.raises(uat.UATError, match="uat_confirmation_required"):
        uat.load_config(tmp_path / ".env.github-uat")


@pytest.mark.parametrize("value", ["0", "", "true", "yes", "2", "1 ", '"1"'])
def test_live_gate_default_denies(tmp_path, value):
    values = {**VALUES, "ARYN_GITHUB_UAT_ENABLE_LIVE": value}
    with pytest.raises(uat.UATError, match="uat_live_gate_disabled"):
        uat.load_config(write_config(tmp_path, values), confirmed=True)


@pytest.mark.parametrize("field", list(VALUES))
def test_required_configuration_cannot_fall_back_to_environment(tmp_path, monkeypatch, field):
    monkeypatch.setenv(field, VALUES[field])
    values = {key: value for key, value in VALUES.items() if key != field}
    with pytest.raises(uat.UATError):
        uat.load_config(write_config(tmp_path, values), confirmed=True)


@pytest.mark.parametrize("number", ["0", "-1", "01", "2147483648", "99999999999", "42.0", "true", "42/../1", "42?x=1", " 42", ""])
def test_invalid_issue_number_is_sanitized(tmp_path, number):
    with pytest.raises(uat.UATError, match="uat_issue_number_invalid"):
        uat.load_config(write_config(tmp_path, {**VALUES, "ARYN_GITHUB_UAT_ISSUE_NUMBER": number}), confirmed=True)


@pytest.mark.parametrize("repository", ["other/private", "ARYN-labs/aryn", "aryn-labs/aryn/", "https://github.com/aryn-labs/aryn", ""])
def test_only_exact_owner_repository_is_allowed(tmp_path, repository):
    with pytest.raises(uat.UATError, match="uat_repository_invalid"):
        uat.load_config(write_config(tmp_path, {**VALUES, "ARYN_GITHUB_UAT_REPOSITORY": repository}), confirmed=True)


@pytest.mark.parametrize("token", ["", "short", "ghp_" + "a" * 40, "github_pat_" + "x" * 246,
    "github_pat_" + "x" * 21, "${OTHER_TOKEN}", "$(Get-Secret)", "`whoami`", '"' + TOKEN + '"', TOKEN + " "])
def test_invalid_or_missing_token_never_appears_in_error(tmp_path, caplog, token):
    with pytest.raises(uat.UATError) as error:
        uat.load_config(write_config(tmp_path, {**VALUES, "ARYN_GITHUB_UAT_TOKEN": token}), confirmed=True)
    assert str(error.value) in {"uat_token_missing", "uat_token_format_invalid"}
    assert TOKEN not in str(error.value) + caplog.text


@pytest.mark.parametrize("extra", ["ARYN_GITHUB_UAT_TOKEN=" + TOKEN, "OTHER_TOKEN=" + TOKEN,
    "export ARYN_GITHUB_UAT_TOKEN=" + TOKEN, "garbage", "\x00"])
def test_duplicate_unknown_and_shell_syntax_denied(tmp_path, extra):
    path = write_config(tmp_path)
    with path.open("a", encoding="ascii") as stream:
        stream.write("\n" + extra)
    with pytest.raises(uat.UATError, match="uat_config_invalid"):
        uat.load_config(path, confirmed=True)


def test_oversized_and_missing_file_have_fixed_errors(tmp_path):
    path = tmp_path / ".env.github-uat"
    with pytest.raises(uat.UATError, match="uat_config_unavailable"):
        uat.load_config(path, confirmed=True)
    path.write_bytes(b"x" * 2049)
    with pytest.raises(uat.UATError, match="uat_config_invalid"):
        uat.load_config(path, confirmed=True)


def test_cli_default_deny_and_unknown_secret_argument_do_not_load_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(uat, "ENV_FILE", tmp_path / "absent")
    assert uat.main([]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "uat_confirmation_required"
    assert uat.main(["--token", TOKEN]) == 1
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err
    assert json.loads(output.out)["error_code"] == "uat_config_invalid"


def test_import_does_not_open_owner_file(monkeypatch):
    reads = []
    native = os.open
    def guarded(path, *args, **kwargs):
        if str(path).endswith(".env.github-uat"):
            reads.append(path)
            pytest.fail("Import must not open the owner's token file.")
        return native(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", guarded)
    spec = importlib.util.spec_from_file_location("uat_import_probe", uat.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert not reads


@pytest.mark.parametrize("control", ["\x00", "\x0b", "\x0c", "\t", "\r"])
def test_control_characters_are_not_normalized_into_live_opt_in(tmp_path, control):
    path = write_config(tmp_path)
    path.write_bytes(path.read_bytes() + control.encode())
    with pytest.raises(uat.UATError, match="uat_config_invalid"):
        uat.load_config(path, confirmed=True)


@pytest.mark.parametrize("kind", ["symlink", "non_regular"])
def test_only_regular_owner_file_can_be_loaded(tmp_path, monkeypatch, kind):
    path = write_config(tmp_path)
    if kind == "symlink":
        monkeypatch.setattr(type(path), "is_symlink", lambda _: True)
    else:
        monkeypatch.setattr(os, "fstat", lambda _: SimpleNamespace(st_mode=stat.S_IFDIR, st_size=0))
    with pytest.raises(uat.UATError, match="uat_config_invalid"):
        uat.load_config(path, confirmed=True)
