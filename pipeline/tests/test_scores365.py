"""Testy klasyfikacji strzałów 365Scores (bez sieci)."""

from footstats.sources import scores365 as s365


def _ev(outcome_id, body="Right Foot", side=90.0, type_=0):
    return {
        "type": type_,
        "bodyPart": body,
        "side": side,
        "outcome": {"id": outcome_id, "name": "?"},
    }


def test_classify_goal_inside_box():
    c = s365.classify_event(_ev(0, side=90.0))
    assert c["shots"] == 1 and c["sot"] == 1
    assert c["outside"] == 0 and c["blocked"] == 0 and c["off_target"] == 0


def test_classify_header_saved():
    c = s365.classify_event(_ev(2, body="Header", side=95.0))
    assert c["headed"] == 1 and c["headed_sot"] == 1 and c["sot"] == 1


def test_classify_blocked_outside_box():
    c = s365.classify_event(_ev(4, side=70.0))
    assert c["blocked"] == 1 and c["outside"] == 1
    assert c["sot"] == 0 and c["sot_outside"] == 0


def test_classify_missed_outside():
    c = s365.classify_event(_ev(1, side=60.0))
    assert c["off_target"] == 1 and c["outside"] == 1 and c["sot"] == 0


def test_classify_skips_non_shot_types():
    assert s365.classify_event(_ev(0, type_=2)) is None


def test_box_threshold_penalty_is_inside():
    # rzut karny (side ~88.5) musi być w polu karnym
    c = s365.classify_event(_ev(0, side=88.5))
    assert c["outside"] == 0


def test_resolve_player_key_exact_and_fuzzy():
    keys = {"nico paz", "mohamed salah"}
    assert s365.resolve_player_key(keys, "Mohamed Salah") == "mohamed salah"
    assert s365.resolve_player_key(keys, "Nicolás Paz") == "nico paz"
    assert s365.resolve_player_key(keys, "Julian Alvarez") is None


def test_poz_z_formacji_mapuje_kubelki():
    def m(nazwa):
        return {"formation": {"name": nazwa}}
    assert s365._poz_z_formacji(m("Goalkeeper")) == "G"
    assert s365._poz_z_formacji(m("Centre Back")) == "D"
    assert s365._poz_z_formacji(m("Left Wing Back")) == "D"   # wahadlowy to obrona
    assert s365._poz_z_formacji(m("Central Midfield")) == "M"
    assert s365._poz_z_formacji(m("Defensive Midfield")) == "M"
    assert s365._poz_z_formacji(m("Right Winger")) == "F"
    assert s365._poz_z_formacji(m("Striker")) == "F"
    assert s365._poz_z_formacji(m("")) == ""
    assert s365._poz_z_formacji({}) == ""


# --- DOLICZONY CZAS TO NIE DOGRYWKA (2026-07-30) ----------------------------


def _et(gid, **game):
    s365._et_cache.pop(gid, None)
    s365._zapamietaj_et(gid, game)
    return s365._et_cache[gid]


def test_doliczony_czas_nie_jest_dogrywka():
    """Sprawa Fluminense – Bahia (liga brazylijska, 30.07): 365Scores podało
    `gameTime = 98` (90 + 8 doliczonych), a my uznaliśmy to za mecz po
    dogrywce i NIE ROZLICZYLIŚMY rynków drużynowych. Tego dnia wisiało tak
    89 typów — typ znikał ze strony po meczu i nie trafiał do Skuteczności.
    """
    assert _et(1, gameTime=98.0, shortStatusText="Ended", statusText="Ended") is False
    assert _et(2, gameTime=100.0, shortStatusText="Ended") is False
    assert _et(3, gameTime=90.0, shortStatusText="Ended") is False


def test_prawdziwa_dogrywka_dalej_wykrywana():
    # Kairat – Omonia 29.07: 130 minut, „After Penalties"
    assert _et(4, gameTime=130.0, shortStatusText="After Penalties",
               statusText="After Penalties") is True
    # ...także wtedy, gdy minut nie ma, a status mówi wprost
    assert _et(5, gameTime=0.0, shortStatusText="AET") is True
    assert _et(6, gameTime=0.0, statusText="After Extra Time") is True


def test_status_ended_nie_wpada_na_slowie_et():
    """„Ended" nie może przypadkiem wyglądać jak „ET"."""
    assert _et(7, gameTime=95.0, shortStatusText="Ended", statusText="Ended") is False


# --- DOPASOWANIE NAZWY DRUŻYNY (2026-07-30) --------------------------------


def test_resolve_team_key_lapie_inne_warianty_nazwy():
    """365Scores nazywa kluby inaczej niż my. Statystyki drużynowe
    rozliczały się tylko przy IDENTYCZNYM napisie — 26 z 46 wiszących typów
    ginęło wyłącznie na tym."""
    assert s365.resolve_team_key(
        {"cska sofia", "qarabag agdam"}, "Qarabağ") == "qarabag agdam"
    assert s365.resolve_team_key(
        {"banfield", "sarmiento junin"}, "Sarmiento") == "sarmiento junin"
    assert s365.resolve_team_key(
        {"levadia tallinn", "ifk goteborg"},
        "FCI Levadia Tallinn") == "levadia tallinn"
    assert s365.resolve_team_key(
        {"defensa y justicia", "riestra"}, "Deportivo Riestra") == "riestra"
    assert s365.resolve_team_key(
        {"instituto ac cordoba", "platense"},
        "Instituto De Córdoba") == "instituto ac cordoba"


def test_resolve_team_key_nie_zgaduje_po_podobienstwie():
    """PUŁAPKA Z PAMIĘCI PROJEKTU: dla „Deportivo Riestra" najbliższe
    tekstowo jest „Deportivo Recoleta" — INNY klub. Wspólne jest tylko słowo
    szumowe, więc dopasowania nie ma i nie wolno go zgadywać."""
    assert s365.resolve_team_key(
        {"deportivo recoleta", "argentinos juniors"}, "Riestra") is None


def test_resolve_team_key_remis_to_brak_dopasowania():
    """Dwa kluby o tej samej sile dopasowania = nie wiemy, który to."""
    assert s365.resolve_team_key(
        {"gimnasia la plata", "gimnasia mendoza"}, "Gimnasia") is None
    # ...ale gdy nasza nazwa rozstrzyga, wybieramy jednoznacznie
    assert s365.resolve_team_key(
        {"gimnasia la plata", "gimnasia mendoza"},
        "Gimnasia y Esgrima Mendoza") == "gimnasia mendoza"


def test_resolve_team_key_samo_fc_to_za_malo():
    """„FC" wspólne dwóm klubom nie jest dopasowaniem."""
    assert s365.resolve_team_key({"fc porto", "fc basel"}, "FC Kopenhaga") is None


def test_resolve_team_key_dokladny_napis_ma_pierwszenstwo():
    assert s365.resolve_team_key(
        {"bohemians", "bohemian fc"}, "Bohemian FC") == "bohemian fc"


# --- NAZWY, KTÓRE GUBIŁY ROZLICZENIA (zmierzone 2026-08-17) --------------
#
# Diagnoza 20 meczów z wiszącymi typami: mecz znaleziony u źródła, statystyki
# pobrane, drużyna NIEDOPASOWANA — 32 typy w pięciu meczach czekały na dane,
# które leżały gotowe. Rozkład: FC København 9, Olympique Lyonnais 11,
# CD Guadalajara 8, HamKam 4.

def test_ten_sam_klub_inny_podzial_na_slowa():
    """„HamKam" u nas, „Ham-Kam" u źródła — zbiory słów nie mają nic wspólnego."""
    assert s365.resolve_team_key(
        {"brann", "ham-kam"}, "HamKam") == "ham-kam"
    assert s365.resolve_team_key(
        {"brann", "ham-kam"}, "SK Brann") == "brann"


def test_aliasy_z_realnych_wiszacych_typow():
    """København/Copenhagen i Guadalajara/Chivas nie mają wspólnego tokenu."""
    assert s365.resolve_team_key(
        {"fc copenhagen", "randers fc"}, "FC København") == "fc copenhagen"
    assert s365.resolve_team_key(
        {"chivas", "seattle sounders"}, "CD Guadalajara") == "chivas"
    assert s365.resolve_team_key(
        {"lyon", "sparta praha"}, "Olympique Lyonnais") == "lyon"


def test_deportivo_nie_jest_tozsamoscia_klubu():
    """⚑ Najgorsza klasa błędu: rozliczyć typ statystyką INNEGO klubu.

    Docstring `resolve_team_key` obiecuje to od początku, ale bez odsiania
    „deportivo" wspólny token dawał jednoznaczne maksimum i dopasowanie
    wychodziło — bez śladu, a rozliczenie jest nieodwracalne.
    """
    assert s365.resolve_team_key(
        {"deportivo recoleta", "boca juniors"}, "Deportivo Riestra") is None
    # ...a prawdziwe dopasowanie dalej działa
    assert s365.resolve_team_key(
        {"defensa y justicia", "riestra"}, "Deportivo Riestra") == "riestra"
