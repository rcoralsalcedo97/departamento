"""Hindi (Devanagari) glossary and pattern rules for the client deliverables.

Written for an Indian professional couple: natural, professional Hindi — not word-for-word.
Numbers, currencies, names, addresses, URLs and IDs are carried over verbatim by the patterns.
"""
from __future__ import annotations

import re

LEVEL = {"high": "उच्च", "medium": "मध्यम", "low": "कम"}
RISK = {"LOW": "कम", "MEDIUM": "मध्यम", "HIGH": "अधिक", "UNKNOWN": "अज्ञात"}
BAND = {"very spacious": "बहुत विशाल", "good": "अच्छा", "acceptable": "पर्याप्त", "small": "छोटा"}
VALUE = {"excellent value": "उत्कृष्ट मूल्य", "good value": "अच्छा मूल्य"}
NOISE_LABEL = {"LIKELY QUIET": "संभवतः शांत", "POSSIBLY QUIET": "शायद शांत", "NOISE UNCERTAIN": "शोर अनिश्चित",
               "LIKELY NOISY": "संभवतः शोरगुल वाला"}
FX_SRC = {"BCRP live": "BCRP लाइव", "fallback": "दस्तावेज़ित वैकल्पिक दर"}
PLACES = {"supermarket": "सुपरमार्केट", "pharmacy": "फ़ार्मेसी", "park": "पार्क", "café": "कैफ़े",
          "bus/Metropolitano stop": "बस/Metropolitano स्टॉप", "Malecón": "Malecón"}

HI: dict[str, str] = {
    # ---- glossary requested by the client
    "Rent": "मासिक किराया",
    "Monthly rent": "मासिक किराया",
    "Maintenance": "रखरखाव शुल्क",
    "Estimated total": "अनुमानित कुल मासिक खर्च",
    "Est. total": "अनुमानित कुल खर्च",
    "Est. Total": "अनुमानित कुल खर्च",
    "Est. total / month": "अनुमानित कुल मासिक खर्च",
    "Bedrooms": "बेडरूम",
    "Area": "क्षेत्रफल",
    "Area m²": "क्षेत्रफल m²",
    "Furnished": "सुसज्जित",
    "Noise risk": "शोर का जोखिम",
    "Noise Risk": "शोर का जोखिम",
    "Noise": "शोर",
    "Quietness": "शांत वातावरण",
    "Main advantage": "मुख्य लाभ",
    "Main Advantage": "मुख्य लाभ",
    "Main drawback": "मुख्य कमी",
    "Main Drawback": "मुख्य कमी",
    "Contact via listing": "विज्ञापन के माध्यम से संपर्क करें",
    "View listing": "विज्ञापन देखें",
    "View Listing": "विज्ञापन देखें",
    "Map": "नक्शा देखें",
    "Open map": "नक्शा देखें",
    "Unknown": "जानकारी उपलब्ध नहीं",
    "UNKNOWN": "जानकारी उपलब्ध नहीं",
    # ---- yes / no / generic values
    "Yes": "हाँ", "No": "नहीं", "Semi": "आंशिक रूप से",
    "Included in rent": "किराये में शामिल",
    "Unknown (maint. n/p)": "जानकारी उपलब्ध नहीं (रखरखाव शुल्क प्रकाशित नहीं)",
    "Open": "खोलें",
    "Open WhatsApp": "WhatsApp खोलें",
    "Via portal": "पोर्टल के माध्यम से",
    "TOP 10": "शीर्ष 10",
    "ALTERNATIVE": "विकल्प",
    "NOT_CHECKED": "जाँच नहीं हुई",
    # ---- workbook headers
    "Rank": "क्रम",
    "Tier": "श्रेणी",
    "Fit Score": "उपयुक्तता स्कोर",
    "Property": "संपत्ति",
    "Monthly Rent USD": "मासिक किराया USD",
    "Estimated Total USD": "अनुमानित कुल खर्च USD",
    "Budget Class": "बजट श्रेणी",
    "USD/m²": "USD/m²",
    "Parking": "पार्किंग",
    "Floor": "मंज़िल",
    "Quietness Score": "शांति स्कोर",
    "Location": "स्थान",
    "Contract": "अनुबंध",
    "Deposit": "जमा राशि",
    "Foreign Tenant": "विदेशी किरायेदार",
    "Source": "स्रोत",
    "WhatsApp": "WhatsApp",
    "QA Status": "जाँच की स्थिति",
    "Category": "श्रेणी",
    "Why in this sheet": "इस शीट में क्यों",
    "Rent as published": "प्रकाशित किराया",
    "Rent USD basis": "USD किराये का आधार",
    "Rent PEN": "किराया PEN",
    "Maintenance basis": "रखरखाव शुल्क का आधार",
    "Budget note": "बजट टिप्पणी",
    "Bathrooms": "बाथरूम",
    "Area basis": "क्षेत्रफल का आधार",
    "Space band": "आकार श्रेणी",
    "Value band": "मूल्य श्रेणी",
    "Balcony/Terrace": "बालकनी/टैरेस",
    "Laundry": "लॉन्ड्री",
    "Elevator": "लिफ़्ट",
    "Security": "सुरक्षा",
    "Pets": "पालतू जानवर",
    "Interior view": "भीतर की ओर",
    "Noise category": "शोर श्रेणी",
    "Quietness evidence": "शांत वातावरण का प्रमाण",
    "Nearest major road (m)": "निकटतम मुख्य सड़क (मी)",
    "Nearest nightclub (m)": "निकटतम नाइटक्लब (मी)",
    "Bars ≤150 m": "बार ≤150 मी",
    "Daily needs nearby": "पास की दैनिक सुविधाएँ",
    "Utilities included": "शामिल सेवाएँ",
    "Published": "प्रकाशन तिथि",
    "Active status": "उपलब्धता की स्थिति",
    "Availability": "उपलब्धता",
    "Red flags": "चेतावनी संकेत",
    "Foreign-tenant evidence": "विदेशी किरायेदार से जुड़ा प्रमाण",
    "Agency / agent": "एजेंसी / एजेंट",
    "Phone": "फ़ोन",
    "# Sources": "स्रोतों की संख्या",
    "Duplicate group": "डुप्लिकेट समूह",
    "Duplicate conflicts": "डुप्लिकेट में अंतर",
    "Location source": "स्थान का स्रोत",
    "QA notes": "जाँच टिप्पणियाँ",
    "Why It Stands Out": "यह क्यों ख़ास है",
    "Listing": "विज्ञापन",
    "WhatsApp / Contact": "WhatsApp / संपर्क",
    "Who to contact": "किससे संपर्क करें",
    "Ask specifically": "विशेष रूप से पूछें",
    "Status": "स्थिति",
    "Method": "तरीका",
    "Target search URL": "खोज URL",
    "Records collected": "एकत्रित रिकॉर्ड",
    "Public access": "सार्वजनिक पहुँच",
    "Pagination": "पेज",
    "Detail pages": "विवरण पेज",
    "Contact data": "संपर्क जानकारी",
    "Coordinates": "निर्देशांक",
    "Publication date": "प्रकाशन तिथि",
    "Maintenance fee": "रखरखाव शुल्क",
    "Completeness": "पूर्णता",
    "Limitations / errors": "सीमाएँ / त्रुटियाँ",
    # ---- sheet / section titles
    "Top 10 apartments to contact first — Miraflores, rent ≤ USD 1,000":
        "सबसे पहले संपर्क करने योग्य शीर्ष 10 अपार्टमेंट — Miraflores, मासिक किराया ≤ USD 1,000",
    "Miraflores rental shortlist — Top 10 and strong alternatives":
        "Miraflores किराया शॉर्टलिस्ट — शीर्ष 10 और अच्छे विकल्प",
    "All budget-compliant Miraflores matches": "बजट के भीतर Miraflores के सभी उपयुक्त अपार्टमेंट",
    "Stretch / negotiable (rent USD 1,001–1,100) — kept separate":
        "स्ट्रेच / मोलभाव योग्य (किराया USD 1,001–1,100) — अलग रखे गए",
    "Near misses and borderline cases — never budget-compliant":
        "लगभग उपयुक्त और सीमा-रेखा वाले मामले — बजट के भीतर नहीं",
    "Source audit": "स्रोत ऑडिट",
    "Methodology, scoring and limitations": "कार्यप्रणाली, स्कोरिंग और सीमाएँ",
    "Contact guide — nothing has been sent; contact is left to you":
        "संपर्क मार्गदर्शिका — कोई संदेश नहीं भेजा गया है; संपर्क आप स्वयं करें",
    "Top 10 — who to contact and what to ask": "शीर्ष 10 — किससे संपर्क करें और क्या पूछें",
    # ---- advantages / drawbacks / notes (fixed phrases)
    "meets all hard requirements": "सभी अनिवार्य शर्तें पूरी करता है",
    "interior-facing": "भीतर की ओर (सड़क से दूर)",
    "acoustic/double-glazed windows": "ध्वनिरोधी / डबल-ग्लेज़्ड खिड़कियाँ",
    "furnished": "सुसज्जित",
    "semi-furnished": "आंशिक रूप से सुसज्जित",
    "unfurnished": "असुसज्जित",
    "building security/controlled access": "भवन में सुरक्षा / नियंत्रित प्रवेश",
    "balcony/terrace": "बालकनी / टैरेस",
    "on a major arterial (see noise evidence) — check traffic noise in the bedroom":
        "मुख्य सड़क (आर्टेरियल) पर स्थित (शोर का प्रमाण देखें) — बेडरूम में ट्रैफ़िक का शोर ज़रूर जाँचें",
    "listing says the unit faces an avenue": "विज्ञापन के अनुसार यूनिट एवेन्यू की ओर है",
    "bars/nightlife nearby — check at night": "पास में बार/नाइटलाइफ़ — रात में ज़रूर जाँचें",
    "maintenance fee not published — confirm before visiting":
        "रखरखाव शुल्क प्रकाशित नहीं — देखने जाने से पहले पुष्टि करें",
    "floor area not published": "क्षेत्रफल प्रकाशित नहीं",
    "portal shows an approximate location only": "पोर्टल केवल अनुमानित स्थान दिखाता है",
    "no map location — noise estimate is text-only": "नक्शे पर स्थान नहीं — शोर का अनुमान केवल विज्ञापन के विवरण पर आधारित",
    "no direct phone/WhatsApp — contact via portal": "सीधा फ़ोन/WhatsApp उपलब्ध नहीं — पोर्टल के माध्यम से संपर्क करें",
    "publication date unknown": "प्रकाशन तिथि: जानकारी उपलब्ध नहीं",
    "moderate estimated noise — visit at rush hour and at night":
        "अनुमानित शोर मध्यम — भीड़ के समय और रात में देखने जाएँ",
    "no major drawback identified from listing data": "विज्ञापन के आँकड़ों में कोई बड़ी कमी नहीं मिली",
    "rent within budget; maintenance not published — total unknown":
        "किराया बजट में; रखरखाव शुल्क प्रकाशित नहीं — कुल खर्च अज्ञात",
    "rent unknown": "किराया अज्ञात",
    "location data unavailable (neutral score)": "स्थान संबंधी जानकारी उपलब्ध नहीं (तटस्थ स्कोर)",
    # ---- noise evidence (fixed phrases)
    "listing says interior-facing / contrafrente": "विज्ञापन के अनुसार यूनिट भीतर की ओर (contrafrente) है",
    "acoustic / double-glazed windows mentioned": "ध्वनिरोधी / डबल-ग्लेज़्ड खिड़कियों का उल्लेख",
    "listing says it faces an avenue": "विज्ञापन के अनुसार यूनिट एवेन्यू की ओर है",
    "street-facing unit near a major road": "मुख्य सड़क के पास, सड़क की ओर वाली यूनिट",
    "seller describes the street as quiet (unverified claim)": "विज्ञापनदाता सड़क को शांत बताता है (असत्यापित दावा)",
    "no usable coordinates — text evidence only": "उपयोग योग्य निर्देशांक नहीं — केवल विज्ञापन के विवरण पर आधारित",
    "no map location and no noise-related wording in the listing — street exposure unknown":
        "नक्शे पर स्थान नहीं और विज्ञापन में शोर से जुड़ी कोई जानकारी नहीं — सड़क के शोर का स्तर अज्ञात",
    "portal location is approximate": "पोर्टल का स्थान अनुमानित है",
    # ---- foreign-tenant evidence phrases
    "accepts foreigners": "विदेशी किरायेदार स्वीकार",
    "expat-oriented": "प्रवासियों के लिए उपयुक्त",
    "passport mentioned": "पासपोर्ट का उल्लेख",
    "corporate lease possible": "कंपनी के नाम पर अनुबंध संभव",
    "foreigners welcome / English spoken": "विदेशियों का स्वागत / अंग्रेज़ी बोली जाती है",
    "temporary / short stays offered": "अस्थायी / कम अवधि का किराया उपलब्ध",
    "aimed at executives": "पेशेवरों के लिए उपयुक्त",
    "no guarantor required": "गारंटर की आवश्यकता नहीं",
    "foreigners explicitly not accepted": "विदेशी किरायेदार स्पष्ट रूप से स्वीकार नहीं",
    "guarantor (aval/fiador) requested": "गारंटर (aval/fiador) माँगा गया है",
    "carné de extranjería requested": "carné de extranjería माँगा गया है",
    "Peruvian DNI requested": "पेरू का DNI माँगा गया है",
    "proof of income requested": "आय का प्रमाण माँगा गया है",
    "utilities included": "सेवाएँ (बिजली/पानी आदि) शामिल",
    "listing written in English": "विज्ञापन अंग्रेज़ी में लिखा है",
    # ---- noise categories and levels (the codes themselves are kept in Latin where shown as codes)
    **NOISE_LABEL,
    "LOW": "कम", "MEDIUM": "मध्यम", "HIGH": "अधिक",
    "high": "उच्च", "medium": "मध्यम", "low": "कम",
    # ---- budget pills / labels
    "All-in ≤ USD 1,000": "कुल खर्च ≤ USD 1,000",
    "Rent ≤ USD 1,000 · total over/unknown": "किराया ≤ USD 1,000 · कुल खर्च अधिक/अज्ञात",
    "Stretch USD 1,001–1,100": "स्ट्रेच USD 1,001–1,100",
    "Borderline — just above USD 1,100": "सीमा-रेखा — USD 1,100 से थोड़ा अधिक",
    # ---- contact guide: what to ask each advertiser
    "exact maintenance fee": "सटीक रखरखाव शुल्क",
    "floor area (m²)": "क्षेत्रफल (m²)",
    "furnished or not": "सुसज्जित है या नहीं",
    "minimum lease term": "न्यूनतम किराया अवधि",
    "deposit months": "जमा राशि (कितने महीने)",
    "does the bedroom face the street or the interior?": "बेडरूम सड़क की ओर है या भीतर की ओर?",
    "exact address/block": "सटीक पता / ब्लॉक",
    "availability and visit times": "उपलब्धता और देखने का समय",
    "Open WhatsApp (pre-filled ES message)": "WhatsApp खोलें (स्पेनिश संदेश पहले से भरा)",
    "No listings in this category for the current run.": "इस खोज में इस श्रेणी का कोई अपार्टमेंट नहीं।",
    # ---- exclusion / sheet reasons
    "district not stated": "ज़िले का उल्लेख नहीं",
    "outside district": "ज़िले के बाहर",
    "fit below near-miss bar": "उपयुक्तता स्कोर आवश्यक स्तर से कम",
}


def _money(s: str) -> str:
    return "जानकारी उपलब्ध नहीं" if s == "UNKNOWN" else s


def _p(rx: str, fn):
    return re.compile(rx), fn


MONEY = r"(?:USD [\d,]+(?:\.\d+)?|UNKNOWN)"
PATTERNS = [
    # money-only formats stay identical
    _p(r"S/ [\d,]+ \(≈ USD [\d,]+\)", lambda m, t: m.group(0)),
    _p(r"(?:USD|PEN|S/) [\d,]+(?:\.\d+)?", lambda m, t: m.group(0)),
    _p(r"WhatsApp \+?[\d ]+", lambda m, t: m.group(0)),
    _p(r"Tel\. (?P<n>\+?[\d ]+)", lambda m, t: f"फ़ोन {m['n']}"),
    # totals
    _p(rf"(?P<r>{MONEY}) \(maintenance included in rent\)", lambda m, t: f"{_money(m['r'])} (रखरखाव शुल्क किराये में शामिल)"),
    _p(rf"≈ (?P<tot>{MONEY}) \((?P<r>{MONEY}) rent \+ (?P<m>S/ [\d,]+|{MONEY}) maintenance\)",
       lambda m, t: f"≈ {_money(m['tot'])} ({_money(m['r'])} किराया + {_money(m['m'])} रखरखाव शुल्क)"),
    _p(rf"(?P<r>{MONEY}) rent \+ maintenance UNKNOWN",
       lambda m, t: f"{_money(m['r'])} किराया + रखरखाव शुल्क: जानकारी उपलब्ध नहीं"),
    _p(rf"= rent \(maint\. incl\.\)", lambda m, t: "= किराया (रखरखाव शुल्क शामिल)"),
    _p(rf"≈ (?P<x>{MONEY})", lambda m, t: f"≈ {_money(m['x'])}"),
    # advantages
    _p(r"(?P<a>\d+) m² (?P<b>built )?area — (?P<band>[a-z ]+) for a (?P<n>\d)-bedroom",
       lambda m, t: f"{m['a']} m² {'निर्मित ' if m['b'] else ''}क्षेत्रफल — {m['n']} बेडरूम के लिए {BAND.get(m['band'], m['band'])}"),
    _p(r"low estimated noise \((?P<n>\d+)/100\)", lambda m, t: f"अनुमानित शोर कम ({m['n']}/100)"),
    _p(r"USD (?P<x>[\d.]+)/m² \((?P<v>excellent value|good value) vs other (?P<b>\d)BR in sample\)",
       lambda m, t: f"USD {m['x']}/m² (नमूने के अन्य {m['b']}BR की तुलना में {VALUE[m['v']]})"),
    _p(rf"all-in ≈ (?P<x>{MONEY})/month", lambda m, t: f"कुल मासिक खर्च ≈ {_money(m['x'])}"),
    _p(rf"all-in ≈ (?P<x>{MONEY})", lambda m, t: f"कुल मासिक खर्च ≈ {_money(m['x'])}"),
    _p(r"(?P<n>\d)-bedroom, (?P<a>\d+) m² \((?P<band>[a-z ]+) for a (?P<b>\d)BR\)",
       lambda m, t: f"{m['n']} बेडरूम, {m['a']} m² ({m['b']}BR के लिए {BAND.get(m['band'], m['band'])})"),
    _p(r"(?P<n>\d)-bedroom \(area not published\)", lambda m, t: f"{m['n']} बेडरूम (क्षेत्रफल प्रकाशित नहीं)"),
    # drawbacks
    _p(r"high estimated noise: (?P<r>.+)", lambda m, t: f"अनुमानित शोर अधिक: {t(m['r'])}"),
    _p(r"only (?P<d>\d+) m from (?P<road>.+)", lambda m, t: f"{m['road']} से केवल {m['d']} मीटर"),
    _p(r"rent \+ maintenance (?P<tt>.+) exceeds USD 1,000", lambda m, t: f"किराया + रखरखाव शुल्क {t(m['tt'])} — USD 1,000 से अधिक"),
    _p(r"only (?P<a>\d+) m²", lambda m, t: f"केवल {m['a']} m²"),
    _p(r"minimum contract (?P<n>\d+) months", lambda m, t: f"न्यूनतम अनुबंध {m['n']} माह"),
    _p(r"(?P<n>\d+) months' deposit", lambda m, t: f"{m['n']} माह की जमा राशि"),
    _p(r"portals disagree: (?P<x>.+)", lambda m, t: f"पोर्टलों के आँकड़ों में अंतर: {m['x']}"),
    # budget notes
    _p(rf"rent within budget but total ≈ (?P<x>{MONEY}) \(over (?P<y>{MONEY})\)",
       lambda m, t: f"किराया बजट में, पर कुल खर्च ≈ {_money(m['x'])} ({_money(m['y'])} से अधिक)"),
    _p(r"rent USD (?P<x>[\d,]+) \(stretch\)", lambda m, t: f"किराया USD {m['x']} (स्ट्रेच)"),
    _p(r"normalised rent USD (?P<x>[\d,.]+) is (?P<p>[\d.]+)% above the USD (?P<s>[\d,]+) stretch ceiling — not budget-compliant",
       lambda m, t: f"सामान्यीकृत किराया USD {m['x']} — USD {m['s']} की स्ट्रेच सीमा से {m['p']}% अधिक; बजट के भीतर नहीं"),
    _p(r"rent USD (?P<x>[\d,]+)", lambda m, t: f"किराया USD {m['x']}"),
    _p(r"Rent USD (?P<x>[\d,]+): above the USD 1,000 target; only worth it if negotiable",
       lambda m, t: f"किराया USD {m['x']}: USD 1,000 के लक्ष्य से अधिक; केवल मोलभाव संभव हो तो विचार करें"),
    # noise evidence
    _p(r"(?P<body>.+)\. Quietness estimate: (?P<c>high|medium|low) confidence\.",
       lambda m, t: f"{t(m['body'])}। शांत वातावरण का अनुमान: {LEVEL[m['c']]} विश्वसनीयता।"),
    _p(r"(?P<d>\d+) m from (?P<n>.+) \(major road\)", lambda m, t: f"{m['n']} (मुख्य सड़क) से {m['d']} मीटर"),
    _p(r"nearest major road \((?P<n>.+)\) (?P<d>\d+) m away", lambda m, t: f"निकटतम मुख्य सड़क ({m['n']}) {m['d']} मीटर दूर"),
    _p(r"fronts/adjacent to (?P<n>.+) \((?P<d>\d+) m\)", lambda m, t: f"{m['n']} के ठीक सामने/बगल में ({m['d']} मीटर)"),
    _p(r"nightclub '(?P<n>.+)' (?P<d>\d+) m away", lambda m, t: f"नाइटक्लब '{m['n']}' {m['d']} मीटर दूर"),
    _p(r"nightclub (?P<d>\d+) m away", lambda m, t: f"नाइटक्लब {m['d']} मीटर दूर"),
    _p(r"no nightclub mapped within (?P<d>\d+) m", lambda m, t: f"{m['d']} मीटर के भीतर कोई नाइटक्लब दर्ज नहीं"),
    _p(r"(?P<n>\d+) bars/pubs within (?P<r>\d+) m", lambda m, t: f"{m['r']} मीटर के भीतर {m['n']} बार/पब"),
    _p(r"(?P<n>\d+) bar\(s\) within (?P<r>\d+) m", lambda m, t: f"{m['r']} मीटर के भीतर {m['n']} बार"),
    _p(r"(?P<n>\d+) restaurants within (?P<r>\d+) m \(busy frontage\)",
       lambda m, t: f"{m['r']} मीटर के भीतर {m['n']} रेस्तरां (व्यस्त इलाका)"),
    _p(r"(?P<d>\d+) m from (?P<n>.+)", lambda m, t: f"{m['n']} से {m['d']} मीटर"),
    _p(r"listing address is on (?P<s>.+?) — a major arterial(?P<v> \(Vía Expresa\))?",
       lambda m, t: f"विज्ञापन का पता {m['s']} पर है — एक मुख्य सड़क (आर्टेरियल){m['v'] or ''}"),
    _p(r"listing mentions '(?P<x>.+)' \(major arterial\) — check the distance",
       lambda m, t: f"विज्ञापन में '{m['x']}' (मुख्य सड़क) का उल्लेख है — उससे दूरी की पुष्टि करें"),
    _p(r"high floor \((?P<n>\d+)\)", lambda m, t: f"ऊँची मंज़िल ({m['n']})"),
    # livability notes, e.g. "supermarket 180 m, park 90 m"
    _p(r"(?:(?:supermarket|pharmacy|park|café|bus/Metropolitano stop|Malecón) \d+ m(?:, )?)+",
       lambda m, t: re.sub(r"(supermarket|pharmacy|park|café|bus/Metropolitano stop|Malecón) (\d+) m",
                           lambda k: f"{PLACES[k.group(1)]} {k.group(2)} मीटर", m.group(0))),
    # common.py value formats
    _p(r"(?P<n>\d+) months min\.", lambda m, t: f"न्यूनतम {m['n']} माह"),
    _p(r"(?P<n>[\d.]+) months? deposit", lambda m, t: f"{m['n']} माह की जमा राशि"),
    _p(r"(?P<n>[\d.]+) in advance", lambda m, t: f"{m['n']} माह अग्रिम"),
    _p(r"minimum stay (?P<n>\d+) months", lambda m, t: f"न्यूनतम अवधि {m['n']} माह"),
    _p(r"Yes \((?P<n>\d+)\)", lambda m, t: f"हाँ ({m['n']})"),
    _p(r"Contact via listing \((?P<s>.+) contact form\)",
       lambda m, t: f"विज्ञापन के माध्यम से संपर्क करें ({m['s']} संपर्क फ़ॉर्म)"),
    # noise cell: "POSSIBLY QUIET · LOW risk · low confidence"
    _p(r"(?P<l>LIKELY QUIET|POSSIBLY QUIET|NOISE UNCERTAIN|LIKELY NOISY) · (?P<r>LOW|MEDIUM|HIGH|UNKNOWN) risk · "
       r"(?P<c>high|medium|low) confidence",
       lambda m, t: f"{NOISE_LABEL[m['l']]} · जोखिम: {RISK[m['r']]} · विश्वसनीयता: {LEVEL[m['c']]}"),
    _p(r"(?P<r>LOW|MEDIUM|HIGH|UNKNOWN) · conf\. (?P<c>high|medium|low)",
       lambda m, t: f"{RISK[m['r']]} · विश्वसनीयता: {LEVEL[m['c']]}"),
    # workbook stamp / subtitles / cell notes
    _p(r"Est\. Total: green = rent \+ maintenance ≤ USD 1,000 · amber = rent within budget but the total is above "
       r"USD 1,000 or maintenance is not published\. Noise is an estimate — visit at rush hour and at night\. (?P<s>.+)\.",
       lambda m, t: ("अनुमानित कुल खर्च: हरा = किराया + रखरखाव शुल्क ≤ USD 1,000 · पीला = किराया बजट में, पर कुल खर्च USD 1,000 "
                     f"से अधिक या रखरखाव शुल्क प्रकाशित नहीं। शोर केवल एक अनुमान है — भीड़ के समय और रात में जाकर देखें। {t(m['s'])}।")),
    _p(r"(?P<s>Generated .+?\)) · Budget-compliant \(rent ≤ USD 1,000\), 1–2 bedrooms, inside Miraflores\. "
       r"Availability as checked at the QA timestamp; not guaranteed\.",
       lambda m, t: (f"{t(m['s'])} · बजट के भीतर (किराया ≤ USD 1,000), 1–2 बेडरूम, Miraflores के भीतर। उपलब्धता जाँच के "
                     "समय के अनुसार; कोई गारंटी नहीं।")),
    _p(r"Published as S/ (?P<p>[\d,]+)\. Converted at 1 USD = S/ (?P<r>[\d.]+) \(see METHODOLOGY\)\."
       r"(?: The portal also shows USD (?P<u>[\d,]+) \((?P<d>[+-][\d.]+)% vs this rate\)\.)?",
       lambda m, t: (f"प्रकाशित किराया S/ {m['p']}। 1 USD = S/ {m['r']} की दर से बदला गया (कार्यप्रणाली देखें)।"
                     + (f" पोर्टल USD {m['u']} भी दिखाता है (इस दर की तुलना में {m['d']}%)।" if m['u'] else ""))),
    _p(r"Listing publishes both USD and S/ (?P<p>[\d,]+)\.", lambda m, t: f"विज्ञापन में USD और S/ {m['p']} दोनों प्रकाशित हैं।"),
    _p(r"BORDERLINE: (?P<x>.+)", lambda m, t: f"BORDERLINE: {t(m['x'])}"),
    _p(r"outside (?P<d>\w+) \((?P<m>\d+) m beyond the boundary\)", lambda m, t: f"{m['d']} के बाहर (सीमा से {m['m']} मीटर आगे)"),
    _p(r"district text '(?P<x>.+)'", lambda m, t: f"ज़िला: '{m['x']}'"),
    _p(r"Generated (?P<ts>\S+) · FX 1 USD = S/ (?P<r>[\d.]+) \((?P<s>.+)\)",
       lambda m, t: f"तैयार: {m['ts']} · विनिमय दर 1 USD = S/ {m['r']} ({FX_SRC.get(m['s'], m['s'])})"),
]
