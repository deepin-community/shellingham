import pathlib
import shutil
import subprocess

import invoke
import parver

from towncrier._builder import (
    find_fragments, render_fragments, split_fragments,
)
from towncrier._settings import load_config


ROOT = pathlib.Path(__file__).resolve().parent.parent

INIT_PY = ROOT.joinpath('src', 'shellingham', '__init__.py')


@invoke.task()
def clean(ctx):
    """Clean previously built package artifacts.
    """
    ctx.run(f'python setup.py clean')
    dist = ROOT.joinpath('dist')
    print(f'[clean] Removing {dist}')
    if dist.exists():
        shutil.rmtree(str(dist))


def _read_version():
    out = subprocess.check_output(['git', 'tag'], encoding='ascii')
    version = max(parver.Version.parse(v).normalize() for v in (
        line.strip() for line in out.split('\n')
    ) if v)
    return version


def _write_version(v):
    lines = []
    with INIT_PY.open() as f:
        for line in f:
            if line.startswith('__version__ = '):
                line = f'__version__ = {repr(str(v))}\n'
            lines.append(line)
    with INIT_PY.open('w', newline='\n') as f:
        f.write(''.join(lines))


def _render_log():
    """Totally tap into Towncrier internals to get an in-memory result.
    """
    config = load_config(ROOT)
    definitions = config['types']
    fragments, fragment_filenames = find_fragments(
        pathlib.Path(config['directory']).absolute(),
        config['sections'],
        None,
        definitions,
    )
    rendered = render_fragments(
        pathlib.Path(config['template']).read_text(encoding='utf-8'),
        config['issue_format'],
        split_fragments(fragments, definitions),
        definitions,
        config['underlines'][1:],
    )
    return rendered


REL_TYPES = ('major', 'minor', 'patch',)


def _bump_release(version, type_):
    if type_ not in REL_TYPES:
        raise ValueError(f'{type_} not in {REL_TYPES}')
    index = REL_TYPES.index(type_)
    next_version = version.base_version().bump_release(index)
    print(f'[bump] {version} -> {next_version}')
    return next_version


PREBUMP = 2     # Default to next patch number.


def _prebump(version):
    next_version = version.bump_release(PREBUMP).bump_dev()
    print(f'[bump] {version} -> {next_version}')
    return next_version


@invoke.task(pre=[clean])
def release(ctx, type_, repo):
    """Make a new release.
    """
    version = _read_version()
    version = _bump_release(version, type_)
    _write_version(version)

    # Needs to happen before Towncrier deletes fragment files.
    tag_content = _render_log()

    ctx.run('towncrier')

    ctx.run(f'git commit -am "Release {version}"')

    tag_content = tag_content.replace('"', '\\"')
    ctx.run(f'git tag -a {version} -m "Version {version}\n\n{tag_content}"')

    ctx.run(f'setl publish --repository="{repo}"')

    version = _prebump(version)
    _write_version(version)

    ctx.run(f'git commit -am "Prebump to {version}"')
