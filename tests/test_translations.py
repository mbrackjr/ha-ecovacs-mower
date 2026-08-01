"""strings.json och translations/en.json ska hållas identiska.

Bara ``translations/en.json`` finns (se CLAUDE.md: aldrig en ``sv.json``).
``strings.json`` är källan utvecklare redigerar; ``translations/en.json`` är
vad HA:s frontend faktiskt laddar för engelska. Ingenting i den här
integrationens verktygskedja synkar filerna automatiskt — det görs annars
bara av disciplin. Det här testet är vakten mot att de glider isär.

Ingen HA-import krävs (ren JSON-läsning), så testet körs lokalt på Windows
också, utan ``requires_ha``.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"


def test_strings_and_translations_are_identical() -> None:
    """Jämför tolkat JSON, inte råa bytes: formattering ska inte kunna fälla testet."""
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    translations = json.loads(
        (ROOT / "translations" / "en.json").read_text(encoding="utf-8")
    )

    assert strings == translations
