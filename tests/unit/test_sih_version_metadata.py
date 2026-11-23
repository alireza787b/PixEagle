"""Synthetic Git histories exercise version provenance without compiling PX4."""

from pathlib import Path
import subprocess

import pytest

from tools import sih_baseline


def git(source, *arguments):
    return subprocess.check_output(['git', '-C', str(source), '-c', 'user.name=Fixture',
        '-c', 'user.email=fixture@example.invalid', *arguments], text=True, stderr=subprocess.STDOUT).strip()


@pytest.fixture
def history(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    git(source, 'init', '-b', 'main')
    file = source / 'source.txt'
    file.write_text('first\n')
    git(source, 'add', 'source.txt')
    git(source, 'commit', '-m', 'first')
    first = git(source, 'rev-parse', 'HEAD')
    git(source, 'tag', '-a', 'v1.2.3', '-m', 'synthetic version')
    file.write_text('second\n')
    git(source, 'commit', '-am', 'second')
    expected = dict(describe=git(source, 'describe', '--tags'), tag='v1.2.3',
        tag_object=git(source, 'rev-parse', 'refs/tags/v1.2.3'), tag_commit=first)
    return source, expected


def test_real_reachable_metadata_is_returned_without_changing_head_or_sources(history):
    source, expected = history
    head, contents = git(source, 'rev-parse', 'HEAD'), (source / 'source.txt').read_bytes()
    assert sih_baseline.verify_version_metadata(source, expected) == expected
    assert git(source, 'rev-parse', 'HEAD') == head
    assert (source / 'source.txt').read_bytes() == contents


def test_missing_tag_metadata_refuses_instead_of_falling_back_to_zero(history):
    source, expected = history
    git(source, 'tag', '-d', expected['tag'])
    with pytest.raises(ValueError, match='refusing v0.0.0 fallback'):
        sih_baseline.verify_version_metadata(source, expected)


def test_replaced_tag_object_cannot_claim_the_same_release_name(history):
    source, expected = history
    git(source, 'tag', '-f', '-a', expected['tag'], expected['tag_commit'], '-m', 'different object')
    with pytest.raises(ValueError, match='differs from the pinned'):
        sih_baseline.verify_version_metadata(source, expected)


def test_unreachable_tag_commit_cannot_qualify_the_pinned_head(history):
    source, expected = history
    head = git(source, 'rev-parse', 'HEAD')
    git(source, 'checkout', '--orphan', 'unrelated')
    git(source, 'commit', '-m', 'unrelated root')
    unrelated = git(source, 'rev-parse', 'HEAD')
    git(source, 'checkout', '--detach', head)
    with pytest.raises(ValueError, match='ancestry is unavailable'):
        sih_baseline.verify_version_metadata(source, expected | {'tag_commit': unrelated})


@pytest.mark.parametrize('change', [{'tag': 'v0.0.0'}, {'tag': 'version-1'},
    {'tag_object': 'unknown'}, {'tag_commit': True}, {'unknown': 'field'}])
def test_unknown_or_unpinned_version_metadata_fails_closed(history, change):
    source, expected = history
    with pytest.raises(ValueError, match='missing or unknown'):
        sih_baseline.verify_version_metadata(source, expected | change)


def test_canonical_authority_pins_version_metadata_in_firmware_and_recipe():
    repository = Path(__file__).resolve().parents[2]
    firmware, spec = sih_baseline.authority(repository, simulator='gazebo')
    assert firmware['version']['tag'] == 'v1.18.0-beta1'
    assert firmware['version']['describe'].endswith('-g155f415168')
    changed = firmware | {'version': firmware['version'] | {'tag_object': 'a' * 40}}
    assert sih_baseline.recipe_fingerprint(firmware, spec) != sih_baseline.recipe_fingerprint(changed, spec)
