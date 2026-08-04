"""Rejestr publikacji: typ raz pokazany zostaje na liście do gwizdka.

Regresja 2026-07-26 (Wisła Kraków–GKS): o 13:31 trzy typy drużynowe, o 14:05
zero, kursy Superbetu nietknięte — feed przestał zwracać trend dla drużyny.
Typy poszły do `typy_log` i normalnie się rozliczą, ale z listy zniknęły,
a przy zerze typów mecz wypadał nawet z `matches`.
"""
import time

from footstats.jobs import build_wc_fast as B


def _bet(mecz_id=1, podmiot="GKS Katowice", linia=6.5, kurs=1.23,
         kickoff_ts=None):
    return {
        "mecz_id": mecz_id, "podmiot": podmiot, "rynek_kod": "team_corners",
        "linia": linia, "strona": "ponizej", "kurs": kurs,
        "kickoff_ts": kickoff_ts or (int(time.time()) + 7200),
        "mecz": "Wisła Kraków – GKS Katowice",
    }


def _stub_supa(monkeypatch, magazyn: dict, odczyt_ok: bool = True):
    monkeypatch.setattr(
        B.supa, "get_key_ok",
        lambda k: ((magazyn.get(k), True) if odczyt_ok else (None, False)),
    )
    monkeypatch.setattr(B.supa, "get_key",
                        lambda k: magazyn.get(k) if odczyt_ok else None)
    monkeypatch.setattr(B.supa, "put_key",
                        lambda k, v: magazyn.__setitem__(k, v) or True)
    monkeypatch.setattr(B, "_dry_run", lambda: False)


def test_typ_wraca_gdy_cykl_go_nie_odtworzyl(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    bet = _bet()
    mecze = {1: {"id": 1, "liga": "Ekstraklasa", "gospodarz": "Wisła Kraków"}}

    # cykl 1: typ opublikowany
    out, wzn = B.scal_z_publikacjami([bet], mecze)
    assert len(out) == 1 and wzn == 0

    # cykl 2: feed zamilkł, przeliczenie nie dało nic — a mecz wypadł z bazy
    mecze2: dict = {}
    out2, wzn2 = B.scal_z_publikacjami([], mecze2)
    assert wzn2 == 1
    assert len(out2) == 1
    assert out2[0]["wznowiony"] is True
    assert out2[0]["kurs"] == 1.23        # kurs ZAMROŻONY z publikacji
    assert 1 in mecze2                    # mecz wrócił razem z typem


def test_publikacja_znika_po_kickoffie(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    teraz = int(time.time())
    B.scal_z_publikacjami([_bet(kickoff_ts=teraz + 60)], {1: {"id": 1}})
    # gwizdek minął — dalej rozlicza się z typy_log, ale z listy schodzi
    out, wzn = B.scal_z_publikacjami([], {}, teraz=teraz + 120)
    assert out == [] and wzn == 0
    assert magazyn[B.PUBLIKACJE_KLUCZ] == {}


def test_pierwsza_publikacja_wygrywa_cene(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    B.scal_z_publikacjami([_bet(kurs=1.23)], {1: {"id": 1}}, teraz=1000)
    # kolejny cykl widzi ten sam typ po innym kursie — znacznik publikacji
    # zostaje ten pierwszy, bo to wtedy user go zobaczył
    B.scal_z_publikacjami([_bet(kurs=1.28)], {1: {"id": 1}}, teraz=5000)
    rec = list(magazyn[B.PUBLIKACJE_KLUCZ].values())[0]
    assert rec["opublikowano_ts"] == 1000
    assert rec["bet"]["kurs"] == 1.28      # sama cena jest odświeżana


def test_wznowiony_typ_pokazuje_cene_z_ksiegi(monkeypatch):
    """Rejestr odświeża `bet` w każdym cyklu, a rozliczenie idzie po cenie
    z PIERWSZEJ publikacji — bez tego user widziałby 1,28, a ROI liczyłoby
    się z 1,23."""
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    bet = _bet(kurs=1.23)
    bet["podmiot_id"] = 500
    bet["p_model"] = 0.8
    B.scal_z_publikacjami([bet], {1: {"id": 1}}, teraz=1000)
    B.scal_z_publikacjami([{**bet, "kurs": 1.28}], {1: {"id": 1}}, teraz=2000)
    # cykl bez tego typu — wraca z ceną, po której rozliczy go księga
    ksiega = {"k": _wpis_logu(linia=6.5, strona="ponizej", kurs=1.23,
                              rynek_kod="team_corners")}
    out, wzn = B.scal_z_publikacjami([], {}, teraz=3000, typy_log=ksiega)
    assert wzn == 1 and out[0]["kurs"] == 1.23
    assert out[0]["ev_pct"] == round((0.8 * 1.23 - 1.0) * 100.0, 1)


def test_wpis_bez_kickoffu_wygasa_zamiast_wracac_w_kolko(monkeypatch):
    magazyn: dict = {
        B.PUBLIKACJE_KLUCZ: {
            "zepsuty": {"bet": {"mecz_id": 1, "podmiot": "X"},
                        "kickoff_ts": None, "opublikowano_ts": 1},
        },
    }
    _stub_supa(monkeypatch, magazyn)
    out, wzn = B.scal_z_publikacjami([], {})
    assert out == [] and wzn == 0
    assert magazyn[B.PUBLIKACJE_KLUCZ] == {}


def test_dry_run_nie_zapisuje_rejestru(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    monkeypatch.setattr(B, "_dry_run", lambda: True)
    B.scal_z_publikacjami([_bet()], {1: {"id": 1}})
    assert B.PUBLIKACJE_KLUCZ not in magazyn


# --- DRUGIE ŹRÓDŁO SIATKI: KSIĘGA ROZLICZEŃ ---
# Rejestr publikacji chroni tylko to, co przez niego przeszło. Typy wystawione
# zanim powstał (albo w cyklu, w którym zapis do bazy padł) znikały mimo że
# leżą w typy_log z zamrożoną ceną i normalnie się rozliczą.

def _wpis_logu(**kw) -> dict:
    rec = {
        "mecz_id": 1, "mecz": "Wisła Kraków – GKS Katowice",
        "kickoff_ts": int(time.time()) + 7200,
        "podmiot_id": 500, "podmiot": "GKS Katowice",
        "rynek_kod": "team_corners", "rynek": "Rzuty rożne drużyny",
        "linia": 6.5, "strona": "ponizej", "kurs": 1.28,
        "p_model": 0.8844, "sugestia": False, "wynik": None,
        "opublikowano_ts": 1000,
    }
    rec.update(kw)
    return rec


def test_typ_wraca_z_ksiegi_gdy_rejestr_go_nie_zna(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    mecze: dict = {}
    out, wzn = B.scal_z_publikacjami([], mecze, typy_log={"k": _wpis_logu()})
    assert wzn == 1 and len(out) == 1
    b = out[0]
    assert b["wznowiony"] is True and b["uproszczony"] is True
    assert b["kurs"] == 1.28 and b["p_model"] == 0.8844   # zamrożone przy publikacji
    assert b["podmiot_typ"] == "druzyna" and b["przeciwnik"] == "Wisła Kraków"
    assert b["opublikowano_ts"] == 1000
    # mecz wraca razem z typem — inaczej apka nie ma gdzie go pokazać
    assert mecze[1]["gospodarz"] == "Wisła Kraków"
    assert mecze[1]["gosc"] == "GKS Katowice"


def _policzony(**kw) -> dict:
    """Ten sam typ policzony w BIEŻĄCYM cyklu — z pełnym rachunkiem."""
    rec = {
        "mecz_id": 1, "podmiot": "GKS Katowice", "rynek_kod": "team_corners",
        "linia": 6.5, "strona": "ponizej", "p_model": 0.8844,
        "czynniki": {"rywal": 1.08, "wyjazd": 0.97},
        "uzasadnienie": {"czynniki": [{"nazwa": "Poziom bazowy"}]},
        "ci": [0.81, 0.94], "lambda": 4.31, "rozklad": {"0": 0.1},
        "poza_publikacja": "kwarantanna_strony",
    }
    rec.update(kw)
    return rec


def test_karta_z_ksiegi_odzyskuje_rachunek_policzony_w_tym_cyklu(monkeypatch):
    """Typ zdjęty bramą jest liczony w KAŻDYM cyklu z pełnym rachunkiem, tylko
    trafia do worka „poza publikacją" i tam ginie — a ten sam typ wraca na
    listę z księgi jako uproszczony, bo księga rentgenu nie trzyma.

    Zmierzone 2026-08-04: 9 z 20 kart na stronie nie miało czym wypełnić
    rozwinięcia, a rejestr publikacji trzymał 6 wpisów wobec 46 typów przed
    gwizdkiem w księdze.
    """
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    out, wzn = B.scal_z_publikacjami(
        [], {}, typy_log={"k": _wpis_logu()},
        policzone_w_cyklu=[_policzony()],
    )
    assert wzn == 1
    b = out[0]
    assert b["uproszczony"] is False
    assert b["czynniki"] == {"rywal": 1.08, "wyjazd": 0.97}
    assert b["ci"] == [0.81, 0.94] and b["lambda"] == 4.31
    # ...ale CENA I SZANSA zostają zamrożone przy pierwszej publikacji
    assert b["kurs"] == 1.28 and b["p_model"] == 0.8844


def test_rachunek_nie_dokladany_gdy_szansa_sie_rozjechala(monkeypatch):
    """Karta pokazuje szansę zamrożoną. Gdy dzisiejsze przeliczenie prowadzi
    do wyraźnie innej liczby, jego czynniki tłumaczyłyby COŚ INNEGO niż to,
    co widać na karcie — wtedy lepszy brak rachunku niż rachunek mylący."""
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    out, _ = B.scal_z_publikacjami(
        [], {}, typy_log={"k": _wpis_logu()},
        policzone_w_cyklu=[_policzony(p_model=0.8844 - 0.2)],
    )
    assert out[0]["uproszczony"] is True
    assert out[0]["czynniki"] == {}


def test_ksiega_nie_wskrzesza_tego_czego_user_nie_widzial(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    przypadki = {
        "rozliczony": _wpis_logu(wynik="wygrany"),
        "po_gwizdku": _wpis_logu(kickoff_ts=int(time.time()) - 60),
        "pomiarowy": _wpis_logu(odrzucony=True),
        "kwarantanna": _wpis_logu(poza_publikacja="kwarantanna_rynku"),
        "sugestia_sts": _wpis_logu(sugestia=True),
        "drabinka": _wpis_logu(zrodlo="drabinka"),
        "bez_kursu": _wpis_logu(kurs=None),
    }
    for nazwa, rec in przypadki.items():
        out, wzn = B.scal_z_publikacjami([], {}, typy_log={"k": rec})
        assert out == [] and wzn == 0, nazwa


def test_ksiega_nie_dubluje_typu_z_biezacego_cyklu(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    bet = _bet(linia=6.5, kurs=1.31)
    bet["podmiot_id"] = 500
    out, wzn = B.scal_z_publikacjami([bet], {1: {"id": 1}},
                                     typy_log={"k": _wpis_logu()})
    assert len(out) == 1 and wzn == 0
    assert out[0]["kurs"] == 1.31          # świeży typ, nie kopia z księgi


def test_wznowiony_typ_dostaje_wlasny_numer(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    swiezy = {**_bet(mecz_id=2, podmiot="Piast Gliwice"), "id": 1,
              "podmiot_id": 501}
    out, _ = B.scal_z_publikacjami([swiezy], {2: {"id": 2}},
                                   typy_log={"k": _wpis_logu()})
    numery = [b["id"] for b in out]
    assert len(numery) == len(set(numery)) == 2   # front używa id jako kotwic


def test_nieudany_odczyt_nie_nadpisuje_rejestru(monkeypatch):
    magazyn: dict = {"publikacje_typy": {"stary": {"bet": {}, "kickoff_ts": 0}}}
    _stub_supa(monkeypatch, magazyn, odczyt_ok=False)
    B.scal_z_publikacjami([_bet()], {1: {"id": 1}})
    # baza nie odpowiedziała — rejestru NIE zastępujemy jednym cyklem
    assert magazyn["publikacje_typy"] == {"stary": {"bet": {}, "kickoff_ts": 0}}


def _karta(mecz_id=9, pid=77, linia=2.5, kurs=2.05, kickoff_ts=None):
    return {
        "mecz_id": mecz_id, "podmiot_id": pid, "podmiot": "Nicolas Acevedo",
        "mecz": "Bahia – Corinthians", "rodzaj": "drabinka",
        "kickoff_ts": kickoff_ts or (int(time.time()) + 7200),
        "hero": {"rynek_kod": "shots", "linia": linia, "kurs": kurs,
                 "edge": 0.05},
    }


def test_karta_wraca_gdy_kurs_wypchnal_ja_z_bramy(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    out = B.scal_karty_z_publikacjami([_karta()])
    assert len(out) == 1 and not out[0].get("wznowiony")

    # kolejny cykl: kurs sie skrocil, edge spadl ponizej progu -> zero kart
    out2 = B.scal_karty_z_publikacjami([])
    assert len(out2) == 1
    assert out2[0]["wznowiony"] is True
    assert out2[0]["hero"]["kurs"] == 2.05     # ZAMROZONY kurs z publikacji
    assert out2[0]["id"] == 1                  # numeracja przeliczona


def test_karta_schodzi_po_kickoffie(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    teraz = int(time.time())
    B.scal_karty_z_publikacjami([_karta(kickoff_ts=teraz + 60)])
    assert B.scal_karty_z_publikacjami([], teraz=teraz + 120) == []
    assert magazyn[B.PUBLIKACJE_KART_KLUCZ] == {}
