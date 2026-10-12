"""Позволить импортировать пакет site рядом со стандартным модулем Python."""

from __future__ import annotations

import site as _stdlib_site
from pathlib import Path


# Стандартный модуль site загружается раньше пользовательских модулей и
# обычно не является пакетом. Добавляем путь проекта, чтобы работал импорт
# site.app, требуемый для запуска каталога.
_project_site = Path(__file__).resolve().parent / "site"
if _project_site.is_dir():
    _stdlib_site.__path__ = [str(_project_site)]
