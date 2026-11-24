"""The menu owns launch arguments, never flight actions or a second runtime."""
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import launch_training as menu


@pytest.fixture
def config(tmp_path):
    value=dict(version=1, python='/usr/bin/python3', runtime_root=str(tmp_path), environment={},
        arguments=['--build-manifest', '/a path/manifest.json'],
        profiles={'test': dict(label='Test scene', arguments=['--scenario', 'verified-scene'])})
    path=tmp_path/'training.json';path.write_text(json.dumps(value))
    return path,value


def test_example_loads_without_resolving_or_launching_dependencies():
    assert menu.load_config(menu.ROOT/'tools/training-launcher.example.json')['profiles']


@pytest.mark.parametrize('headless',[False,True])
def test_only_the_existing_runner_launches_with_explicit_ui_ownership(config,headless):
    _,value=config
    command,env,runtime=menu.launch_plan(value,'test',headless=headless)
    assert command[1]==str(menu.ROOT/'tools/run_gazebo_training.py')
    assert command.count('--runtime')==1 and command.count('--execute')==1
    assert ('--no-operator-ui' in command)==headless
    assert '/a path/manifest.json' in command  # Kept as one argv element, no shell.
    assert not runtime.exists()
    assert env is not menu.os.environ
    assert not any('takeoff' in x or 'native-follow-start' in x for x in command)


@pytest.mark.parametrize('arguments',[['--runtime','/tmp/old'],['--runtime=/tmp/old'],['--execute'],['--no-operator-ui']])
def test_recipe_cannot_override_launch_ownership(config,arguments):
    path,value=config;value['profiles']['test']['arguments']=arguments;path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='ownership'):
        menu.load_config(path)


def test_interactive_choice_reprompts_and_quit_never_launches(config):
    _,value=config;answers=iter(['bad','2','1']);out=io.StringIO()
    assert menu.choose_profile(value['profiles'],read=lambda _:next(answers),stream=out)=='test'
    assert 'Simulator training' in out.getvalue() and 'Test scene' in out.getvalue()
    assert 'Choose a listed number' in out.getvalue()
    assert menu.choose_profile(value['profiles'],read=lambda _:'q',stream=io.StringIO()) is None


@pytest.mark.parametrize('flag',['--list','--dry-run'])
def test_observation_commands_start_no_process_or_files(config,monkeypatch,flag,capsys):
    path,_=config;execute=Mock();monkeypatch.setattr(menu.os,'execve',execute)
    assert menu.main(['--config',str(path),'--profile','test',flag])==0
    execute.assert_not_called()
    assert capsys.readouterr().out
    assert list(path.parent.iterdir())==[path]


def test_headless_requires_an_explicit_profile(config,monkeypatch):
    path,_=config;execute=Mock();monkeypatch.setattr(menu.os,'execve',execute)
    assert menu.main(['--config',str(path),'--headless'])==2
    execute.assert_not_called()


def test_dispatch_uses_exec_and_preserves_owned_cleanup_signals(config,monkeypatch):
    path,_=config;execute=Mock();monkeypatch.setattr(menu.os,'execve',execute)
    assert menu.main(['--config',str(path),'--profile','test','--headless'])==0
    command,argv,environment=execute.call_args.args
    assert command==argv[0]=='/usr/bin/python3'
    assert '--no-operator-ui' in argv


def test_existing_evidence_is_never_replaced(config):
    path,value=config
    with pytest.raises(ValueError,match='fresh'):
        menu.launch_plan(value,'test',runtime=path.parent)


def test_unknown_environment_and_multiline_labels_reject(config):
    path,value=config;value['environment']={'SECRET_TOKEN':'no'};path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='search paths'):
        menu.load_config(path)
    value['environment']={};value['profiles']['test']['label']='test\nspoofed';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='single-line'):
        menu.load_config(path)


def test_rejects_shadowed_options_instead_of_silently_overriding(config):
    path,value=config;value['profiles']['test']['arguments']+=['--build-manifest=/other.json'];path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='Duplicate launch option'):
        menu.load_config(path)


def test_beginner_menu_hides_advanced_profiles_and_cannot_start_pending(config):
    _,value=config
    value['profiles']['private']=dict(label='Private tailsitter',audience='advanced',arguments=[])
    value['profiles']['fw']=dict(label='Native FW',unavailable_reason='Qualification pending.',arguments=[])
    out=io.StringIO();answers=iter(['2','1'])
    assert menu.choose_profile(value['profiles'],read=lambda _:next(answers),stream=out)=='test'
    assert 'Private tailsitter' not in out.getvalue()
    assert 'Native FW (pending)' in out.getvalue() and 'Qualification pending.' in out.getvalue()
    with pytest.raises(ValueError,match='Qualification pending'):
        menu.launch_plan(value,'fw',headless=True)
    assert '--no-operator-ui' in menu.launch_plan(value,'private',headless=True)[0]


def test_headless_listing_retains_expert_profiles_only_on_explicit_request(config,capsys):
    path,value=config;value['profiles']['private']=dict(label='Expert',audience='advanced',arguments=[])
    path.write_text(json.dumps(value))
    assert menu.main(['--config',str(path),'--list'])==0
    assert 'Expert' not in capsys.readouterr().out
    assert menu.main(['--config',str(path),'--headless','--list'])==0
    assert 'Expert' in capsys.readouterr().out
