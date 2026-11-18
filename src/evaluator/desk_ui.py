"""Common navigation and document layout for Integrity Desk."""
from html import escape
from pathlib import Path
from string import Template

STATIC = Path(__file__).parent / 'static'


def _asset(name):
    return (STATIC / name).read_text(encoding='utf-8')


def shell(title, content, notice='', *, active='', workspace=False, workspace_url='/'):
    if workspace:
        workspace_links = ''.join(
            f'<button data-screen="{key}">{label}</button>'
            for key, label in (
                ('import', 'Workbook library'),
                ('workspace', 'Location review'),
                ('results', 'Calculation results'),
            )
        )
    else:
        workspace_links = f'<a href="{escape(workspace_url, quote=True)}">Inspection workspace</a>'

    def link(path, label):
        current = ' aria-current="page"' if active == path else ''
        return f'<a href="{path}"{current}>{label}</a>'

    navigation = (
        f'<nav aria-label="Inspection workspace">{workspace_links}</nav>'
        '<nav aria-label="Engineering tools">'
        + link('/tanks', 'Tank assessments')
        + link('/codes', 'Code reference library') + '</nav>'
    )
    return Template(_asset('desk_shell.html')).substitute(
        title=escape(title),
        document_title='Integrity Desk' if workspace else f'{escape(title)} · Integrity Desk',
        navigation=navigation,
        scripts='<script defer src="/assets/workspace.js"></script>' if workspace else '',
        tools=_asset('desk_project_tools.html') if workspace else '',
        notice=('<div id="message" role="status" aria-live="polite" hidden></div>' if workspace else
                f'<div id="message" class="error" role="alert">{escape(notice)}</div>' if notice else ''),
        main_class='' if workspace else 'desk-document',
        content=content,
        overlays=_asset('desk_overlays.html') if workspace else '',
    )


def workspace_page():
    return shell('Workbook library', _asset('workspace.html'), workspace=True)
