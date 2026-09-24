from src.normalize.text_signals import extract_signals, parse_amount, parse_money, relative_date_days


def test_furnishing_variants():
    assert extract_signals("Departamento amoblado")["furnished"] is True
    s = extract_signals("Departamento semi-amoblado")
    assert s["semi_furnished"] is True and s["furnished"] is False
    assert extract_signals("Se entrega sin amoblar")["furnished"] is False
    assert extract_signals("Unfurnished apartment")["furnished"] is False


def test_terms_parsed_from_spanish_text():
    s = extract_signals("Contrato mínimo 1 año. Dos meses de garantía y 1 mes de adelanto. 7mo piso.")
    assert s["minimum_contract_months"] == 12
    assert s["deposit_months"] == 2
    assert s["advance_months"] == 1
    assert s["floor"] == 7
    assert extract_signals("plazo de 6 meses")["minimum_contract_months"] == 6


def test_noise_signals_and_negations():
    s = extract_signals("Vista interior, ventanas con doble vidrio. No se aceptan mascotas.")
    assert s["interior_view"] and s["acoustic_windows"]
    assert s["pets_allowed"] is False
    assert extract_signals("Frente a la avenida Arequipa")["avenue_view"] is True


def test_maintenance_text_and_inclusion():
    s = extract_signals("Mantenimiento S/ 350 mensual")
    assert s["maintenance_text_amount"] == 350 and s["maintenance_text_currency"] == "PEN"
    assert extract_signals("Precio incluye mantenimiento")["maintenance_included"] is True
    assert "maintenance_text_amount" not in extract_signals("mantenimiento incluido")


def test_money_parsing():
    assert parse_money("US$ 1,050") == (1050.0, "USD")
    assert parse_money("S/ 3.500") == (3500.0, "PEN")
    assert parse_amount("1.250,50") == 1250.5
    assert parse_amount("950") == 950.0


def test_relative_dates():
    assert relative_date_days("Publicado hace 3 días") == 3
    assert relative_date_days("Publicado hace 2 meses") == 60
    assert relative_date_days("Publicado hoy") == 0
    assert relative_date_days("sin fecha") is None
