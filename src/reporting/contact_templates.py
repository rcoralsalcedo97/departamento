"""First-contact templates (never sent automatically).

Each language file contains: instructions for the client (English or Hindi), the exact Spanish
message to send to the landlord/agent, and a translation of that message so the client knows
precisely what is being asked. The Top-10 section lists every listing with a ready-to-paste
Spanish message that already contains its link.
"""
from __future__ import annotations

from pathlib import Path

TEMPLATE_ES = """Hola, buen día. Vi su anuncio del departamento en Miraflores: [ENLACE DEL ANUNCIO]

Somos una pareja interesada. ¿Podrían confirmarnos, por favor?
1. ¿El departamento sigue disponible?
2. ¿Cuál es el precio final del alquiler mensual?
3. ¿Cuánto es el mantenimiento mensual?
4. ¿Qué servicios están incluidos (agua, luz, gas)?
5. ¿El internet está incluido?
6. ¿Cuál es el plazo mínimo del contrato?
7. ¿Cuántos meses de garantía y de adelanto se requieren?
8. ¿Está completamente amoblado?
9. ¿El dormitorio da a la calle o al interior del edificio? ¿Se escucha ruido de tráfico?
10. ¿Qué requisitos piden a un inquilino extranjero?
11. ¿Aceptan pasaporte como documento de identidad?
12. ¿Qué sustento de ingresos solicitan?
13. ¿Cuándo podríamos visitarlo?

Muchas gracias. Saludos cordiales,
[SU NOMBRE] · [TELÉFONO]"""

TEMPLATE_EN = """Hello, good day. I saw your listing for the apartment in Miraflores: [LISTING LINK]

We are a couple and we are interested. Could you please confirm:
1. Is the apartment still available?
2. What is the final monthly rent?
3. How much is the monthly maintenance fee?
4. Which utilities are included (water, electricity, gas)?
5. Is internet included?
6. What is the minimum rental term?
7. How many months of deposit and of advance are required?
8. Is it fully furnished?
9. Does the bedroom face the street or the interior of the building? Can traffic noise be heard?
10. What are the requirements for a foreign tenant?
11. Do you accept a passport as identification?
12. What proof of income do you require?
13. When could we visit?

Thank you very much. Kind regards,
[YOUR NAME] · [PHONE]"""

TEMPLATE_HI = """नमस्ते। मैंने Miraflores में अपार्टमेंट का आपका विज्ञापन देखा: [विज्ञापन का लिंक]

हम एक दंपति हैं और इसमें रुचि रखते हैं। कृपया इन बातों की पुष्टि करें:
1. क्या अपार्टमेंट अभी उपलब्ध है?
2. अंतिम मासिक किराया कितना है?
3. मासिक रखरखाव शुल्क कितना है?
4. कौन-सी सेवाएँ शामिल हैं (पानी, बिजली, गैस)?
5. क्या इंटरनेट शामिल है?
6. न्यूनतम किराया अवधि कितनी है?
7. कितने महीने की जमा राशि (garantía) और कितने महीने का अग्रिम (adelanto) देना होगा?
8. क्या यह पूरी तरह सुसज्जित है?
9. बेडरूम सड़क की ओर है या भवन के भीतर की ओर? क्या ट्रैफ़िक का शोर सुनाई देता है?
10. विदेशी किरायेदार के लिए क्या शर्तें हैं?
11. क्या आप पहचान-पत्र के रूप में पासपोर्ट स्वीकार करते हैं?
12. आय का कौन-सा प्रमाण चाहिए?
13. हम इसे देखने कब आ सकते हैं?

बहुत धन्यवाद। सादर,
[आपका नाम] · [फ़ोन]"""

SHORT_ES = ("Hola, vi su anuncio del departamento en Miraflores ({link}). ¿Sigue disponible? ¿Precio final, "
            "mantenimiento, servicios e internet incluidos, plazo mínimo, garantía y adelanto? ¿Amoblado? ¿El dormitorio "
            "da a la calle? ¿Requisitos para inquilino extranjero (aceptan pasaporte, sustento de ingresos)? "
            "¿Cuándo podríamos visitarlo? Gracias.")

TEXT = {
    "en": {
        "title": "MIRAFLORES RENTAL SEARCH — CONTACT TEMPLATES (ENGLISH)",
        "intro": ["Nothing has been sent automatically. You decide whom to contact and when.",
                  "How to use: open the listing link, use the portal's contact form or WhatsApp (if the advertiser shows "
                  "one), and paste the SPANISH message below — most landlords and agents in Lima reply in Spanish. Replace "
                  "the text in [brackets]. The ENGLISH version shows exactly what the Spanish message asks.",
                  "Tip: ask for the answers in writing, and for the exact address before visiting."],
        "es": "MESSAGE TO SEND (SPANISH — copy exactly)",
        "tr": "WHAT THE MESSAGE SAYS (ENGLISH)",
        "short": "SHORT VERSION FOR WHATSAPP / PORTAL FORM (SPANISH)",
        "top": "TOP 10 — READY-TO-SEND SPANISH MESSAGES WITH EACH LINK",
        "contact": "Contact",
        "tr_body": TEMPLATE_EN,
    },
    "hi": {
        "title": "MIRAFLORES किराया खोज — संपर्क संदेश (हिंदी)",
        "intro": ["कोई भी संदेश अपने-आप नहीं भेजा गया है। किससे और कब संपर्क करना है, यह आप तय करें।",
                  "उपयोग का तरीका: विज्ञापन का लिंक खोलें, पोर्टल का संपर्क फ़ॉर्म या WhatsApp (यदि विज्ञापनदाता ने दिया हो) "
                  "उपयोग करें, और नीचे दिया गया स्पेनिश संदेश चिपकाएँ — Lima के अधिकांश मकान-मालिक और एजेंट स्पेनिश में उत्तर "
                  "देते हैं। [कोष्ठक] में लिखा पाठ बदलें। हिंदी अनुवाद से आप जान सकते हैं कि स्पेनिश संदेश में ठीक-ठीक क्या पूछा गया है।",
                  "सुझाव: उत्तर लिखित में माँगें, और देखने जाने से पहले सटीक पता पूछ लें।"],
        "es": "भेजने के लिए संदेश (स्पेनिश — ज्यों का त्यों कॉपी करें)",
        "tr": "संदेश का अर्थ (हिंदी अनुवाद)",
        "short": "WhatsApp / पोर्टल फ़ॉर्म के लिए छोटा संदेश (स्पेनिश)",
        "top": "शीर्ष 10 — हर लिंक के साथ भेजने के लिए तैयार स्पेनिश संदेश",
        "contact": "संपर्क",
        "tr_body": TEMPLATE_HI,
    },
}


def write_contact_templates(path: Path, top_rows: list[dict] | None = None, lang: str = "en") -> Path:
    tx = TEXT[lang]
    bar = "=" * 72
    lines = [tx["title"], "", *tx["intro"], "",
             bar, tx["es"], bar, TEMPLATE_ES, "",
             bar, tx["tr"], bar, tx["tr_body"], "",
             bar, tx["short"], bar, SHORT_ES.format(link="[ENLACE]")]
    if top_rows:
        lines += ["", bar, tx["top"], bar]
        for k, r in enumerate(top_rows, start=1):
            lines.append(f"{k:>2}. {r.get('_label')} — {r.get('source_url')}")
            if r.get("_contact"):
                lines.append(f"    {tx['contact']}: {r['_contact']}")
            lines.append("    " + SHORT_ES.format(link=r.get("source_url")))
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path
