import httpx

from src.http_client import is_challenge
from src.sources.mercadolibre import parse_detail_html, parse_search_html, to_listing
from src.sources.navent import map_navent_record, norm_currency, parse_navent_search_html

FLAT = {"id": "123", "url": "/propiedades/demo-123.html", "title": "Depa 2 dormitorios", "price": "USD 950",
        "expenses": "S/ 320", "bedrooms": 2, "bathrooms": 2, "coveredArea": "72 m²", "totalArea": 80,
        "latitude": -12.12, "longitude": -77.03, "address": "Calle Demo 123", "district": "Miraflores",
        "publishedText": "Publicado hace 5 días", "images": ["https://img.example/abcdef1234567890-1.jpg"]}
NESTED = {"postingId": "456", "url": "https://example.com/p/456",
          "priceOperationTypes": [{"operationType": {"name": "Alquiler"},
                                   "prices": [{"amount": 3200, "currency": "S/"}, {"amount": 940, "currency": "USD"}]}],
          "expenses": {"amount": 300, "currency": "PEN"},
          "mainFeatures": {"CFT100": {"label": "Área total", "value": "65"}, "CFT2": {"label": "Dormitorios", "value": "1"},
                           "CFT3": {"label": "Baños", "value": "1"}, "CFT4": {"label": "Medio baño", "value": "1"}},
          "postingLocation": {"address": {"name": "Av. Demo 45"}, "location": {"name": "Miraflores"},
                              "postingGeolocation": {"geolocation": {"latitude": -12.11, "longitude": -77.04},
                                                     "showExactLocation": False}},
          "publisher": {"name": "Demo Agency"}}


def test_flat_actor_shape():
    lst = map_navent_record(FLAT, "urbania", "https://urbania.pe", "2026-09-24T10:00:00-05:00")
    assert lst.source_url == "https://urbania.pe/propiedades/demo-123.html"
    assert (lst.rent_original, lst.rent_currency) == (950, "USD")
    assert (lst.maintenance_fee, lst.maintenance_currency) == (320, "PEN")
    assert lst.built_area_m2 == 72 and lst.total_area_m2 == 80
    assert lst.publication_date == "2026-09-19"
    assert lst.image_keys == ["abcdef1234567890"]
    assert lst.active_status == "LIKELY_ACTIVE"


def test_nested_navent_shape_keeps_both_published_prices():
    lst = map_navent_record(NESTED, "adondevivir", "https://www.adondevivir.com")
    assert lst.rent_pen == 3200 and lst.rent_pen_basis == "PUBLISHED"
    assert lst.rent_usd == 940 and lst.rent_usd_basis == "PUBLISHED"
    assert lst.bedrooms == 1 and lst.bathrooms == 1.5 and lst.total_area_m2 == 65
    assert lst.coord_precision == "APPROXIMATE"
    assert lst.district == "Miraflores" and lst.agency_name == "Demo Agency"


def test_coordinates_outside_lima_are_dropped():
    lst = map_navent_record({**FLAT, "latitude": -16.4, "longitude": -71.5}, "urbania", "https://urbania.pe")
    assert lst.latitude is None


def test_inactive_status():
    assert map_navent_record({**FLAT, "status": "FINALIZADO"}, "urbania", "https://urbania.pe").active_status == "INACTIVE"


def test_currency_tokens():
    assert norm_currency("S/.") == "PEN" and norm_currency("US$") == "USD" and norm_currency("USD") == "USD"
    assert norm_currency(None) is None


def test_navent_card_html():
    html = """<div data-qa="posting PROPERTY" data-id="777" data-to-posting="/propiedades/x-777.html">
      <div data-qa="POSTING_CARD_PRICE">USD 900</div><div data-qa="expensas">S/ 250 Mantenimiento</div>
      <h3 data-qa="POSTING_CARD_FEATURES"><span>70 m² tot.</span><span>2 dorm.</span><span>2 baños</span></h3>
      <div data-qa="POSTING_CARD_LOCATION">Miraflores, Lima</div></div>"""
    recs = parse_navent_search_html(html, "https://urbania.pe")
    lst = map_navent_record(recs[0], "urbania", "https://urbania.pe")
    assert lst.source_listing_id == "777" and lst.rent_original == 900 and lst.bedrooms == 2
    assert lst.total_area_m2 == 70 and lst.maintenance_fee == 250


def test_mercadolibre_parsers():
    search = """<ol><li class="ui-search-layout__item"><div class="poly-card">
      <a class="poly-component__title" href="https://departamento.mercadolibre.com.pe/MPE-123456789-demo">Depa Miraflores</a>
      <div class="poly-price__current"><span class="andes-money-amount"><span class="andes-money-amount__currency-symbol">US$</span>
      <span class="andes-money-amount__fraction">850</span></span></div>
      <ul><li class="poly-attributes_list__item">1 dormitorio</li><li class="poly-attributes_list__item">55 m² cubiertos</li></ul>
      <span class="poly-component__location">Calle Demo 1, Miraflores, Lima</span></div></li></ol>"""
    cards = parse_search_html(search)
    assert cards[0]["id"] == "MPE123456789" and cards[0]["price"] == 850 and cards[0]["currency"] == "USD"
    assert cards[0]["bedrooms"] == 1 and cards[0]["built_area_m2"] == 55
    detail = parse_detail_html("""<table><tr class="andes-table__row"><th>Superficie total</th><td>60 m²</td></tr>
      <tr class="andes-table__row"><th>Mantenimiento</th><td>350 PEN</td></tr>
      <tr class="andes-table__row"><th>Amoblado</th><td>Sí</td></tr></table>
      <p class="ui-pdp-description__content">Vista interior</p><span>Publicado hace 4 días</span>
      <script>{"latitude": -12.12, "longitude": -77.03}</script>""")
    lst = to_listing(cards[0], detail, "2026-09-24T10:00:00-05:00")
    assert lst.total_area_m2 == 60 and lst.maintenance_fee == 350 and lst.furnished is True
    assert lst.latitude == -12.12 and lst.publication_date == "2026-09-20"
    assert lst.phone is None           # never collected from Mercado Libre


def test_challenge_detection():
    r = httpx.Response(403, headers={"content-type": "text/html"}, text="<title>Just a moment...</title>")
    assert is_challenge(r)
    ok = httpx.Response(200, headers={"content-type": "text/html"}, text="<html>" + "x" * 70000 + "</html>")
    assert not is_challenge(ok)
