"""Bilingual first-contact templates (never sent automatically)."""
from __future__ import annotations

from pathlib import Path

TEMPLATE_EN = """Hello, I found your listing for the apartment in Miraflores: [LISTING LINK]

My partner and I are interested and would be grateful if you could confirm:
1. Is the apartment still available?
2. What is the final monthly rent?
3. What is the monthly maintenance fee?
4. Which utilities are included (water, electricity, gas, internet)?
5. Is internet included?
6. What is the minimum lease term?
7. How many months of deposit (and advance) are required?
8. Is it fully furnished? Could you share an inventory?
9. Do the bedroom and living room face the street or the interior of the building? Is there traffic or nightlife noise?
10. What documents do you require from a foreign tenant?
11. When could we visit? Ideally we would see it once on a weekday evening.

Thank you very much. Kind regards,
[YOUR NAME] · [PHONE]"""

TEMPLATE_ES = """Hola, vi su anuncio del departamento en Miraflores: [ENLACE DEL ANUNCIO]

Somos una pareja interesada y les agradecería confirmar:
1. ¿El departamento sigue disponible?
2. ¿Cuál es el precio final de alquiler mensual?
3. ¿Cuánto es el mantenimiento mensual?
4. ¿Qué servicios están incluidos (agua, luz, gas, internet)?
5. ¿El internet está incluido?
6. ¿Cuál es el plazo mínimo del contrato?
7. ¿Cuántos meses de garantía (y adelanto) se requieren?
8. ¿Está completamente amoblado? ¿Podrían enviarnos el inventario?
9. ¿El dormitorio y la sala dan a la calle o al interior del edificio? ¿Hay ruido de tráfico o de locales nocturnos?
10. ¿Qué documentos solicitan a un inquilino extranjero?
11. ¿Cuándo podríamos visitarlo? De preferencia, un día de semana por la tarde-noche.

Muchas gracias. Saludos cordiales,
[SU NOMBRE] · [TELÉFONO]"""


def write_contact_templates(path: Path, top_rows: list[dict] | None = None) -> Path:
    lines = [
        "MIRAFLORES RENTAL SEARCH — CONTACT TEMPLATES",
        "Nothing has been sent automatically. Copy, fill in the brackets, and send yourself.",
        "",
        "=" * 72, "ENGLISH", "=" * 72, TEMPLATE_EN, "",
        "=" * 72, "ESPAÑOL", "=" * 72, TEMPLATE_ES, "",
        "=" * 72, "SHORT WHATSAPP VERSION (ES)", "=" * 72,
        "Hola, vi su anuncio del depa en Miraflores ([ENLACE]). ¿Sigue disponible? ¿Cuánto es el mantenimiento, "
        "qué servicios incluye, plazo mínimo de contrato y meses de garantía? ¿Da a la calle o al interior? "
        "¿Podríamos visitarlo esta semana? Gracias.",
        "",
        "=" * 72, "SHORT WHATSAPP VERSION (EN)", "=" * 72,
        "Hi, I saw your Miraflores apartment listing ([LINK]). Is it still available? What are the maintenance fee, "
        "included utilities, minimum lease term and deposit? Does it face the street or the interior? Could we "
        "visit this week? Thank you.",
    ]
    if top_rows:
        lines += ["", "=" * 72, "TOP 10 — LINKS TO PASTE", "=" * 72]
        for k, r in enumerate(top_rows, start=1):
            lines.append(f"{k:>2}. {r.get('_label')} — {r.get('source_url')}")
            if r.get("_contact"):
                lines.append(f"    Contact: {r['_contact']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
