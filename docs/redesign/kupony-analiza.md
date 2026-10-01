# Kupony – po co i jak mają działać (analiza v2, 01.10.2026)

v1 zakładała „Postaw w Superbet” + „Obserwuj”. Właściciel (01.10): zapamiętywanie
i linki do bukmachera nie mają sensu – gracz przychodzi po to, żeby **wygenerować
i dopasować** kupon i wiedzieć, **jaki jest najlepszy na dziś**. Śledzenie ma w
aplikacji bukmachera.

## Fakty, na których stoi propozycja

- Budowniczy kuponów działa **w przeglądarce** (`lib/kuponBuilder.ts`, parytet z
  pipeline): profile bezpieczny / zbalansowany / agresywny, zasięg osiągalnych
  kursów, alternatywy dla nogi, dołożenie nogi, kary za zależne nogi (ten sam mecz).
  Czyli kupon może się przebudowywać natychmiast, bez czekania na serwer.
- Pula nóg (`legi_pool`) jest w danych strony.
- Pomiar z 05.08: długie i wielodniowe kupony 0 z 41 – do powtórzenia na świeżych danych.
- Dziś „Gram ten kupon” prowadzi donikąd (widok usunięty 04.08) – do usunięcia.

## Od A do Z

**A. Wejście.** Na głównej karta „Kupon dnia” (oś meczów): kurs, szansa, „rozstrzygnie
się do 22:45”. Przycisk: **Dopasuj** → strona Kupony z tym kuponem załadowanym.

**B. „Ile chcesz wygrać?”** Góra strony Kupony: stawka (10 zł) i cel – suwak/miarka
×2 … ×10. Przesuwasz, a kupon pod spodem przebudowuje się na żywo (nogi wjeżdżają
i wyjeżdżają). Obok: „z 10 zł → 51,90 zł”.

**C. Kupon do edycji (oś meczów).** Każda noga: Zamień / Zablokuj / Usuń.
- Zamień: 3 propozycje o podobnym kursie z wpływem na szansę („+6 pp”).
- Zablokuj: noga zostaje przy każdej przebudowie.
- Usuń: kupon sam dobiera nogę, żeby utrzymać cel.
- „Dodaj typ” i kliknięcia w kursy w całej aplikacji trafiają do tego samego kuponu.

**D. Ustawienia (jeden rząd jak filtry):** dzień, zawodnicy / drużyny / wszystko,
rozgrywki, tylko pewne składy, maks. 1 typ z meczu, bukmacher.

**E. Gotowe style jednym dotknięciem:** Bezpieczniejszy (~×2) / Zbalansowany (×3–5) /
Odważny (×8+), zawsze z uczciwą szansą obok.

**F. Powrót przed meczem.** Ostatni kupon pamięta się sam (bez przycisku). Gdy wrócisz:
„kurs Schmida spadł”, „składy ogłoszone – wszystko gra” albo „X nie gra – zamień”.

**G. Zaufanie.** „Kupony dnia z ostatnich 14 dni” – ile weszło, liczone uczciwie.

## Funkcje „wow” (propozycje)

1. **Na 100 takich kuponów** – siatka 10×10 kropek (znak z logo): ile razy wchodzi
   całość, ile razy zabrakło jednej nogi, która noga pada najczęściej.
2. **System zamiast „wszystko albo nic”** – „3 z 4 nóg wchodzi w 52% przypadków.
   System 3/4: wygrywasz przy trzech trafionych”. Superbet przyjmuje systemy.
3. **Najlepszy bukmacher dla tego kuponu** – ten sam zestaw policzony u Superbetu i
   Betclica: „w Betclic ×5,62 zamiast ×5,19”. Rozwiązuje też zasadę jednego bukmachera.
4. **Najsłabsze ogniwo z gotową zamianą** – „zamień X na Y: kurs prawie ten sam,
   szansa +6 pp”, jednym dotknięciem.
5. **Karta do udostępnienia** – ładny obrazek kuponu z logo na Discorda / Instagram
   (reklama, która robi się sama). Uwaga: tylko z uczciwą szansą, bez obietnic.

## Do decyzji

1. Kierunek A–Z (jeden edytowalny kupon, bez „Gram” i bez linków) – tak?
2. Które „wow” robimy (1–5)?
3. Automatyczne pamiętanie ostatniego kuponu na urządzeniu (punkt F) – tak?
4. Zakres celów i styli (×2–×10? wielodniowe?) – po świeżym pomiarze.
5. Wygrana brutto czy po podatku 12%.
